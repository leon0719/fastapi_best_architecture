"""UserService tests — the reference for service-layer tests.

Cover every business rule and every exception branch here, before writing the views.
"""

import pytest

from app.common.exceptions import ConflictException, NotFoundException
from app.users.schemas import UserCreate, UserUpdate
from app.users.services import UserService

pytestmark = pytest.mark.unit


@pytest.fixture()
def service(db_session):
    return UserService(db_session)


def test_create_user(service):
    user = service.create_user(UserCreate(name="alice"))

    assert user.id is not None
    assert user.name == "alice"


def test_create_user_with_taken_name_raises_conflict(service):
    service.create_user(UserCreate(name="alice"))

    with pytest.raises(ConflictException):
        service.create_user(UserCreate(name="alice"))


def test_get_missing_user_raises_not_found(service):
    with pytest.raises(NotFoundException):
        service.get_user(999)


def test_list_users_is_newest_first_and_paginated(service):
    for name in ("a", "b", "c"):
        service.create_user(UserCreate(name=name))

    assert [u.name for u in service.list_users()] == ["c", "b", "a"]
    assert [u.name for u in service.list_users(skip=1, limit=1)] == ["b"]


def test_update_user_can_keep_its_own_name(service):
    user = service.create_user(UserCreate(name="alice"))

    updated = service.update_user(user.id, UserUpdate(name="alice"))

    assert updated.name == "alice"


def test_update_user_to_taken_name_raises_conflict(service):
    service.create_user(UserCreate(name="alice"))
    bob = service.create_user(UserCreate(name="bob"))

    with pytest.raises(ConflictException):
        service.update_user(bob.id, UserUpdate(name="alice"))


def test_delete_user(service):
    user = service.create_user(UserCreate(name="alice"))

    service.delete_user(user.id)

    with pytest.raises(NotFoundException):
        service.get_user(user.id)


def test_writes_are_audited_in_the_same_transaction(service, db_session):
    from app.audit.models import AuditLog

    user = service.create_user(UserCreate(name="alice"), actor="user:1")
    service.update_user(user.id, UserUpdate(name="alicia"), actor="user:1")
    service.delete_user(user.id, actor="user:1")

    logs = db_session.query(AuditLog).order_by(AuditLog.id).all()
    assert [(log.action, log.actor, log.target_id) for log in logs] == [
        ("create", "user:1", str(user.id)),
        ("update", "user:1", str(user.id)),
        ("delete", "user:1", str(user.id)),
    ]
    assert logs[1].changes == {"name": ["alice", "alicia"]}


def test_failed_create_leaves_no_audit_row(service, db_session):
    from app.audit.models import AuditLog

    service.create_user(UserCreate(name="alice"))
    with pytest.raises(ConflictException):
        service.create_user(UserCreate(name="alice"))

    assert db_session.query(AuditLog).count() == 1


def test_export_rows(service):
    service.create_user(UserCreate(name="alice"))

    headers, rows = service.export_rows()

    assert headers[:2] == ["ID", "名稱"]
    assert rows[0][1] == "alice"
    assert rows[0][3] == "user"
