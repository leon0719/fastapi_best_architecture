from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.chatbots import views as chatbot_views
from app.chatbots.admin import ChatbotAdmin
from app.common.core.admin import setup_admin
from app.common.core.config import config
from app.common.core.log_config import setup_logging
from app.common.core.redis import close_redis, ping_redis
from app.common.db.database import engine
from app.common.middleware.error_handler import setup_exception_handlers
from app.common.middleware.request_logging import RequestLoggingMiddleware
from app.users import views as user_views
from app.users.admin import UserAdmin

# Configure logging before anything logs
setup_logging()

# 設定安全檢查要在建立 app 之前 —— SessionMiddleware 下面就要吃
# config.admin_secret_key,等到收第一個請求才發現金鑰是 placeholder 就太晚了。
# DEBUG=False 時直接 raise(服務起不來);本機開發只警告。
for _issue in config.enforce_secure_settings():
    logger.warning(f"[Startup] 設定安全警告(DEBUG=True 才容許): {_issue}")


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

    yield

    # Shutdown: Cleanup resources
    logger.info("[Shutdown] Closing Redis connections...")
    close_redis()
    logger.info("[Shutdown] Application shutdown complete")


app = FastAPI(
    title=config.app_name,
    description="FastAPI Best Architecture - Clean, scalable, and maintainable",
    version="1.0.0",
    lifespan=lifespan,
)

# Setup exception handlers
setup_exception_handlers(app)

# Add request logging middleware (logs all API calls with duration)
app.add_middleware(RequestLoggingMiddleware)

# Add session middleware for admin authentication
app.add_middleware(SessionMiddleware, secret_key=config.admin_secret_key)

# Setup admin panel
admin = setup_admin(app, engine)
admin.add_view(UserAdmin)
admin.add_view(ChatbotAdmin)

# Register API routes (New Django-style app structure)
app.include_router(user_views.router, prefix="/api/v1")
app.include_router(chatbot_views.router, prefix="/api/v1")


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
