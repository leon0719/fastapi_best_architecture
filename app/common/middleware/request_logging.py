"""Request logging middleware: request ID + one [API] line per request."""

import time

from fastapi import Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from app.common.core.request_context import REQUEST_ID_HEADER, set_request_id


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Assign a request ID and log every API request with duration.

    - 接收上游(nginx/前端)送來的 X-Request-ID,沒有或不合法就產生一個;存進 contextvar,
      loguru 每一行與 Sentry 事件都會帶上,並回寫到回應 header。
    - 每個請求一行 [API] log:method、path、status、duration;`current_user` 驗證成功時
      會把 user_id 放進 request.state,這裡一起記(只記 id,不記 email 或姓名)。

    Example log output:
        [API] POST /api/v1/users - status: 201, duration: 0.245s, user_id: 5
        [API] GET /api/v1/users - status: 200, duration: 0.032s
    """

    # Paths to skip logging (health checks, docs, admin, static files)
    SKIP_PATHS = {"/health/live", "/health/ready", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(self, request: Request, call_next):
        request_id = set_request_id(request.headers.get(REQUEST_ID_HEADER))

        if request.url.path in self.SKIP_PATHS or request.url.path.startswith("/admin"):
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id
            return response

        start_time = time.perf_counter()
        status_code = 500  # call_next 拋出例外時(交給最外層的 500 handler),log 照樣記一行
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration = time.perf_counter() - start_time
            user_id = getattr(request.state, "user_id", None)
            who = f", user_id: {user_id}" if user_id is not None else ""
            logger.info(
                f"[API] {request.method} {request.url.path} - status: {status_code}, duration: {duration:.3f}s{who}"
            )
