"""抓政府行政機關辦公日曆。第三方呼叫只放這裡。"""

from typing import Any

import httpx
from loguru import logger

from app.common.core.retry import retry_external
from app.common.exceptions import ExternalAPIException

# 人事行政總處辦公日曆表的 JSON 整理版(github.com/ruyut/TaiwanCalendar),經 jsDelivr CDN;網址依年份固定。
# 官方 CSV 在政府資料開放平臺上每年換網址,沒辦法自動抓。
_CALENDAR_URL = "https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/{year}.json"


@retry_external("辦公日曆", retry_on=(httpx.TransportError,))
def fetch_taiwan_calendar(year: int) -> list[dict[str, Any]]:
    """整年每一天一筆:{"date": "YYYYMMDD", "week": "五", "isHoliday": bool, "description": str}。"""
    url = _CALENDAR_URL.format(year=year)
    logger.info(f"[External] Fetching Taiwan calendar - year: {year}")
    try:
        response = httpx.get(url, timeout=30)
        response.raise_for_status()
        days = response.json()
    except (httpx.HTTPStatusError, ValueError) as e:
        logger.warning(f"[External] Failed to fetch calendar - year: {year}, error_type: {type(e).__name__}")
        raise ExternalAPIException(f"抓不到 {year} 年的辦公日曆(該年度可能尚未公告)") from e
    if not isinstance(days, list) or not days or not {"date", "isHoliday"} <= days[0].keys():
        logger.warning(f"[External] Unexpected calendar format - year: {year}")
        raise ExternalAPIException(f"{year} 年辦公日曆的格式不符預期")
    return days
