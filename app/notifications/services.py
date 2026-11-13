"""通知:先寫 outbox(跟業務資料同一交易),由排程送出、失敗重送、超過次數放棄。

    NotificationService(db).enqueue_email(["a@x.com"], "主旨", "內文")
    db.commit()   # 呼叫端的 commit;資料 rollback 通知也不會送

不要在請求裡直接呼叫 mailer / LINE:第三方慢或掛掉會拖垮請求,失敗也沒有重送。
"""

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from loguru import logger
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.common.core.config import config
from app.common.exceptions import BadRequestException, ErrorCode, ExternalAPIException, UnauthorizedException
from app.notifications.external_services import LineMessagingClient, SmtpMailer
from app.notifications.models import Channel, OutboxNotification
from app.notifications.utils import subject_for_env, verify_line_signature

_MAX_BACKOFF = timedelta(hours=6)


class Mailer(Protocol):
    def send(self, to: list[str], subject: str, body: str) -> None: ...


class LinePusher(Protocol):
    def push(self, to: str, messages: list[dict], retry_key: str) -> None: ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


class NotificationService:
    def __init__(
        self,
        db: Session,
        mailer: Mailer | None = None,
        line: LinePusher | None = None,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.db = db
        self.mailer = mailer
        self.line = line
        self.now = now

    def enqueue_email(self, to: list[str], subject: str, body: str) -> OutboxNotification:
        """加入 session,不 commit。標題在入列時就決定([DEV] 前綴),重送時不會變。"""
        payload = {"to": to, "subject": subject_for_env(subject, config.is_prod), "body": body}
        return self._enqueue(Channel.EMAIL, ", ".join(to), payload)

    def enqueue_line(self, to: str, text: str) -> OutboxNotification:
        """to 是 LINE userId / groupId。retry_key 入列時產生,重送沿用,LINE 端去重。"""
        payload = {"to": to, "messages": [{"type": "text", "text": text}], "retry_key": str(uuid.uuid4())}
        return self._enqueue(Channel.LINE, to, payload)

    def _enqueue(self, channel: Channel, recipient: str, payload: dict[str, Any]) -> OutboxNotification:
        row = OutboxNotification(
            channel=channel, recipient=recipient[:500], payload=payload, next_attempt_at=self.now()
        )
        self.db.add(row)
        logger.info(f"[Service] Notification enqueued - channel: {channel}")
        return row

    def dispatch_pending(self, limit: int = 50) -> dict[str, int]:
        """送出到期的待送通知(排程呼叫)。一次鎖一筆(FOR UPDATE SKIP LOCKED),多 worker 不會重複送。"""
        counts = {"sent": 0, "failed": 0, "abandoned": 0}
        for _ in range(limit):
            row = self.db.scalar(
                select(OutboxNotification)
                .where(
                    OutboxNotification.sent_at.is_(None),
                    OutboxNotification.abandoned_at.is_(None),
                    OutboxNotification.next_attempt_at <= self.now(),
                )
                .order_by(OutboxNotification.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if row is None:
                break
            counts[self._attempt(row)] += 1
            self.db.commit()
        if any(counts.values()):
            logger.info(f"[Service] Outbox dispatched - {counts}")
        return counts

    def purge_finished(self, days: int) -> int:
        """刪掉已送出或已放棄、且超過保留天數的列(排程呼叫);待送的永遠不刪。days <= 0 = 永久保存。"""
        if days <= 0:
            return 0
        cutoff = self.now() - timedelta(days=days)
        try:
            result = self.db.execute(
                delete(OutboxNotification).where(
                    or_(OutboxNotification.sent_at < cutoff, OutboxNotification.abandoned_at < cutoff)
                )
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception(f"[Service] Failed to purge outbox - retention_days: {days}")
            raise
        deleted = int(getattr(result, "rowcount", 0) or 0)
        logger.info(f"[Service] Purged finished outbox rows - total: {deleted}, retention_days: {days}")
        return deleted

    def _attempt(self, row: OutboxNotification) -> str:
        try:
            self._send(row)
        except ExternalAPIException as e:
            row.retry_count += 1
            row.last_error = e.message[:1000]
            if row.retry_count >= config.notification_max_retries:
                row.abandoned_at = self.now()
                logger.error(
                    f"[Service] Notification abandoned - id: {row.id}, channel: {row.channel}, "
                    f"retry_count: {row.retry_count}"
                )
                return "abandoned"
            backoff = timedelta(seconds=config.notification_retry_interval_seconds * 2 ** (row.retry_count - 1))
            row.next_attempt_at = self.now() + min(backoff, _MAX_BACKOFF)
            logger.warning(f"[Service] Notification failed, will retry - id: {row.id}, retry_count: {row.retry_count}")
            return "failed"
        row.sent_at = self.now()
        return "sent"

    def _send(self, row: OutboxNotification) -> None:
        payload = row.payload
        if row.channel == Channel.EMAIL:
            (self.mailer or get_mailer()).send(payload["to"], payload["subject"], payload["body"])
        elif row.channel == Channel.LINE:
            (self.line or get_line_client()).push(payload["to"], payload["messages"], payload["retry_key"])
        else:
            raise ExternalAPIException(f"未知的通知管道: {row.channel}")


def get_mailer() -> SmtpMailer:
    return SmtpMailer(
        config.smtp_host, config.smtp_port, config.smtp_username, config.smtp_password, config.smtp_from_email
    )


def get_line_client() -> LineMessagingClient:
    return LineMessagingClient(config.line_channel_access_token)


class LineWebhookService:
    """LINE inbound webhook:驗簽後交給 handle_event。"""

    def __init__(self, channel_secret: str) -> None:
        self.channel_secret = channel_secret

    def handle(self, body: bytes, signature: str | None) -> int:
        """驗證 X-Line-Signature(HMAC-SHA256),回傳處理的事件數。簽章不符 → 401。"""
        if not verify_line_signature(body, signature, self.channel_secret):
            logger.warning(
                f"[Service] LINE webhook rejected - reason: invalid signature, secret_configured: "
                f"{bool(self.channel_secret)}"
            )
            raise UnauthorizedException("Invalid LINE signature", reason=ErrorCode.INVALID_SIGNATURE)
        try:
            events = json.loads(body).get("events", [])
        except (ValueError, AttributeError) as e:
            logger.warning("[Service] LINE webhook rejected - reason: malformed body")
            raise BadRequestException("Malformed LINE webhook body") from e
        for event in events:
            self.handle_event(event)
        logger.info(f"[Service] LINE webhook handled - events: {len(events)}")
        return len(events)

    def handle_event(self, event: dict[str, Any]) -> None:
        """依事件類型處理(message / follow / unfollow / postback …)。模板只記錄類型;專案在這裡接業務邏輯。

        不要記錄訊息內容或 userId 以外的個資。LINE 會重送 webhook(deliveryContext.isRedelivery),
        有副作用的處理要以 webhookEventId 去重。
        """
        logger.info(f"[Service] LINE event received - type: {event.get('type')}")
