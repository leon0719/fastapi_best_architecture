"""登入流程:Google 登入 → 一次性登入碼(60 秒)→ 前端帶 PKCE verifier 換 session token。

- 原始 token 只交給使用者一次,DB 只存 sha256 digest(DB 外洩也拿不到可用的 token)。
- 登入碼綁定發起登入的瀏覽器(PKCE S256):發起時帶 challenge,兌換時要附上對應的 verifier,
  別人拿到登入碼(瀏覽器歷史、Referer、log)也換不到 token。
- 兌換用單一 DELETE … RETURNING:兩個請求同時拿同一個碼來換,只有一個刪得到。
"""

import base64
import hashlib
import re
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.external_services import GoogleIdentity
from app.auth.models import AuthToken, TokenKind
from app.common.core.config import config
from app.common.exceptions import ExternalAPIException, UnauthorizedException
from app.users.models import Role, User

LOGIN_CODE_TTL = timedelta(seconds=60)

_CHALLENGE_RE = re.compile(r"[A-Za-z0-9_-]{43}")


def is_valid_challenge(challenge: str | None) -> bool:
    return challenge is not None and _CHALLENGE_RE.fullmatch(challenge) is not None


def challenge_of(verifier: str) -> str:
    """PKCE S256:base64url(sha256(verifier)),去掉 padding。"""
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def _digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    # SQLite(測試)讀回 timestamptz 是 naive;Postgres 是 aware。兩邊都是 UTC。
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def login_error_url(reason: str) -> str:
    """登入失敗導回前端登入頁;reason 是穩定代碼(auth_failed / forbidden / not_registered / not_configured)。"""
    return f"{config.frontend_base_url}/login?error={reason}"


class GoogleClient(Protocol):
    """GoogleOAuthClient 的介面;測試換成 FakeGoogle。"""

    @property
    def configured(self) -> bool: ...
    def authorization_url(self, redirect_uri: str, state: str) -> str: ...
    def fetch_identity(self, code: str, redirect_uri: str) -> GoogleIdentity: ...


class AuthService:
    """Google 登入、登入碼兌換、session 驗證與登出。"""

    def __init__(self, db: Session, google: GoogleClient, now: Callable[[], datetime] = _utc_now) -> None:
        self.db = db
        self.google = google
        self.now = now

    def finish_google_login(
        self,
        code: str | None,
        state: str | None,
        expected_state: str | None,
        challenge: str | None,
        redirect_uri: str,
    ) -> str:
        """處理 Google 導回;回傳要導去的前端完整網址(瀏覽器整頁導轉,不能回 JSON)。

        expected_state、challenge 來自發起登入時存進 session cookie 的值。
        """
        # encode 成 bytes 再比:compare_digest 遇到非 ASCII 的 str 會 raise TypeError
        if (
            not code
            or not state
            or not expected_state
            or not secrets.compare_digest(state.encode(), expected_state.encode())
        ):
            logger.warning("[Service] Google login failed - reason: missing code or state mismatch")
            return login_error_url("auth_failed")
        if not is_valid_challenge(challenge):
            logger.warning("[Service] Google login failed - reason: missing challenge in session")
            return login_error_url("auth_failed")
        try:
            identity = self.google.fetch_identity(code, redirect_uri)
        except ExternalAPIException:
            logger.warning("[Service] Google login failed - reason: token exchange failed")
            return login_error_url("auth_failed")
        if not self._identity_allowed(identity):
            return login_error_url("forbidden")

        user = self._find_or_register(identity)
        if user is None:
            return login_error_url("not_registered")
        if not user.is_active:
            logger.warning(f"[Service] Google login failed - reason: inactive, user_id: {user.id}")
            return login_error_url("forbidden")

        try:
            raw = self._issue(user.id, TokenKind.LOGIN, LOGIN_CODE_TTL, challenge=challenge)
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception(f"[Service] Failed to issue login code - user_id: {user.id}")
            raise
        logger.info(f"[Service] Google login succeeded, login code issued - user_id: {user.id}")
        return f"{config.frontend_base_url}/login/callback?code={raw}"

    def exchange(self, code: str, verifier: str) -> str:
        """一次性登入碼(附上發起登入時的 verifier)換 session token。"""
        row = self.db.execute(
            delete(AuthToken)
            .where(
                AuthToken.digest == _digest(code),
                AuthToken.kind == TokenKind.LOGIN,
                AuthToken.expires_at > self.now(),
            )
            .returning(AuthToken.user_id, AuthToken.challenge)
        ).one_or_none()
        if row is None:
            self.db.rollback()
            logger.warning("[Service] Login code exchange failed - reason: invalid, used or expired")
            raise UnauthorizedException("登入碼無效或已過期")
        user_id, challenge = row
        if challenge is None or not secrets.compare_digest(challenge_of(verifier).encode(), challenge.encode()):
            self.db.commit()  # 登入碼照樣作廢:先 commit 刪除,不能讓之後的 rollback 把它救回來
            logger.warning(f"[Service] Login code exchange failed - reason: verifier mismatch, user_id: {user_id}")
            raise UnauthorizedException("登入碼無效或已過期")
        raw = self._issue(user_id, TokenKind.SESSION, timedelta(days=config.auth_session_ttl_days))
        self.db.commit()
        logger.info(f"[Service] Login code exchanged for session - user_id: {user_id}")
        return raw

    def authenticate(self, token: str) -> User:
        """Bearer token → 使用者;無效、過期、停用一律 401(不透露是哪一種)。"""
        row = self.db.scalar(
            select(AuthToken).where(AuthToken.digest == _digest(token), AuthToken.kind == TokenKind.SESSION)
        )
        if row is None:
            logger.warning("[Service] Authentication failed - reason: unknown session token")
            raise UnauthorizedException("請重新登入")
        if _as_utc(row.expires_at) <= self.now():
            logger.warning(f"[Service] Authentication failed - reason: session expired, user_id: {row.user_id}")
            self.db.delete(row)
            self.db.commit()
            raise UnauthorizedException("請重新登入")
        if not row.user.is_active:
            logger.warning(f"[Service] Authentication failed - reason: user inactive, user_id: {row.user_id}")
            raise UnauthorizedException("請重新登入")
        return row.user

    def logout(self, token: str) -> None:
        self.db.execute(
            delete(AuthToken).where(AuthToken.digest == _digest(token), AuthToken.kind == TokenKind.SESSION)
        )
        self.db.commit()
        logger.info("[Service] Session revoked")

    def purge_expired(self) -> int:
        """刪掉過期的登入碼與 session(排程呼叫),回傳刪除筆數。"""
        result = self.db.execute(delete(AuthToken).where(AuthToken.expires_at <= self.now()))
        self.db.commit()
        deleted = int(getattr(result, "rowcount", 0) or 0)
        logger.info(f"[Service] Purged expired auth tokens - total: {deleted}")
        return deleted

    def issue_session(self, user_id: int) -> str:
        """直接發 session token(壓測 seed、管理腳本用);一般登入請走 Google 流程。"""
        raw = self._issue(user_id, TokenKind.SESSION, timedelta(days=config.auth_session_ttl_days))
        self.db.commit()
        return raw

    def _identity_allowed(self, identity: GoogleIdentity) -> bool:
        if identity.email_verified is not True:
            logger.warning("[Service] Google login failed - reason: email not verified")
            return False
        if config.google_allowed_domain and identity.hosted_domain != config.google_allowed_domain:
            logger.warning(f"[Service] Google login failed - reason: domain mismatch, hd: {identity.hosted_domain}")
            return False
        return True

    def _find_or_register(self, identity: GoogleIdentity) -> User | None:
        email = identity.email.strip().lower()
        user = self.db.scalar(select(User).where(User.email == email))
        if user is not None:
            return user
        if not config.google_auto_register:
            logger.warning("[Service] Google login failed - reason: not registered")
            return None
        user = User(name=identity.name or email.split("@")[0], email=email, role=Role.USER)
        self.db.add(user)
        self.db.flush()
        logger.info(f"[Service] User auto-registered from Google login - user_id: {user.id}")
        return user

    def _issue(self, user_id: int, kind: TokenKind, ttl: timedelta, challenge: str | None = None) -> str:
        """新增一筆 token(由呼叫端 commit),回傳原始值。"""
        raw = secrets.token_urlsafe(32)
        self.db.add(
            AuthToken(user_id=user_id, digest=_digest(raw), kind=kind, expires_at=self.now() + ttl, challenge=challenge)
        )
        return raw
