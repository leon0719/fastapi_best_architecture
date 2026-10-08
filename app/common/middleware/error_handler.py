"""Global error handling: every error leaves the API as BaseResponse.

{"data": null, "error": {"code": <HTTP status>, "message": "..."}}
"""

from collections.abc import Mapping

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.common.exceptions import AppException
from app.common.schemas import BaseResponse, ErrorResponse


def _error_response(status_code: int, message: str, headers: Mapping[str, str] | None = None) -> JSONResponse:
    body = BaseResponse[None](error=ErrorResponse(code=status_code, message=message))
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
        return _error_response(exc.status_code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Request body/query validation failures (422). Only field + reason, never the submitted value."""
        message = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'][1:]) or err['loc'][0]}: {err['msg']}" for err in exc.errors()
        )
        logger.warning(f"[Error] 422 validation failed - path: {request.url.path}, errors: {message}")
        return _error_response(status.HTTP_422_UNPROCESSABLE_CONTENT, message)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Framework-level HTTP errors: unknown route (404), wrong method (405), etc."""
        logger.warning(f"[Error] {exc.status_code} {exc.detail} - path: {request.url.path}")
        return _error_response(exc.status_code, str(exc.detail), headers=exc.headers)

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Unexpected exceptions: log the stack trace, never leak details to the client."""
        logger.exception(f"[Error] 500 unexpected error - path: {request.url.path}, error: {exc}")
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error")
