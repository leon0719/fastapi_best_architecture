"""登入與授權的 FastAPI 依賴。其他 app 的 view 用 `current_user` 取得登入者、`require_role` 限制角色:

@router.get("/reports", dependencies=[Depends(require_role(Role.ADMIN))])
def list_reports(...): ...

def create_order(user: Annotated[User, Depends(current_user)], ...): ...
"""

from collections.abc import Callable
from functools import cache
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger
from sqlalchemy.orm import Session

from app.auth.external_services import GoogleOAuthClient
from app.auth.services import AuthService
from app.common.core.config import config
from app.common.db.database import get_db
from app.common.exceptions import ForbiddenException, UnauthorizedException
from app.users.models import Role, User

# auto_error=False:缺 header 時由我們 raise UnauthorizedException,回應才會是 BaseResponse 格式
_bearer = HTTPBearer(auto_error=False)


@cache
def get_google_client() -> GoogleOAuthClient:
    return GoogleOAuthClient(
        config.google_oauth_client_id, config.google_oauth_client_secret, config.google_allowed_domain
    )


def get_auth_service(
    db: Annotated[Session, Depends(get_db)], google: Annotated[GoogleOAuthClient, Depends(get_google_client)]
) -> AuthService:
    return AuthService(db, google)


def current_token(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> str:
    if credentials is None:
        raise UnauthorizedException("請先登入")
    return credentials.credentials


def current_user(
    request: Request,
    token: Annotated[str, Depends(current_token)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    user = service.authenticate(token)
    request.state.user_id = user.id  # RequestLoggingMiddleware 的 [API] log 會附上;只放 id
    return user


def require_role(*roles: Role) -> Callable[[User], User]:
    """登入且具備任一角色才放行(角色繼承見 users.models.ROLE_IMPLIES);否則 403。"""

    def dependency(user: Annotated[User, Depends(current_user)]) -> User:
        if not user.has_any_role(*roles):
            logger.warning(f"[Auth] Forbidden - user_id: {user.id}, role: {user.role}, required: {list(roles)}")
            raise ForbiddenException("權限不足")
        return user

    return dependency
