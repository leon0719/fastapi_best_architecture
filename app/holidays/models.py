"""台灣行事曆例外日 ORM model。"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db.database import Base


class Holiday(Base):
    """只存「和平常不一樣」的日子:平日放假(國定假日、颱風假、公司休假)與週末補班。

    沒有列在這裡的日子:週一到週五上班、週六日休息。
    """

    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    # True:這天放假;False:這天補班(通常是週六)
    is_holiday: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __str__(self) -> str:
        return f"{self.day} {self.name}"
