"""測試用的假 Google OAuth client:不連網,回傳預先設定的身分或錯誤。"""

from app.auth.external_services import GoogleIdentity
from app.common.exceptions import ExternalAPIException


class FakeGoogle:
    configured = True

    def __init__(self, identity: GoogleIdentity | None = None, fail: bool = False) -> None:
        self.identity = identity or GoogleIdentity(
            email="Alice@Example.com", email_verified=True, hosted_domain="example.com", name="Alice"
        )
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def authorization_url(self, redirect_uri: str, state: str) -> str:
        return f"https://accounts.google.test/auth?state={state}&redirect_uri={redirect_uri}"

    def fetch_identity(self, code: str, redirect_uri: str) -> GoogleIdentity:
        self.calls.append((code, redirect_uri))
        if self.fail:
            raise ExternalAPIException("Google 登入驗證失敗")
        return self.identity
