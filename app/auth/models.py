"""登入 token ORM model。"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.database import Base
from app.users.models import User


class TokenKind(StrEnum):
    LOGIN = "login"  # Google 登入後發的一次性登入碼(60 秒),只能換一次 session
    SESSION = "session"  # 前端 Authorization: Bearer 帶的 opaque token


class AuthToken(Base):
    """登入碼與 session token。原始值只交給使用者一次,DB 只存 sha256 digest。"""

    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    # 登入碼綁定發起登入的瀏覽器(PKCE S256):base64url(sha256(verifier)),只有 kind=login 會填
    challenge: Mapped[str | None] = mapped_column(String(43))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship()

    def __str__(self) -> str:
        return f"{self.kind} #{self.id}"
