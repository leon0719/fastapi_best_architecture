import logging
import os
import sys
from pathlib import Path

from loguru import logger

_configured = False


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

    # Force color output in Docker (works with docker compose logs)
    os.environ.setdefault("COLORTERM", "truecolor")
    os.environ.setdefault("TERM", "xterm-256color")

    # Disable SQLAlchemy SQL query logging (we use loguru for application logs)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

    # Disable Uvicorn access logs (we have RequestLoggingMiddleware)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)

    # Console output with colors (always colorize in Docker)
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        ),
        level="DEBUG",
        colorize=True,
    )

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    # File handler - all logs with rotation
    logger.add(
        logs_dir / "app.log",
        rotation="10 MB",
        retention=10,  # keep last 10 rotated files ("10 files" is not a valid loguru duration)
        compression="zip",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        enqueue=True,
    )

    # Separate error log file
    logger.add(
        logs_dir / "error.log",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        backtrace=True,
        diagnose=True,
        enqueue=True,
    )


if __name__ == "__main__":
    setup_logging()
    logger.info("Hello, World!")
    logger.debug("Hello, World!")
    logger.warning("Hello, World!")
    logger.error("Hello, World!")
    logger.critical("Hello, World!")
