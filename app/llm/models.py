"""LLM 用量 ORM model。"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db.database import Base


class LlmUsage(Base):
    """一次成功的 LLM 呼叫用了多少 token、花多少錢(`make llm-cost` 按月統計)。

    費用用寫入當下的單價算好存起來(單價表沒有的模型留 NULL),之後調價不會改到舊資料。
    """

    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    feature: Mapped[str | None] = mapped_column(String(50))  # 哪個功能呼叫的,成本歸屬用
    input_tokens: Mapped[int] = mapped_column(nullable=False)  # 含 cached_tokens
    cached_tokens: Mapped[int] = mapped_column(default=0, nullable=False)  # input 裡吃到快取(較便宜)的部分
    output_tokens: Mapped[int] = mapped_column(nullable=False)  # 含 thinking token(同樣按輸出價計費)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int | None] = mapped_column()

    def __str__(self) -> str:
        return f"{self.provider}/{self.model} #{self.id}"
