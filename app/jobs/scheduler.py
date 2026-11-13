"""輕量排程(不引入 Celery):在 app 程序內以 asyncio 週期執行的任務。

    class PurgeSomethingTask(PeriodicTask):
        name = "purge_something"
        interval_seconds = 24 * 3600

        def run(self, db: Session) -> str:
            return f"deleted: {SomeService(db).purge()}"

    # app/main.py
    scheduler = Scheduler([PurgeSomethingTask(), ...])   # lifespan 內 start()/stop()

- 每一輪各自開 DB session(請求的 session 早已關閉),run() 是同步函式,在 threadpool 執行。
- 例外只寫 log(logger.exception → Sentry),不讓單次失敗停掉排程。
- 多 worker / 多台機器:每輪先搶 Redis 鎖(SET NX EX interval),搶到的才跑,所以全叢集約每個
  interval 只跑一次;Redis 連不上就跳過這輪(寧可漏跑一輪,不要每個 worker 都跑)。
- skip_non_working_days=True:台灣非工作日(週末、國定假日,補班日照跑)不跑,見 app/holidays。
- 需要「每天固定幾點」:覆寫 should_run() 判斷時間,並覆寫 lock_key()/lock_ttl() 以日期為鎖。
"""

import asyncio
import contextlib
import json
import os
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

import redis
from loguru import logger
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.common.core.redis import get_redis
from app.common.db.database import get_session_factory
from app.holidays.services import is_working_day

TAIPEI = ZoneInfo("Asia/Taipei")
_STATUS_TTL_SECONDS = 7 * 24 * 3600


class PeriodicTask(ABC):
    """週期任務的基底類別。子類設定 name、interval_seconds,實作 run()。"""

    name: ClassVar[str]
    interval_seconds: ClassVar[int]
    skip_non_working_days: ClassVar[bool] = False
    # 啟動後多久跑第一輪:避開部署時新容器起來、migration 還沒跑完的那幾秒
    initial_delay_seconds: ClassVar[int] = 30

    @abstractmethod
    def run(self, db: Session) -> str | None:
        """執行一輪;回傳一行摘要(會進 log 與 status)。commit 由實作自己負責。"""

    def should_run(self, now: datetime) -> bool:
        return True

    def lock_key(self, now: datetime) -> str:
        return f"scheduler:lock:{self.name}"

    def lock_ttl(self) -> int:
        return self.interval_seconds

    @property
    def check_every_seconds(self) -> int:
        """多久檢查一次要不要跑;真正的執行頻率由 Redis 鎖控制。"""
        return max(1, min(self.interval_seconds, 60))


@dataclass
class TaskStatus:
    name: str
    interval_seconds: int
    skip_non_working_days: bool
    running: bool = False  # 這個 worker 的排程迴圈是否在跑
    last_run_at: str | None = None  # 以下是全叢集最後一次執行(存在 Redis)
    last_duration_seconds: float | None = None
    last_result: str | None = None
    last_error: str | None = None
    last_worker: str | None = None


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Scheduler:
    def __init__(
        self,
        tasks: list[PeriodicTask],
        *,
        session_factory: Callable[[], Session] | None = None,
        redis_client: Callable[[], redis.Redis] = get_redis,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.tasks = {task.name: task for task in tasks}
        self._session_factory = session_factory
        self._redis = redis_client
        self._now = now
        self._loops: dict[str, asyncio.Task] = {}
        self._worker = f"{os.uname().nodename}:{os.getpid()}"

    def _sessions(self) -> Callable[[], Session]:
        return self._session_factory or get_session_factory()

    async def start(self) -> None:
        for task in self.tasks.values():
            if task.name not in self._loops:
                self._loops[task.name] = asyncio.create_task(self._loop(task), name=f"scheduler:{task.name}")
        logger.info(f"[Scheduler] Started - tasks: {list(self.tasks)}")

    async def stop(self) -> None:
        for loop in self._loops.values():
            loop.cancel()
        for loop in self._loops.values():
            with contextlib.suppress(asyncio.CancelledError):
                await loop
        self._loops.clear()
        logger.info("[Scheduler] Stopped")

    async def _loop(self, task: PeriodicTask) -> None:
        await asyncio.sleep(task.initial_delay_seconds)
        while True:
            try:
                await run_in_threadpool(self.tick, task)
            except Exception:  # noqa: BLE001  # 排程不能因為單次失敗就停掉;已由 logger.exception 回報
                logger.exception(f"[Scheduler] Tick crashed - task: {task.name}")
            await asyncio.sleep(task.check_every_seconds)

    def tick(self, task: PeriodicTask) -> bool:
        """一步:該跑、是工作日、搶到鎖才執行。回傳有沒有執行。例外會被記錄並寫進 status,不往外拋。"""
        now = self._now()
        if not task.should_run(now):
            return False
        if task.skip_non_working_days:
            with self._sessions()() as db:
                if not is_working_day(db, now.astimezone(TAIPEI).date()):
                    return False
        if not self._acquire(task, now):
            return False

        start = time.monotonic()
        result: str | None = None
        error: str | None = None
        try:
            with self._sessions()() as db:
                result = task.run(db)
            logger.info(
                f"[Scheduler] Task done - task: {task.name}, result: {result}, "
                f"duration: {time.monotonic() - start:.3f}s"
            )
        except Exception as e:  # noqa: BLE001  # 只寫 log 與 status,下一輪照常
            error = type(e).__name__
            logger.exception(f"[Scheduler] Task failed - task: {task.name}, duration: {time.monotonic() - start:.3f}s")
        self._save_status(task, now, time.monotonic() - start, result, error)
        return True

    def _acquire(self, task: PeriodicTask, now: datetime) -> bool:
        try:
            return bool(self._redis().set(task.lock_key(now), self._worker, nx=True, ex=task.lock_ttl()))
        except redis.RedisError as e:
            logger.warning(f"[Scheduler] Lock unavailable, skip this round - task: {task.name}, error: {e}")
            return False

    def _save_status(
        self, task: PeriodicTask, now: datetime, duration: float, result: str | None, error: str | None
    ) -> None:
        record = {
            "last_run_at": now.isoformat(),
            "last_duration_seconds": round(duration, 3),
            "last_result": result,
            "last_error": error,
            "last_worker": self._worker,
        }
        try:
            self._redis().set(f"scheduler:status:{task.name}", json.dumps(record), ex=_STATUS_TTL_SECONDS)
        except redis.RedisError as e:
            logger.warning(f"[Scheduler] Failed to save status - task: {task.name}, error: {e}")

    def status(self) -> list[dict[str, Any]]:
        statuses = []
        for task in self.tasks.values():
            loop = self._loops.get(task.name)
            item = TaskStatus(
                name=task.name,
                interval_seconds=task.interval_seconds,
                skip_non_working_days=task.skip_non_working_days,
                running=loop is not None and not loop.done(),
            )
            try:
                raw = self._redis().get(f"scheduler:status:{task.name}")
            except redis.RedisError:
                raw = None
            if isinstance(raw, str | bytes):
                for key, value in json.loads(raw).items():
                    setattr(item, key, value)
            statuses.append(asdict(item))
        return statuses
