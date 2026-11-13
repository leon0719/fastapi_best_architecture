"""record_audit / diff / 保留期清理。"""

from datetime import UTC, datetime, timedelta

import pytest

from app.audit.models import AuditLog, AuditSource
from app.audit.services import AuditService, record_audit, snapshot
from app.audit.utils import MASK, diff
from app.common.core.request_context import set_request_id
from app.users.models import User

pytestmark = pytest.mark.unit


def test_diff_keeps_only_changed_fields():
    assert diff({"a": 1, "b": 2}, {"a": 1, "b": 3, "c": None}) == {"b": [2, 3]}


def test_diff_masks_sensitive_fields():
    changes = diff({"password_hash": "old", "api_key": None}, {"password_hash": "new", "api_key": "k"})

    assert changes == {"api_key": [None, MASK], "password_hash": [MASK, MASK]}


def test_diff_masks_extra_fields():
    assert diff({"pin": "1"}, {"pin": "2"}, masked=frozenset({"pin"})) == {"pin": [MASK, MASK]}


def test_record_audit_joins_caller_transaction(db_session):
    set_request_id("req-1")
    user = User(name="alice")
    db_session.add(user)
    db_session.flush()

    record_audit(db_session, action="create", target_type="User", target_id=user.id, after=snapshot(user), ip="1.2.3.4")
    db_session.rollback()

    assert db_session.query(AuditLog).count() == 0  # 資料 rollback,紀錄也不留


def test_record_audit_persists_with_commit(db_session):
    set_request_id("req-2")

    record_audit(
        db_session, action="role_change", target_type="User", target_id=7, before={"role": "user"},
        after={"role": "admin"}, actor="user:1", source=AuditSource.API,
    )  # fmt: skip
    db_session.commit()

    row = db_session.query(AuditLog).one()
    assert (row.action, row.target_id, row.actor, row.request_id) == ("role_change", "7", "user:1", "req-2")
    assert row.changes == {"role": ["user", "admin"]}


def test_snapshot_skips_pk_and_timestamps(db_session):
    user = User(name="alice", email="a@example.com")
    db_session.add(user)
    db_session.commit()

    snap = snapshot(user)

    assert "id" not in snap
    assert "created_at" not in snap
    assert snap["name"] == "alice"


def test_purge_older_than(db_session):
    now = datetime(2026, 6, 1, tzinfo=UTC)
    db_session.add_all(
        [
            AuditLog(source="api", action="a", target_type="T", changes={}, created_at=now - timedelta(days=400)),
            AuditLog(source="api", action="b", target_type="T", changes={}, created_at=now - timedelta(days=10)),
        ]
    )
    db_session.commit()
    service = AuditService(db_session, now=lambda: now)

    assert service.purge_older_than(0) == 0  # 0 = 永久保存
    assert service.purge_older_than(365) == 1
    assert [r.action for r in db_session.query(AuditLog)] == ["b"]
