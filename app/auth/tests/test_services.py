"""AuthService:Google 登入、PKCE 兌換、session 驗證。Google 一律用 FakeGoogle。"""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest

from app.auth.external_services import GoogleIdentity
from app.auth.models import AuthToken, TokenKind
from app.auth.services import AuthService, challenge_of, is_valid_challenge
from app.auth.tests.fakes import FakeGoogle
from app.common.core.config import config
from app.common.exceptions import UnauthorizedException
from app.users.models import Role, User

pytestmark = pytest.mark.unit

VERIFIER = "v" * 43
CHALLENGE = challenge_of(VERIFIER)
REDIRECT = "http://testserver/api/v1/auth/google/callback"


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture()
def clock():
    return Clock()


@pytest.fixture()
def alice(db_session):
    user = User(name="Alice", email="alice@example.com")
    db_session.add(user)
    db_session.commit()
    return user


def _service(db_session, clock, google=None):
    return AuthService(db_session, google or FakeGoogle(), now=clock)


def _login(service) -> str:
    """跑完 callback,回傳一次性登入碼。"""
    target = service.finish_google_login("google-code", "s", "s", CHALLENGE, REDIRECT)
    return parse_qs(urlparse(target).query)["code"][0]


def test_challenge_format():
    assert is_valid_challenge(CHALLENGE)
    assert not is_valid_challenge("short")
    assert not is_valid_challenge(None)


def test_login_redirects_with_one_time_code(db_session, clock, alice):
    target = _service(db_session, clock).finish_google_login("google-code", "s", "s", CHALLENGE, REDIRECT)

    assert target.startswith(f"{config.frontend_base_url}/login/callback?code=")
    row = db_session.query(AuthToken).one()
    assert row.kind == TokenKind.LOGIN
    assert row.challenge == CHALLENGE
    assert parse_qs(urlparse(target).query)["code"][0] != row.digest  # DB 只存 hash


@pytest.mark.parametrize(
    ("state", "expected"),
    [(None, "s"), ("s", None), ("s", "other")],
)
def test_login_rejects_bad_state(db_session, clock, alice, state, expected):
    target = _service(db_session, clock).finish_google_login("c", state, expected, CHALLENGE, REDIRECT)

    assert target.endswith("/login?error=auth_failed")


def test_login_rejects_missing_challenge(db_session, clock, alice):
    target = _service(db_session, clock).finish_google_login("c", "s", "s", None, REDIRECT)

    assert target.endswith("error=auth_failed")


def test_login_handles_google_failure(db_session, clock, alice):
    target = _service(db_session, clock, FakeGoogle(fail=True)).finish_google_login("c", "s", "s", CHALLENGE, REDIRECT)

    assert target.endswith("error=auth_failed")


def test_login_requires_verified_email(db_session, clock, alice):
    google = FakeGoogle(GoogleIdentity("alice@example.com", email_verified=False, hosted_domain=None, name=None))

    target = _service(db_session, clock, google).finish_google_login("c", "s", "s", CHALLENGE, REDIRECT)

    assert target.endswith("error=forbidden")


def test_login_enforces_hosted_domain(db_session, clock, alice, monkeypatch):
    monkeypatch.setattr(config, "google_allowed_domain", "corp.example.com")

    target = _service(db_session, clock).finish_google_login("c", "s", "s", CHALLENGE, REDIRECT)

    assert target.endswith("error=forbidden")


def test_login_unregistered_user(db_session, clock):
    target = _service(db_session, clock).finish_google_login("c", "s", "s", CHALLENGE, REDIRECT)

    assert target.endswith("error=not_registered")
    assert db_session.query(User).count() == 0


def test_login_auto_registers_when_enabled(db_session, clock, monkeypatch):
    monkeypatch.setattr(config, "google_auto_register", True)

    _login(_service(db_session, clock))

    user = db_session.query(User).one()
    assert (user.email, user.name, user.role) == ("alice@example.com", "Alice", Role.USER)


def test_login_rejects_inactive_user(db_session, clock, alice):
    alice.is_active = False
    db_session.commit()

    target = _service(db_session, clock).finish_google_login("c", "s", "s", CHALLENGE, REDIRECT)

    assert target.endswith("error=forbidden")


def test_exchange_issues_session_once(db_session, clock, alice):
    service = _service(db_session, clock)
    code = _login(service)

    token = service.exchange(code, VERIFIER)

    assert service.authenticate(token).id == alice.id
    with pytest.raises(UnauthorizedException):
        service.exchange(code, VERIFIER)  # 一次性:DELETE … RETURNING 後就沒了


def test_exchange_with_wrong_verifier_burns_the_code(db_session, clock, alice):
    service = _service(db_session, clock)
    code = _login(service)

    with pytest.raises(UnauthorizedException):
        service.exchange(code, "w" * 43)
    with pytest.raises(UnauthorizedException):
        service.exchange(code, VERIFIER)


def test_exchange_expired_code(db_session, clock, alice):
    service = _service(db_session, clock)
    code = _login(service)
    clock.now += timedelta(seconds=61)

    with pytest.raises(UnauthorizedException):
        service.exchange(code, VERIFIER)


def test_authenticate_rejects_unknown_expired_and_inactive(db_session, clock, alice):
    service = _service(db_session, clock)
    token = service.exchange(_login(service), VERIFIER)

    with pytest.raises(UnauthorizedException):
        service.authenticate("nope")

    alice.is_active = False
    db_session.commit()
    with pytest.raises(UnauthorizedException):
        service.authenticate(token)

    alice.is_active = True
    db_session.commit()
    clock.now += timedelta(days=config.auth_session_ttl_days, seconds=1)
    with pytest.raises(UnauthorizedException):
        service.authenticate(token)
    assert db_session.query(AuthToken).count() == 0  # 過期的順手刪掉


def test_logout_revokes_session(db_session, clock, alice):
    service = _service(db_session, clock)
    token = service.exchange(_login(service), VERIFIER)

    service.logout(token)

    with pytest.raises(UnauthorizedException):
        service.authenticate(token)


def test_purge_expired(db_session, clock, alice):
    service = _service(db_session, clock)
    _login(service)  # 60 秒的登入碼
    service.issue_session(alice.id)  # 30 天的 session
    clock.now += timedelta(minutes=5)

    assert service.purge_expired() == 1
    assert db_session.query(AuthToken).one().kind == TokenKind.SESSION


def test_roles_are_expanded(alice):
    assert alice.roles == ["user"]
    alice.role = Role.ADMIN
    assert alice.roles == ["admin", "user"]
    assert alice.has_any_role(Role.USER)


def test_unknown_role_is_rejected(alice):
    with pytest.raises(ValueError):
        alice.role = "superuser"
