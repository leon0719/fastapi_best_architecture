"""Global error handling middleware."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from loguru import logger

from app.common.exceptions import AppException, ErrorCode


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
        """
        Handle custom application exceptions.

        Args:
            request: The incoming request
            exc: The application exception

        Returns:
            JSON response with error details
        """
        logger.error(f"Application error: {exc.message} | code: {exc.code} | Path: {request.url.path}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "error_code": exc.code, "path": str(request.url.path)},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(  # noqa: ARG001
        request: Request, exc: Exception
    ) -> JSONResponse:
        """
        Handle unexpected exceptions.

        Args:
            request: The incoming request
            exc: The exception

        Returns:
            JSON response with error details
        """
        logger.exception(f"Unexpected error: {str(exc)} | Path: {request.url.path}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal server error",
                "error_code": ErrorCode.INTERNAL_ERROR,
                "path": str(request.url.path),
            },
        )
