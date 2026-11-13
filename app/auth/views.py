"""登入端點:Google 導轉、登入碼換 token、目前使用者、登出。

前端流程:
1. 產生 PKCE verifier,整頁導到 GET /api/v1/auth/google/login?challenge=<S256(verifier)>
2. Google 導回 callback 後,後端導回 {FRONTEND_BASE_URL}/login/callback?code=<一次性登入碼>
3. 前端 POST /api/v1/auth/exchange {code, verifier} 換 session token,之後以 Authorization: Bearer 帶上
"""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.auth.dependencies import current_token, current_user, get_auth_service, get_google_client
from app.auth.external_services import GoogleOAuthClient
from app.auth.schemas import ExchangeRequest, MeRead, TokenRead
from app.auth.services import AuthService, is_valid_challenge, login_error_url
from app.common.core.rate_limit import auth_rate, limiter
from app.common.schemas import BaseResponse
from app.users.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/google/login", name="google_login")
@limiter.limit(auth_rate)
def google_login(
    request: Request,
    google: Annotated[GoogleOAuthClient, Depends(get_google_client)],
    challenge: str | None = None,
) -> RedirectResponse:
    """整頁導轉,不能回 422 JSON:未設定或 challenge 不合格就導回前端登入頁。"""
    if not google.configured:
        return RedirectResponse(login_error_url("not_configured"), status_code=302)
    if not is_valid_challenge(challenge):
        return RedirectResponse(login_error_url("auth_failed"), status_code=302)
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    request.session["oauth_challenge"] = challenge
    return RedirectResponse(google.authorization_url(str(request.url_for("google_callback")), state), status_code=302)


@router.get("/google/callback", name="google_callback")
@limiter.limit(auth_rate)
def google_callback(
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
    code: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    # state、challenge 都只能用一次
    expected = request.session.pop("oauth_state", None)
    challenge = request.session.pop("oauth_challenge", None)
    target = service.finish_google_login(code, state, expected, challenge, str(request.url_for("google_callback")))
    return RedirectResponse(target, status_code=302)


@router.post("/exchange", response_model=BaseResponse[TokenRead])
@limiter.limit(auth_rate)
def exchange(request: Request, body: ExchangeRequest, service: Annotated[AuthService, Depends(get_auth_service)]):
    return BaseResponse(data=TokenRead(token=service.exchange(body.code, body.verifier)))


@router.get("/me", response_model=BaseResponse[MeRead])
def me(user: Annotated[User, Depends(current_user)]):
    return BaseResponse(data=MeRead.model_validate(user))


@router.post("/logout", response_model=BaseResponse[None])
def logout(token: Annotated[str, Depends(current_token)], service: Annotated[AuthService, Depends(get_auth_service)]):
    service.logout(token)
    return BaseResponse()
