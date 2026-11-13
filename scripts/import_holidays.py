"""抓整年的政府行政機關辦公日曆,匯入行事曆例外日(平日放假、週末補班)。

用法(開發環境):   make import-holidays YEAR=2027
用法(容器內):     python -m scripts.import_holidays 2027
資料來源見 app/holidays/external_services.py。可重複執行:日期已存在的略過、不覆寫(後台手動改過的保留)。
颱風假等臨時異動請在後台 Holidays 手動新增。
"""

import sys

import app.main  # noqa: F401  # 載入所有 model,mapper 初始化時關聯才找得到
from app.common.db.database import get_session_factory
from app.holidays.external_services import fetch_taiwan_calendar
from app.holidays.services import HolidayService


def main(argv: list[str]) -> int:
    if len(argv) != 1 or not argv[0].isdigit():
        print("用法: python -m scripts.import_holidays <西元年>", file=sys.stderr)  # noqa: T201  # CLI 輸出
        return 2
    days = fetch_taiwan_calendar(int(argv[0]))
    with get_session_factory()() as db:
        created, skipped = HolidayService(db).import_calendar(days)
    print(f"新增 {created} 筆,略過 {skipped} 筆")  # noqa: T201  # CLI 輸出
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
