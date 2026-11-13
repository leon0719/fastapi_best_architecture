"""User ORM models."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, String, func, true
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.common.db.database import Base


class Role(StrEnum):
    """使用者角色。新增角色:加一個成員,並在 ROLE_IMPLIES 寫它涵蓋哪些角色。

    DB 存字串(不是 Postgres enum),新增角色不需要 migration。
    """

    USER = "user"
    ADMIN = "admin"


# 角色 → 它同時具備的角色(含自己)。admin 能做 user 能做的事,require_role(Role.USER) 也放行 admin。
ROLE_IMPLIES: dict[Role, frozenset[Role]] = {
    Role.USER: frozenset({Role.USER}),
    Role.ADMIN: frozenset({Role.ADMIN, Role.USER}),
}


class User(Base):
    """User database model."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, index=True, nullable=False)
    # Google 登入以 email 對應帳號;nullable:既有資料與不需要登入的帳號沒有 email
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    role: Mapped[str] = mapped_column(String(20), default=Role.USER, server_default=Role.USER, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    @validates("email")
    def _normalise_email(self, _key: str, value: str | None) -> str | None:
        # 後台表單留空會送出空字串;unique 欄位不能有兩個 ""
        return value.strip().lower() or None if value else None

    @validates("role")
    def _validate_role(self, _key: str, value: str) -> str:
        return Role(value).value  # 不認得的角色在寫入前就 ValueError(後台表單會顯示錯誤)

    @property
    def roles(self) -> list[str]:
        """這個使用者具備的所有角色(前端 usePermission / RequireRole 用)。"""
        return sorted(ROLE_IMPLIES[Role(self.role)])

    def has_any_role(self, *roles: Role) -> bool:
        return bool(ROLE_IMPLIES[Role(self.role)] & set(roles))

    def __str__(self) -> str:
        return f"{self.name}（{self.email}）" if self.email else self.name
