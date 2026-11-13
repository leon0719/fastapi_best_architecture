from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.audit.admin import AuditLogAdmin
from app.audit.tasks import AuditRetentionTask
from app.auth import views as auth_views
from app.auth.admin import AuthTokenAdmin
from app.auth.tasks import ExpiredTokenCleanupTask
from app.chatbots import views as chatbot_views
from app.chatbots.admin import ChatbotAdmin
from app.common.core.admin import setup_admin
from app.common.core.config import config
from app.common.core.log_config import setup_logging, setup_sentry
from app.common.core.rate_limit import limiter
from app.common.core.redis import close_redis, ping_redis
from app.common.core.request_context import REQUEST_ID_HEADER
from app.common.db.database import engine
from app.common.middleware.error_handler import setup_exception_handlers
from app.common.middleware.request_logging import RequestLoggingMiddleware
from app.holidays.admin import HolidayAdmin
from app.jobs import views as job_views
from app.jobs.scheduler import Scheduler
from app.llm.admin import LlmUsageAdmin
from app.notifications import views as notification_views
from app.notifications.admin import OutboxNotificationAdmin
from app.notifications.tasks import OutboxDispatchTask, OutboxRetentionTask
from app.users import views as user_views
from app.users.admin import UserAdmin

# Configure logging before anything logs; Sentry 的 loguru handler 要加在 setup_logging() 之後
setup_logging()
setup_sentry()

# 設定安全檢查要在建立 app 之前 —— SessionMiddleware 下面就要吃
# config.admin_secret_key,等到收第一個請求才發現金鑰是 placeholder 就太晚了。
# DEBUG=False 時直接 raise(服務起不來);本機開發只警告。
for _issue in config.enforce_secure_settings():
    logger.warning(f"[Startup] 設定安全警告(DEBUG=True 才容許): {_issue}")

# 週期任務:每個 worker 都會跑排程迴圈,實際執行由 Redis 鎖保證全叢集一輪只跑一次(app/jobs/scheduler.py)
scheduler = Scheduler([OutboxDispatchTask(), OutboxRetentionTask(), AuditRetentionTask(), ExpiredTokenCleanupTask()])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.

    Handles startup and shutdown events for the application.
    """
    # Schema is managed by Alembic — run `uv run alembic upgrade head` to migrate.
    logger.info("[Startup] Starting application (schema managed by Alembic)")

    # Startup: Check Redis connection
    logger.info("[Startup] Checking Redis connection...")
    try:
        if ping_redis():
            logger.info("[Startup] Redis connection successful")
        else:
            logger.warning("[Startup] Redis connection failed - cache will be disabled")
    except Exception as e:
        logger.exception(f"[Startup] Redis health check error - error: {e}")

    if config.scheduler_enabled:
        await scheduler.start()

    yield

    # Shutdown(SIGTERM → uvicorn 等進行中的請求結束,最多 --timeout-graceful-shutdown 秒,再跑到這裡)
    await scheduler.stop()
    logger.info("[Shutdown] Closing Redis connections...")
    close_redis()
    logger.info("[Shutdown] Application shutdown complete")


def api_docs_kwargs(debug: bool) -> dict[str, str | None]:
    """正式環境(DEBUG=False)關閉 /docs、/redoc、/openapi.json:不對外公開 API 清單,本機開發保留。"""
    if debug:
        return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}
    return {"docs_url": None, "redoc_url": None, "openapi_url": None}


_docs = api_docs_kwargs(config.debug)
app = FastAPI(
    title=config.app_name,
    description="FastAPI Best Architecture - Clean, scalable, and maintainable",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=_docs["docs_url"],
    redoc_url=_docs["redoc_url"],
    openapi_url=_docs["openapi_url"],
)
app.state.limiter = limiter
app.state.scheduler = scheduler

# Setup exception handlers
setup_exception_handlers(app)

# Request ID + request logging (logs all API calls with duration and user_id)
app.add_middleware(RequestLoggingMiddleware)

# Session cookie:admin 登入、Google 登入的 state/PKCE challenge。正式環境只走 https。
app.add_middleware(SessionMiddleware, secret_key=config.admin_secret_key, https_only=not config.debug)

# 最後加 = 最外層:preflight 與錯誤回應都會帶上 CORS header。
# 前端用 Authorization: Bearer 帶 token(不靠 cookie),所以不開 allow_credentials。
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
    # 跨 origin 的前端要讀下載檔名與 request ID(回報問題用)
    expose_headers=["Content-Disposition", REQUEST_ID_HEADER],
)

# Setup admin panel
admin = setup_admin(app, engine)
admin.add_view(UserAdmin)
admin.add_view(AuthTokenAdmin)
admin.add_view(ChatbotAdmin)
admin.add_view(HolidayAdmin)
admin.add_view(OutboxNotificationAdmin)
admin.add_view(LlmUsageAdmin)
admin.add_view(AuditLogAdmin)

# Register API routes (New Django-style app structure)
app.include_router(auth_views.router, prefix="/api/v1")
app.include_router(user_views.router, prefix="/api/v1")
app.include_router(chatbot_views.router, prefix="/api/v1")
app.include_router(job_views.router, prefix="/api/v1")
app.include_router(job_views.scheduler_router, prefix="/api/v1")
app.include_router(notification_views.router, prefix="/api/v1")


@app.get("/health/live")
def health_live():
    """
    Liveness probe — only proves the process is up, never checks dependencies.

    A transient DB/Redis blip must not fail liveness: restarting this container
    won't make the dependency recover faster, and a mass restart under load can
    trigger a cascading outage. Use /health/ready to gate traffic on dependencies.
    """
    return {"status": "alive"}


@app.get("/health/ready")
def health_ready():
    """
    Readiness probe — checks dependencies this instance needs to actually serve traffic.

    Returns:
        200 with per-dependency status if all required dependencies are reachable,
        503 otherwise (used by load balancers/orchestrators to gate traffic).
    """
    checks = {}

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as e:
        logger.warning(f"[Health] DB readiness check failed - error: {e}")
        checks["db"] = "unreachable"

    checks["redis"] = "ok" if ping_redis() else "unreachable"

    all_ok = all(status == "ok" for status in checks.values())
    return JSONResponse(
        status_code=status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ready" if all_ok else "not_ready", "checks": checks},
    )


def add_debug_routes(app: FastAPI, debug: bool) -> None:
    """只在本機(DEBUG=True)註冊的路由。正式環境不存在:沒有登入保護。"""
    if not debug:
        return

    @app.get("/debug/sentry")
    def debug_sentry():
        """驗證 Sentry 收不收得到:故意丟例外,走和真實 500 一樣的路徑(error handler → logger.exception → Sentry)。

        要先在 .env.local 設 SENTRY_DSN 並重啟;沒設的話只會回 500,不會送出任何東西。
        """
        raise RuntimeError("Sentry 測試事件(/debug/sentry)")

    if config.storage_backend == "local":
        # LocalStorage.presigned_url() 回傳 /media/<key>;正式環境請用 S3
        media = Path(config.storage_local_dir)
        media.mkdir(parents=True, exist_ok=True)
        app.mount("/media", StaticFiles(directory=media), name="media")


add_debug_routes(app, config.debug)
