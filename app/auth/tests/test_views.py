"""登入端點。Google 以 dependency override 換成 FakeGoogle,不連網。"""

from urllib.parse import parse_qs, urlparse

import pytest

from app.auth.dependencies import get_google_client
from app.auth.services import challenge_of
from app.auth.tests.fakes import FakeGoogle
from app.common.core.config import config
from app.users.models import User

pytestmark = pytest.mark.unit

URL = "/api/v1/auth"
VERIFIER = "x" * 64
CHALLENGE = challenge_of(VERIFIER)


@pytest.fixture()
def google(client):
    fake = FakeGoogle()
    client.app.dependency_overrides[get_google_client] = lambda: fake
    return fake


@pytest.fixture()
def alice(db_session):
    user = User(name="Alice", email="alice@example.com")
    db_session.add(user)
    db_session.commit()
    return user


def _full_login(client) -> str:
    """login → callback → 前端拿到登入碼。"""
    login = client.get(f"{URL}/google/login", params={"challenge": CHALLENGE}, follow_redirects=False)
    assert login.status_code == 302
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    callback = client.get(
        f"{URL}/google/callback", params={"code": "google-code", "state": state}, follow_redirects=False
    )
    assert callback.status_code == 302
    return parse_qs(urlparse(callback.headers["location"]).query)["code"][0]


def test_full_pkce_login_flow(client, google, alice):
    code = _full_login(client)

    resp = client.post(f"{URL}/exchange", json={"code": code, "verifier": VERIFIER})

    assert resp.status_code == 200
    token = resp.json()["data"]["token"]
    me = client.get(f"{URL}/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["data"] == {
        "id": alice.id,
        "name": "Alice",
        "email": "alice@example.com",
        "role": "user",
        "roles": ["user"],
    }


def test_callback_state_is_single_use(client, google, alice):
    login = client.get(f"{URL}/google/login", params={"challenge": CHALLENGE}, follow_redirects=False)
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    client.get(f"{URL}/google/callback", params={"code": "c", "state": state}, follow_redirects=False)

    replay = client.get(f"{URL}/google/callback", params={"code": "c", "state": state}, follow_redirects=False)

    assert replay.headers["location"].endswith("/login?error=auth_failed")


def test_login_with_invalid_challenge_redirects_to_error(client, google):
    resp = client.get(f"{URL}/google/login", params={"challenge": "bad"}, follow_redirects=False)

    assert resp.status_code == 302
    assert resp.headers["location"] == f"{config.frontend_base_url}/login?error=auth_failed"


def test_login_when_google_not_configured(client):
    resp = client.get(f"{URL}/google/login", params={"challenge": CHALLENGE}, follow_redirects=False)

    assert resp.headers["location"].endswith("/login?error=not_configured")


def test_exchange_wrong_verifier_returns_401(client, google, alice):
    code = _full_login(client)

    resp = client.post(f"{URL}/exchange", json={"code": code, "verifier": "y" * 64})

    assert resp.status_code == 401
    assert resp.json()["error"] == {"code": 401, "message": "登入碼無效或已過期", "reason": "unauthenticated"}


def test_exchange_validates_verifier_format(client):
    resp = client.post(f"{URL}/exchange", json={"code": "c", "verifier": "short"})

    assert resp.status_code == 422


def test_me_without_token_returns_401(client):
    resp = client.get(f"{URL}/me")

    assert resp.status_code == 401
    assert resp.json()["error"]["reason"] == "unauthenticated"


def test_admin_me_returns_expanded_roles(client, make_user):
    _, headers = make_user("admin")

    assert client.get(f"{URL}/me", headers=headers).json()["data"]["roles"] == ["admin", "user"]


def test_logout(client, make_user):
    _, headers = make_user()

    resp = client.post(f"{URL}/logout", headers=headers)

    assert resp.json() == {"data": None, "error": None}
    assert client.get(f"{URL}/me", headers=headers).status_code == 401


def test_exchange_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(config, "rate_limit_auth", "2/minute")
    body = {"code": "c", "verifier": VERIFIER}

    statuses = [client.post(f"{URL}/exchange", json=body).status_code for _ in range(3)]

    assert statuses == [401, 401, 429]
    resp = client.post(f"{URL}/exchange", json=body)
    assert resp.json()["error"] == {
        "code": 429,
        "message": "Too many requests, please try again later",
        "reason": "rate_limited",
    }
