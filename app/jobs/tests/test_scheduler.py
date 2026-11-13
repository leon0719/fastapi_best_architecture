"""Scheduler.tick:Redis 鎖、非工作日跳過、例外只寫 log 與 status。"""

import asyncio
from datetime import UTC, date, datetime
from typing import cast

import pytest
import redis

from app.holidays.models import Holiday
from app.jobs.scheduler import PeriodicTask, Scheduler

pytestmark = pytest.mark.unit

MONDAY_10AM_TAIPEI = datetime(2026, 1, 5, 2, 0, tzinfo=UTC)
SATURDAY = datetime(2026, 1, 10, 2, 0, tzinfo=UTC)


class CountingTask(PeriodicTask):
    name = "counting"
    interval_seconds = 3600

    def __init__(self, fail: bool = False) -> None:
        self.runs = 0
        self.fail = fail

    def run(self, db):
        self.runs += 1
        if self.fail:
            raise RuntimeError("boom")
        return f"run {self.runs}"


class WorkdayTask(CountingTask):
    name = "workday"
    skip_non_working_days = True


def _scheduler(task, fake_redis, session_factory, now=MONDAY_10AM_TAIPEI):
    return Scheduler([task], session_factory=session_factory, redis_client=lambda: fake_redis, now=lambda: now)


def test_lock_prevents_second_worker_from_running(fake_redis, session_factory):
    task = CountingTask()
    worker_a = _scheduler(task, fake_redis, session_factory)
    worker_b = _scheduler(task, fake_redis, session_factory)

    assert worker_a.tick(task) is True
    assert worker_b.tick(task) is False
    assert task.runs == 1
    assert 0 < fake_redis.ttl("scheduler:lock:counting") <= 3600


def test_status_records_last_run(fake_redis, session_factory):
    task = CountingTask()
    scheduler = _scheduler(task, fake_redis, session_factory)

    scheduler.tick(task)

    status = scheduler.status()[0]
    assert status["last_result"] == "run 1"
    assert status["last_error"] is None


def test_exception_is_logged_not_raised(fake_redis, session_factory):
    task = CountingTask(fail=True)
    scheduler = _scheduler(task, fake_redis, session_factory)

    assert scheduler.tick(task) is True
    assert scheduler.status()[0]["last_error"] == "RuntimeError"


def test_skips_weekend(fake_redis, session_factory):
    task = WorkdayTask()

    assert _scheduler(task, fake_redis, session_factory, now=SATURDAY).tick(task) is False
    assert task.runs == 0


def test_skips_holiday_and_runs_on_makeup_workday(fake_redis, session_factory, db_session):
    db_session.add_all(
        [
            Holiday(day=date(2026, 1, 5), name="放假", is_holiday=True),
            Holiday(day=date(2026, 1, 10), name="補班", is_holiday=False),
        ]
    )
    db_session.commit()
    task = WorkdayTask()

    assert _scheduler(task, fake_redis, session_factory).tick(task) is False
    assert _scheduler(task, fake_redis, session_factory, now=SATURDAY).tick(task) is True


def test_redis_down_skips_round(session_factory):
    class Broken:
        def set(self, *args, **kwargs):
            raise redis.ConnectionError("down")

        def get(self, *args, **kwargs):
            raise redis.ConnectionError("down")

    task = CountingTask()
    scheduler = Scheduler([task], session_factory=session_factory, redis_client=lambda: cast(redis.Redis, Broken()))

    assert scheduler.tick(task) is False
    assert scheduler.status()[0]["last_run_at"] is None


def test_start_and_stop(fake_redis, session_factory):
    task = CountingTask()
    scheduler = _scheduler(task, fake_redis, session_factory)

    async def lifecycle():
        await scheduler.start()
        running = scheduler.status()[0]["running"]
        await scheduler.stop()
        return running

    assert asyncio.run(lifecycle()) is True
    assert scheduler.status()[0]["running"] is False
