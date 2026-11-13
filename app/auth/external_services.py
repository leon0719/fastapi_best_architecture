"""Google OAuth 2.0(授權碼流程):產生登入網址、用授權碼換回並驗證 ID token。"""

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleTransportRequest
from google.oauth2 import id_token
from loguru import logger

from app.common.core.retry import retry_external
from app.common.exceptions import ExternalAPIException

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105  # 公開端點網址,不是密碼
_TIMEOUT_SECONDS = 10.0


class _TimeoutRequest(GoogleTransportRequest):
    """抓 Google 公鑰時套 10 秒 timeout(預設 120 秒會卡住 worker);逾時會變成 TransportError → 登入失敗。"""

    def __call__(self, url, method="GET", body=None, headers=None, timeout=_TIMEOUT_SECONDS, **kwargs):
        return super().__call__(url, method, body, headers, timeout, **kwargs)


@dataclass(frozen=True)
class GoogleIdentity:
    email: str
    email_verified: bool
    hosted_domain: str | None
    name: str | None


class GoogleOAuthClient:
    def __init__(self, client_id: str, client_secret: str, hosted_domain: str = "") -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.hosted_domain = hosted_domain

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def authorization_url(self, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }
        if self.hosted_domain:
            # 只是讓 Google 帳號選單預選網域;真正的檢查在 service 比對 ID token 的 hd
            params["hd"] = self.hosted_domain
        return f"{_AUTH_URL}?{urlencode(params)}"

    def fetch_identity(self, code: str, redirect_uri: str) -> GoogleIdentity:
        """用授權碼換 ID token 並驗簽(簽章、aud、iss、到期)。失敗一律 raise ExternalAPIException。"""
        try:
            resp = self._exchange_code(code, redirect_uri)
            claims = id_token.verify_oauth2_token(resp["id_token"], _TimeoutRequest(), audience=self.client_id)
            return GoogleIdentity(
                email=claims["email"],
                email_verified=claims.get("email_verified") is True,
                hosted_domain=claims.get("hd"),
                name=claims.get("name"),
            )
        # ValueError 含驗簽失敗與 JSON 解析失敗;GoogleAuthError 是抓 Google 公鑰失敗;KeyError 是回應缺欄位。
        except (httpx.HTTPStatusError, ValueError, GoogleAuthError, KeyError) as e:
            # 只記例外類別:驗簽錯誤訊息可能夾帶 token 內容,授權碼也不能進 log。
            logger.warning(f"[External] Google OAuth exchange failed - error_type: {type(e).__name__}")
            raise ExternalAPIException("Google 登入驗證失敗") from e

    # 授權碼只能用一次:只重試連線層錯誤(請求可能根本沒送到),HTTP 4xx 不重試
    @retry_external("Google OAuth", retry_on=(httpx.TransportError,), attempts=2, max_seconds=15)
    def _exchange_code(self, code: str, redirect_uri: str) -> dict:
        logger.info("[External] Google OAuth exchanging code")
        resp = httpx.post(
            _TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": redirect_uri,
            },
            timeout=_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp.json()
