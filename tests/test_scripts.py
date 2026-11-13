"""營運腳本:匯入假日(外部資料以 monkeypatch 取代,不連網)、壓測帳號 seed。"""

import pytest

from app.common.core.config import config
from app.holidays.models import Holiday
from app.users.models import User

pytestmark = pytest.mark.unit


def test_import_holidays(session_factory, db_session, monkeypatch, capsys):
    from scripts import import_holidays

    calendar = [{"date": "20270101", "isHoliday": True, "description": "開國紀念日"}]
    monkeypatch.setattr(import_holidays, "fetch_taiwan_calendar", lambda year: calendar)

    assert import_holidays.main(["2027"]) == 0
    assert db_session.query(Holiday).count() == 1
    assert "新增 1 筆" in capsys.readouterr().out
    assert import_holidays.main(["abc"]) == 2


def test_seed_perf_is_idempotent(session_factory, db_session):
    from scripts.seed_perf import seed

    first = seed(2)
    second = seed(2)

    assert [a["role"] for a in first] == ["admin", "user"]
    assert db_session.query(User).count() == 2
    assert first[0]["token"] != second[0]["token"]


def test_seed_perf_refuses_without_debug(monkeypatch):
    from scripts.seed_perf import main

    monkeypatch.setattr(config, "debug", False)

    assert main(["1"]) == 1
