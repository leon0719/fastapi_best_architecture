"""NotificationService:outbox 入列、送出、重試退避、放棄;LINE webhook 驗簽。"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.common.core.config import config
from app.common.exceptions import BadRequestException, UnauthorizedException
from app.notifications.models import Channel, OutboxNotification
from app.notifications.services import LineWebhookService, NotificationService
from app.notifications.tests.fakes import FakeLine, FakeMailer
from app.notifications.utils import line_signature, subject_for_env, verify_line_signature

pytestmark = pytest.mark.unit

SECRET = "line-test-secret"


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture()
def clock():
    return Clock()


def test_enqueue_does_not_commit(db_session, clock):
    NotificationService(db_session, now=clock).enqueue_email(["a@example.com"], "Hi", "Body")
    db_session.rollback()  # 呼叫端的交易失敗 → 通知也不在

    assert db_session.query(OutboxNotification).count() == 0


def test_email_subject_has_dev_prefix_outside_prod(db_session, clock):
    row = NotificationService(db_session, now=clock).enqueue_email(["a@example.com"], "Hi", "Body")

    assert row.payload["subject"] == "[DEV] Hi"
    assert subject_for_env("Hi", is_prod=True) == "Hi"


def test_dispatch_sends_email_and_line(db_session, clock):
    mailer, line = FakeMailer(), FakeLine()
    service = NotificationService(db_session, mailer=mailer, line=line, now=clock)
    service.enqueue_email(["a@example.com"], "Hi", "Body")
    service.enqueue_line("U123", "哈囉")
    db_session.commit()

    assert service.dispatch_pending() == {"sent": 2, "failed": 0, "abandoned": 0}
    assert mailer.sent == [(["a@example.com"], "[DEV] Hi", "Body")]
    assert line.pushed[0][:2] == ("U123", [{"type": "text", "text": "哈囉"}])
    assert all(r.sent_at is not None for r in db_session.query(OutboxNotification))
    assert service.dispatch_pending() == {"sent": 0, "failed": 0, "abandoned": 0}  # 已送的不重送


def test_failed_send_backs_off_then_abandons(db_session, clock, monkeypatch):
    monkeypatch.setattr(config, "notification_max_retries", 3)
    monkeypatch.setattr(config, "notification_retry_interval_seconds", 60)
    line = FakeLine(fail=True)
    service = NotificationService(db_session, line=line, now=clock)
    row = service.enqueue_line("U123", "hi")
    db_session.commit()
    retry_key = row.payload["retry_key"]

    assert service.dispatch_pending()["failed"] == 1
    assert row.retry_count == 1
    assert row.last_error is not None and "429" in row.last_error
    assert service.dispatch_pending()["failed"] == 0  # 還沒到下次嘗試時間

    clock.now += timedelta(seconds=60)
    assert service.dispatch_pending()["failed"] == 1  # 第 2 次,下次等 120 秒
    clock.now += timedelta(seconds=120)
    assert service.dispatch_pending()["abandoned"] == 1

    assert row.abandoned_at is not None
    assert row.payload["retry_key"] == retry_key  # 重送沿用同一個 key,LINE 端去重


def test_unknown_channel_is_treated_as_failure(db_session, clock):
    db_session.add(OutboxNotification(channel="fax", recipient="x", payload={}, next_attempt_at=clock()))
    db_session.commit()

    assert NotificationService(db_session, now=clock).dispatch_pending()["failed"] == 1


def test_enqueued_channels(db_session, clock):
    service = NotificationService(db_session, now=clock)
    assert service.enqueue_email(["a@x.com", "b@x.com"], "s", "b").recipient == "a@x.com, b@x.com"
    assert service.enqueue_line("U1", "t").channel == Channel.LINE


def test_line_signature_verification():
    body = b'{"events":[]}'
    good = line_signature(body, SECRET)

    assert verify_line_signature(body, good, SECRET)
    assert not verify_line_signature(body, good, "other-secret")
    assert not verify_line_signature(body + b" ", good, SECRET)
    assert not verify_line_signature(body, None, SECRET)
    assert not verify_line_signature(body, line_signature(body, ""), "")  # 未設定 secret 一律拒絕


def test_webhook_service_counts_events():
    body = json.dumps({"events": [{"type": "message"}, {"type": "follow"}]}).encode()

    assert LineWebhookService(SECRET).handle(body, line_signature(body, SECRET)) == 2


def test_webhook_service_rejects_bad_signature_and_body():
    with pytest.raises(UnauthorizedException):
        LineWebhookService(SECRET).handle(b"{}", "bad")
    with pytest.raises(BadRequestException):
        LineWebhookService(SECRET).handle(b"not json", line_signature(b"not json", SECRET))


def test_purge_finished_keeps_pending_and_recent(db_session, clock):
    now = clock()
    old, recent = now - timedelta(days=31), now - timedelta(days=5)
    db_session.add_all(
        [
            OutboxNotification(channel="email", recipient="sent-old", payload={}, next_attempt_at=old, sent_at=old),
            OutboxNotification(
                channel="email", recipient="gave-up-old", payload={}, next_attempt_at=old, abandoned_at=old
            ),
            OutboxNotification(
                channel="email", recipient="sent-recent", payload={}, next_attempt_at=recent, sent_at=recent
            ),
            OutboxNotification(channel="email", recipient="pending-old", payload={}, next_attempt_at=old),
        ]
    )
    db_session.commit()
    service = NotificationService(db_session, now=clock)

    assert service.purge_finished(0) == 0  # 0 = 永久保存
    assert service.purge_finished(30) == 2
    assert sorted(r.recipient for r in db_session.query(OutboxNotification)) == ["pending-old", "sent-recent"]


def test_retention_task_uses_setting(db_session, clock, monkeypatch):
    from app.notifications.tasks import OutboxRetentionTask

    monkeypatch.setattr(config, "notification_retention_days", 30)
    db_session.add(
        OutboxNotification(
            channel="line",
            recipient="U1",
            payload={},
            next_attempt_at=clock(),
            sent_at=datetime(2000, 1, 1, tzinfo=UTC),
        )
    )
    db_session.commit()

    assert OutboxRetentionTask().run(db_session) == "deleted: 1"
