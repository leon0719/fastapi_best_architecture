"""User ORM models."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db.database import Base


class User(Base):
    """User database model."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, index=True, nullable=False)
