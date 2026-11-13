"""通知 outbox ORM model。"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db.database import Base


class Channel(StrEnum):
    EMAIL = "email"
    LINE = "line"


class OutboxNotification(Base):
    """待送/已送的通知。業務層只寫這張表(跟業務資料同一交易),實際寄送由排程負責、失敗重送。

    狀態:sent_at 有值 = 已送達;abandoned_at 有值 = 重試超過上限放棄;兩者皆空 = 待送。
    """

    __tablename__ = "outbox_notifications"
    # 排程每輪查「待送且到期」的那幾筆
    __table_args__ = (Index("ix_outbox_notifications_pending", "sent_at", "abandoned_at", "next_attempt_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    recipient: Mapped[str] = mapped_column(String(500), nullable=False)  # 顯示/查詢用;實際收件人在 payload
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    retry_count: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    abandoned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __str__(self) -> str:
        return f"{self.channel} → {self.recipient}"
