"""Global error handling: every error leaves the API as BaseResponse.

{"data": null, "error": {"code": <HTTP status>, "message": "...", "reason": "<ErrorCode>" | null}}
"""

from collections.abc import Mapping

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.common.core.request_context import REQUEST_ID_HEADER, get_request_id
from app.common.exceptions import AppException, ErrorCode
from app.common.schemas import BaseResponse, ErrorResponse


def _error_response(
    status_code: int, message: str, reason: ErrorCode | None = None, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    body = BaseResponse[None](error=ErrorResponse(code=status_code, message=message, reason=reason))
    return JSONResponse(status_code=status_code, content=body.model_dump(), headers=headers)


def setup_exception_handlers(app: FastAPI) -> None:
    """
    Setup global exception handlers for the FastAPI application.

    Args:
        app: FastAPI application instance

    Note:
        The functions defined inside are registered as exception handlers
        and are called by FastAPI framework, not directly by our code.
    """

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        """Business errors raised by services. 4xx → warning, 5xx → error."""
        log = logger.warning if exc.status_code < 500 else logger.error
        log(f"[Error] {exc.status_code} {exc.message} - path: {request.url.path}")
        return _error_response(exc.status_code, exc.message, exc.reason)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Request body/query validation failures (422). Only field + reason, never the submitted value."""
        message = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'][1:]) or err['loc'][0]}: {err['msg']}" for err in exc.errors()
        )
        logger.warning(f"[Error] 422 validation failed - path: {request.url.path}, errors: {message}")
        return _error_response(status.HTTP_422_UNPROCESSABLE_CONTENT, message, ErrorCode.VALIDATION_ERROR)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Framework-level HTTP errors: unknown route (404), wrong method (405), etc."""
        logger.warning(f"[Error] {exc.status_code} {exc.detail} - path: {request.url.path}")
        reason = ErrorCode.NOT_FOUND if exc.status_code == status.HTTP_404_NOT_FOUND else None
        return _error_response(exc.status_code, str(exc.detail), reason, headers=exc.headers)

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        """slowapi 超過速率 → 429 BaseResponse(不回傳限制細節以外的資訊)。"""
        logger.warning(f"[Error] 429 rate limited - path: {request.url.path}, limit: {exc.detail}")
        return _error_response(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests, please try again later", ErrorCode.RATE_LIMITED
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Unexpected exceptions: log the stack trace, never leak details to the client.

        這個 handler 跑在所有 middleware 外層(Starlette 的 ServerErrorMiddleware),回應不會經過
        RequestLoggingMiddleware,所以 X-Request-ID 在這裡補上,使用者回報 500 時才有 ID 可查。
        """
        logger.exception(f"[Error] 500 unexpected error - path: {request.url.path}, error: {exc}")
        request_id = get_request_id()
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal server error",
            ErrorCode.INTERNAL_ERROR,
            headers={REQUEST_ID_HEADER: request_id} if request_id else None,
        )
