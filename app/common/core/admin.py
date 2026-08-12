"""FastAPI Admin configuration using SQLAdmin."""

import secrets

from sqladmin import Admin
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from app.common.core.config import config


class AdminAuth(AuthenticationBackend):
    """Simple authentication backend for admin panel."""

    async def login(self, request: Request) -> bool:
        """Handle login request."""
        form = await request.form()
        username = form.get("username")
        password = form.get("password")

        # 帳密未設定時一律拒絕。少了這道,admin_username/admin_password 的預設值
        # 空字串會讓「送出空白表單」== 設定值而通過驗證(無密碼登入後台)。
        if not config.admin_username or not config.admin_password:
            return False

        # compare_digest 避免以字元比對耗時反推帳密;str 型別檢查是因為
        # form.get() 對檔案欄位會回傳 UploadFile,對缺欄位回傳 None。
        if not isinstance(username, str) or not isinstance(password, str):
            return False

        user_ok = secrets.compare_digest(username, config.admin_username)
        pass_ok = secrets.compare_digest(password, config.admin_password)
        if user_ok and pass_ok:
            request.session.update({"token": "authenticated"})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        """Handle logout request."""
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        """Check if user is authenticated."""
        token = request.session.get("token")
        return token == "authenticated"


def setup_admin(app, engine):
    """Initialize and configure SQLAdmin."""
    authentication_backend = AdminAuth(secret_key=config.admin_secret_key)

    admin = Admin(
        app,
        engine,
        title=f"{config.app_name} - Admin Panel",
        authentication_backend=authentication_backend,
    )

    return admin
