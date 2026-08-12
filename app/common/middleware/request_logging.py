"""Request logging middleware for automatic API call tracking."""

import time

from fastapi import Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to automatically log all API requests with duration.

    Logs the following information for each request:
    - HTTP method (GET, POST, PUT, DELETE, etc.)
    - Request path
    - Response status code
    - Request duration in seconds
    - Client IP address (optional, for security-critical endpoints)

    Example log output:
        [API] POST /api/v1/users - status: 201, duration: 0.245s
        [API] GET /api/v1/users - status: 200, duration: 0.032s
        [API] DELETE /api/v1/users/1 - status: 404, duration: 0.018s
    """

    # Paths to skip logging (health checks, docs, admin, static files)
    SKIP_PATHS = {"/health/live", "/health/ready", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(self, request: Request, call_next):
        """
        Process the request and log details.

        Args:
            request: The incoming HTTP request
            call_next: The next middleware or route handler

        Returns:
            Response from the next handler
        """
        # Skip logging for certain paths
        if request.url.path in self.SKIP_PATHS or request.url.path.startswith("/admin"):
            return await call_next(request)

        # Record start time
        start_time = time.time()

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration = time.time() - start_time

        # Log request details
        logger.info(
            f"[API] {request.method} {request.url.path} - status: {response.status_code}, duration: {duration:.3f}s"
        )

        return response
