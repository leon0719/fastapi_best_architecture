"""AdminAuditMixin:SQLAdmin 的新增/修改/刪除寫進 AuditLog(含 IP、欄位 diff)。"""

import asyncio

import pytest
from starlette.requests import Request

from app.audit.models import AuditLog, AuditSource
from app.users.admin import UserAdmin
from app.users.models import User

pytestmark = pytest.mark.unit


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "headers": [(b"x-real-ip", b"203.0.113.9")], "client": None})


@pytest.fixture()
def view(session_factory):
    admin_view = UserAdmin()
    # Admin.add_view() 平常會設這兩個;這裡直接接到測試 DB
    admin_view.session_maker = session_factory  # type: ignore[misc]  # sqladmin 宣告成 ClassVar,實際由 add_view 指派
    admin_view.is_async = False  # type: ignore[misc]  # 同上
    return admin_view


def test_create_update_delete_are_audited(view, db_session):
    obj = asyncio.run(
        view.insert_model(_request(), {"name": "alice", "email": "a@example.com", "role": "user", "is_active": True})
    )
    asyncio.run(view.update_model(_request(), str(obj.id), {"name": "alicia"}))
    asyncio.run(view.delete_model(_request(), str(obj.id)))

    logs = db_session.query(AuditLog).order_by(AuditLog.id).all()
    assert [log.action for log in logs] == ["create", "update", "delete"]
    assert all(log.source == AuditSource.ADMIN and log.ip == "203.0.113.9" for log in logs)
    assert logs[0].changes["email"] == [None, "a@example.com"]
    assert logs[1].changes == {"name": ["alice", "alicia"]}
    assert logs[2].changes["name"] == ["alicia", None]
    assert logs[2].target_label == "alicia（a@example.com）"
    assert db_session.query(User).count() == 0


def test_save_without_changes_is_not_audited(view, db_session):
    obj = asyncio.run(view.insert_model(_request(), {"name": "alice", "role": "user", "is_active": True}))

    asyncio.run(view.update_model(_request(), str(obj.id), {"name": "alice"}))

    assert [log.action for log in db_session.query(AuditLog)] == ["create"]
