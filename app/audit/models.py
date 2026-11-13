"""稽核軌跡 ORM model。"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db.database import Base


class AuditSource(StrEnum):
    ADMIN = "admin"  # SQLAdmin 後台(AdminAuditMixin 自動寫)
    API = "api"  # 業務層(service 呼叫 record_audit)
    SYSTEM = "system"  # 排程、腳本


class AuditLog(Base):
    """誰、在什麼時候、從哪裡、對哪一筆資料、改了哪些欄位。

    這張表任何進得了後台的人都看得到,所以機密欄位只記「有變更」不記值(見 audit.utils.diff)。
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # created_at 有 index:保留期清理以它刪除,列表也以它排序
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    # 誰做的:後台是共用帳密,記 "admin";API 記 "user:<id>";排程記任務名稱
    actor: Mapped[str | None] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # create / update / delete / 自訂動作
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 被改的資料種類,例如 User
    target_id: Mapped[str | None] = mapped_column(String(100))
    # 被改那一筆當下的名稱;改名、刪除後軌跡仍看得出是誰
    target_label: Mapped[str | None] = mapped_column(String(200))
    # {欄位: [舊值, 新值]},只放有變的欄位;create 的舊值與 delete 的新值是 null
    changes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    ip: Mapped[str | None] = mapped_column(String(45))
    request_id: Mapped[str | None] = mapped_column(String(64))

    def __str__(self) -> str:
        return f"{self.action} {self.target_type} #{self.target_id}"
