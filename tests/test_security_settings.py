"""設定安全驗證與 admin 登入的迴歸測試。

背景:2026-07 發現 .env / .env.local / .env.prod 連同一把共用的 ADMIN_SECRET_KEY
被 commit 進公開 repo,且 admin 帳密未設定時可用空白表單登入後台。
這些測試釘住修正後的行為。
"""

import asyncio
from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    from starlette.requests import Request

pytestmark = pytest.mark.unit


def _config(**overrides):
    from app.common.core.config import Config

    base = {
        "admin_secret_key": "a-perfectly-fine-secret-key-of-sufficient-length",
        "admin_username": "someone",
        "admin_password": "a-real-password",
        "db_password": "a-real-db-password",
        "redis_password": "a-real-redis-password",
    }
    return Config(**{**base, **overrides})


class TestSecurityIssues:
    def test_clean_config_has_no_issues(self):
        assert _config().security_issues() == []

    @pytest.mark.parametrize(
        "value",
        [
            "CHANGEME-generate-with-secrets-token-urlsafe-48",
            "your-super-secret-key-change-in-production",
            "",
        ],
    )
    def test_placeholder_secret_key_is_flagged(self, value):
        issues = _config(admin_secret_key=value).security_issues()
        assert any("ADMIN_SECRET_KEY" in i for i in issues)

    def test_short_secret_key_is_flagged(self):
        issues = _config(admin_secret_key="tooshort").security_issues()
        assert any("字元" in i for i in issues)

    @pytest.mark.parametrize("value", ["admin123", "postgres", "password", ""])
    def test_weak_admin_password_is_flagged(self, value):
        issues = _config(admin_password=value).security_issues()
        assert any("ADMIN_PASSWORD" in i for i in issues)

    def test_dev_default_db_and_redis_passwords_are_flagged(self):
        issues = _config(db_password="postgres", redis_password="redis_password").security_issues()
        assert any("DB_PASSWORD" in i for i in issues)
        assert any("REDIS_PASSWORD" in i for i in issues)


class TestEnforceSecureSettings:
    def test_raises_when_not_debug(self):
        cfg = _config(debug=False, admin_password="admin123")
        with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
            cfg.enforce_secure_settings()

    def test_only_warns_when_debug(self):
        """本機開發不該被擋 —— 但仍要把問題回報給呼叫端印出來。"""
        cfg = _config(debug=True, admin_password="admin123")
        issues = cfg.enforce_secure_settings()
        assert any("ADMIN_PASSWORD" in i for i in issues)

    def test_passes_silently_when_secure(self):
        assert _config(debug=False).enforce_secure_settings() == []


class TestAdminLogin:
    """空帳密不得放行 —— 這是修正前真實存在的無密碼登入路徑。

    用 asyncio.run 直接驅動 coroutine,不引入 pytest-asyncio:整個專案只有這幾個
    async 測試,為此多一個外掛與 marker 設定並不划算。
    """

    def _try_login(self, monkeypatch, *, configured, submitted):
        from app.common.core import admin as admin_module

        monkeypatch.setattr(admin_module.config, "admin_username", configured[0])
        monkeypatch.setattr(admin_module.config, "admin_password", configured[1])

        class _Request:
            def __init__(self):
                self.session = {}

            async def form(self):
                return {"username": submitted[0], "password": submitted[1]}

        request = _Request()
        backend = admin_module.AdminAuth(secret_key="x" * 32)
        # login() 只用到 .form() 與 .session,不需要完整的 starlette Request。
        return asyncio.run(backend.login(cast("Request", request))), request

    def test_empty_credentials_are_rejected(self, monkeypatch):
        ok, request = self._try_login(monkeypatch, configured=("", ""), submitted=("", ""))
        assert ok is False
        assert request.session == {}

    def test_missing_form_fields_are_rejected(self, monkeypatch):
        ok, _ = self._try_login(monkeypatch, configured=("admin", "pw"), submitted=(None, None))
        assert ok is False

    def test_wrong_password_is_rejected(self, monkeypatch):
        ok, _ = self._try_login(monkeypatch, configured=("admin", "pw"), submitted=("admin", "nope"))
        assert ok is False

    def test_correct_credentials_are_accepted(self, monkeypatch):
        ok, request = self._try_login(monkeypatch, configured=("admin", "pw"), submitted=("admin", "pw"))
        assert ok is True
        assert request.session == {"token": "authenticated"}
