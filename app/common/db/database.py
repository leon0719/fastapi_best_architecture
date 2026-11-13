"""Database configuration and session management."""

from collections.abc import Callable

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.common.core.config import config

# Create engine (no check_same_thread for PostgreSQL)
engine = create_engine(
    config.db_url,
    pool_pre_ping=True,  # Enable connection health checks
    echo=False,  # Disable SQL query logging (use loguru for app logs)
    # 例外訊息不附 SQL 參數:參數可能含個資或 token,而例外訊息會進 log 與 Sentry
    hide_parameters=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


def get_db():
    """FastAPI dependency that yields a database session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session_factory() -> Callable[[], Session]:
    """背景工作(排程、BackgroundTasks、長任務)在請求之外跑,不能用請求的 session:用這個工廠自己開。

    測試以 monkeypatch 換掉模組變數 SessionLocal(這裡執行時才讀取,所以對所有呼叫端都生效)。
    """
    return SessionLocal
