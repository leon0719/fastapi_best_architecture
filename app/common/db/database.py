"""Database configuration and session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.common.core.config import config

# Create engine (no check_same_thread for PostgreSQL)
engine = create_engine(
    config.db_url,
    pool_pre_ping=True,  # Enable connection health checks
    echo=False,  # Disable SQL query logging (use loguru for app logs)
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
