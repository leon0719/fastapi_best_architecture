"""台灣工作日判斷與行事曆匯入。"""

from datetime import date

import httpx
import pytest

from app.common.exceptions import ExternalAPIException
from app.holidays import external_services
from app.holidays.models import Holiday
from app.holidays.services import HolidayService, is_working_day

pytestmark = pytest.mark.unit

CALENDAR = [
    {"date": "20260101", "week": "四", "isHoliday": True, "description": "開國紀念日"},
    {"date": "20260102", "week": "五", "isHoliday": False, "description": ""},
    {"date": "20260103", "week": "六", "isHoliday": True, "description": ""},
    {"date": "20260214", "week": "六", "isHoliday": False, "description": "補行上班"},
]


def test_default_week_without_records(db_session):
    assert is_working_day(db_session, date(2026, 1, 5))  # 週一
    assert not is_working_day(db_session, date(2026, 1, 10))  # 週六


def test_import_stores_only_exceptions(db_session):
    created, skipped = HolidayService(db_session).import_calendar(CALENDAR)

    assert (created, skipped) == (2, 0)
    assert {(h.day, h.is_holiday) for h in db_session.query(Holiday)} == {
        (date(2026, 1, 1), True),
        (date(2026, 2, 14), False),
    }
    assert not is_working_day(db_session, date(2026, 1, 1))
    assert is_working_day(db_session, date(2026, 2, 14))


def test_import_is_idempotent_and_keeps_manual_edits(db_session):
    db_session.add(Holiday(day=date(2026, 1, 1), name="手動", is_holiday=True))
    db_session.commit()

    assert HolidayService(db_session).import_calendar(CALENDAR) == (1, 1)
    assert db_session.query(Holiday).filter_by(day=date(2026, 1, 1)).one().name == "手動"


def test_fetch_calendar_validates_format(monkeypatch):
    request = httpx.Request("GET", "https://cdn.example")
    monkeypatch.setattr(
        external_services.httpx, "get", lambda *a, **k: httpx.Response(200, json=CALENDAR, request=request)
    )
    assert external_services.fetch_taiwan_calendar(2026) == CALENDAR

    monkeypatch.setattr(external_services.httpx, "get", lambda *a, **k: httpx.Response(200, json={}, request=request))
    with pytest.raises(ExternalAPIException):
        external_services.fetch_taiwan_calendar(2026)

    monkeypatch.setattr(external_services.httpx, "get", lambda *a, **k: httpx.Response(404, request=request))
    with pytest.raises(ExternalAPIException):
        external_services.fetch_taiwan_calendar(2099)
