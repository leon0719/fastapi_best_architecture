import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

import sentry_sdk
from loguru import logger
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.loguru import LoguruIntegration
from sentry_sdk.types import Event, Hint
from sentry_sdk.utils import BadDsn

from app.common.core.config import config
from app.common.core.request_context import get_request_id

_configured = False


def _add_request_id(record: Any) -> None:
    """loguru patcher:每一行都帶上目前請求的 request ID(請求外,例如排程,是 "-")。"""
    record["extra"]["request_id"] = get_request_id() or "-"


def setup_logging() -> None:
    """Configure loguru handlers and silence noisy stdlib loggers.

    Idempotent: calling more than once has no effect.
    """
    global _configured
    if _configured:
        return
    _configured = True

    # Remove default handler
    logger.remove()
    logger.configure(patcher=_add_request_id)

    # Force color output in Docker (works with docker compose logs)
    os.environ.setdefault("COLORTERM", "truecolor")
    os.environ.setdefault("TERM", "xterm-256color")

    # Disable SQLAlchemy SQL query logging (we use loguru for application logs)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

    # Disable Uvicorn access logs (we have RequestLoggingMiddleware)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)

    # diagnose 會把 traceback 每一層的區域變數值印出來(token、金鑰都可能在裡面),正式環境必須關掉。
    debug = config.debug

    # Console output with colors (always colorize in Docker)
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
            "<magenta>{extra[request_id]}</magenta> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        ),
        level="DEBUG",
        colorize=True,
        backtrace=debug,
        diagnose=debug,
    )

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    file_format = (
        "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[request_id]} | {name}:{function}:{line} - {message}"
    )

    # File handler - all logs with rotation
    logger.add(
        logs_dir / "app.log",
        rotation="10 MB",
        retention=10,  # keep last 10 rotated files ("10 files" is not a valid loguru duration)
        compression="zip",
        level="INFO",
        format=file_format,
        enqueue=True,
        backtrace=debug,
        diagnose=debug,
    )

    # Separate error log file
    logger.add(
        logs_dir / "error.log",
        rotation="10 MB",
        retention=10,
        compression="zip",
        level="ERROR",
        format=file_format,
        backtrace=debug,
        diagnose=debug,
        enqueue=True,
    )


# ===================
# Sentry
# ===================

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_BEARER = re.compile(r"(?i)bearer\s+[\w.~+/=-]+")
_SENTRY_TEXT_MAX = 300


def _scrub_text(text: str) -> str:
    """只留第一行,遮掉 email 與 bearer token。

    機密常藏在後面幾行:DB 例外的 DETAIL 行(Key (email)=(…))與 [SQL: …]、pydantic 的 input_value、
    loguru 接在訊息後面的例外文字。第一行足以看出是什麼錯,位置由堆疊提供。
    """
    lines = text.strip().splitlines()
    first = lines[0] if lines else ""
    return _BEARER.sub("Bearer [token]", _EMAIL.sub("[email]", first))[:_SENTRY_TEXT_MAX]


def _scrub_event(event: Event, _hint: Hint) -> Event | None:
    """送出前的最後一道:不管訊息從哪條路徑進來,都只留第一行並遮掉機密;附上 request ID 方便對 log。"""
    for exception in (event.get("exception") or {}).get("values") or []:
        if isinstance(exception.get("value"), str):
            exception["value"] = _scrub_text(exception["value"])
    if logentry := event.get("logentry"):
        # message 與 formatted 是同一句話的兩份;params 是 log 的參數值,一併拿掉
        event["logentry"] = {
            key: _scrub_text(value) if isinstance(value, str) else value
            for key, value in logentry.items()
            if key != "params"
        }
    if isinstance(event.get("message"), str):
        event["message"] = _scrub_text(event["message"])
    if request := event.get("request"):
        # Authorization、Cookie 等 header 與 query string 可能含 token,一律不送
        request.pop("headers", None)
        request.pop("cookies", None)
        request.pop("query_string", None)
        request.pop("data", None)
    if request_id := get_request_id():
        event.setdefault("tags", {})["request_id"] = request_id
    return event


def _message_only(record: object) -> str:
    """loguru 事件格式。用函式而不是字串:字串格式會被 loguru 自動接上 {exception},
    在 diagnose=True 時那段文字會印出出錯那一行的變數值,繞過 include_local_variables=False。"""
    return "{message}"


def setup_sentry() -> None:
    """有設 SENTRY_DSN 才啟用。要在 setup_logging() 之後呼叫:
    Sentry 的 loguru 整合是加一個 handler,先加會被 setup_logging 的 logger.remove() 清掉。

    logger.error / logger.exception 會成為 Sentry 事件,所以 500、排程失敗、寄信失敗都看得到,
    不需要另外呼叫 capture_exception。
    """
    if not config.sentry_dsn:
        return
    try:
        sentry_sdk.init(
            dsn=config.sentry_dsn,
            environment=config.env,
            traces_sample_rate=config.sentry_traces_sample_rate,
            # 只送「哪裡壞了」:例外類型、訊息第一行、堆疊(不含變數)、請求的方法與路徑
            send_default_pii=False,
            max_request_body_size="never",
            include_local_variables=False,
            # breadcrumb 是 INFO 以上的每一行 log,內容無法逐一把關,整個不送
            max_breadcrumbs=0,
            integrations=[
                LoguruIntegration(level=None, sentry_logs_level=None, event_format=_message_only),
                # stdlib logging 是套件在用的(例如 sqladmin 表單錯誤含使用者輸入),不當成事件
                LoggingIntegration(level=None, event_level=None, sentry_logs_level=None),
            ],
            before_send=_scrub_event,
        )
    except BadDsn as e:  # DSN 打錯只是收不到錯誤回報,不能讓服務在 import 時就起不來
        logger.error(f"[Startup] SENTRY_DSN 格式不正確,錯誤回報未啟用 - error: {e}")
