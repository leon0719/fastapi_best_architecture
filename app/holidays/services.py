"""台灣工作日判斷與行事曆匯入。"""

from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.holidays.models import Holiday

_NAME_MAX = 50  # Holiday.name 的欄寬


def is_working_day(db: Session, day: date) -> bool:
    """這天要不要上班:有例外紀錄看紀錄(放假/補班),沒有就是週一到週五上班。"""
    is_holiday = db.scalar(select(Holiday.is_holiday).where(Holiday.day == day))
    if is_holiday is not None:
        return not is_holiday
    return day.weekday() < 5


class HolidayService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def import_calendar(self, days: Iterable[dict[str, Any]]) -> tuple[int, int]:
        """匯入辦公日曆(fetch_taiwan_calendar 的格式),回傳 (新增, 略過)。

        只存「例外日」:平日放假、週末上班。可重複執行:日期已存在的略過、不覆寫(後台手動改過的保留)。
        """
        created = skipped = 0
        existing = set(self.db.scalars(select(Holiday.day)))
        try:
            for row in days:
                day = datetime.strptime(row["date"], "%Y%m%d").date()  # noqa: DTZ007  # 純日期,沒有時區
                is_holiday = row["isHoliday"] is True
                is_weekend = day.weekday() >= 5
                if is_holiday == is_weekend:  # 週末放假、平日上班:和預設一樣,不用存
                    continue
                if day in existing:
                    skipped += 1
                    continue
                name = (row.get("description") or ("放假" if is_holiday else "補班"))[:_NAME_MAX]
                self.db.add(Holiday(day=day, name=name, is_holiday=is_holiday))
                existing.add(day)
                created += 1
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception("[Service] Failed to import calendar")
            raise
        logger.info(f"[Service] Calendar imported - created: {created}, skipped: {skipped}")
        return created, skipped
