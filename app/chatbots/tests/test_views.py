"""Chatbot endpoints: reads need login, writes need admin (system_prompt controls LLM behavior)."""

import pytest

pytestmark = pytest.mark.unit

URL = "/api/v1/chatbots"


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", URL), ("post", URL), ("get", f"{URL}/1"), ("put", f"{URL}/1"), ("delete", f"{URL}/1")],
)
def test_requires_login(client, method, path):
    resp = client.request(method, path, json={"name": "x"})

    assert resp.status_code == 401
    assert resp.json()["error"]["reason"] == "unauthenticated"


@pytest.mark.parametrize(("method", "path"), [("post", URL), ("put", f"{URL}/1"), ("delete", f"{URL}/1")])
def test_writes_require_admin_role(client, make_user, method, path):
    _, headers = make_user("user")

    resp = client.request(method, path, json={"name": "x"}, headers=headers)

    assert resp.status_code == 403


def test_logged_in_user_can_read(client, make_user, admin_headers):
    bot_id = client.post(URL, json={"name": "bot"}, headers=admin_headers).json()["data"]["id"]
    _, headers = make_user("user")

    assert client.get(URL, headers=headers).json()["data"][0]["name"] == "bot"
    assert client.get(f"{URL}/{bot_id}", headers=headers).json()["data"]["name"] == "bot"


def test_admin_writes_are_audited(client, make_user, db_session):
    from app.audit.models import AuditLog
    from app.users.models import Role

    admin, headers = make_user(Role.ADMIN, name="admin")

    resp = client.post(URL, json={"name": "bot", "system_prompt": "a"}, headers=headers)
    assert resp.status_code == 201
    bot_id = resp.json()["data"]["id"]
    client.put(f"{URL}/{bot_id}", json={"system_prompt": "b"}, headers=headers)
    client.delete(f"{URL}/{bot_id}", headers=headers)

    logs = db_session.query(AuditLog).filter(AuditLog.target_type == "Chatbot").order_by(AuditLog.id).all()
    assert [(log.action, log.actor, log.target_id) for log in logs] == [
        ("create", f"user:{admin.id}", str(bot_id)),
        ("update", f"user:{admin.id}", str(bot_id)),
        ("delete", f"user:{admin.id}", str(bot_id)),
    ]
    assert logs[1].changes["system_prompt"] == ["a", "b"]
