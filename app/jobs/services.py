"""長任務:job_id + Redis 存狀態/進度(有 TTL),FastAPI BackgroundTasks 執行,可取消。

    # view:建立 job,交給 BackgroundTasks,馬上回 202 + job
    job = jobs.create(kind="report_export", owner_id=user.id)
    background.add_task(jobs.run, job.id, build_report, month)
    return BaseResponse(data=JobRead.from_record(job))

    # 工作函式:第一個參數是 JobContext,定期回報進度並檢查取消
    def build_report(ctx: JobContext, month: str) -> dict:
        for i, chunk in enumerate(chunks):
            ctx.check_cancelled()
            ...
            ctx.progress(100 * (i + 1) // len(chunks), f"第 {i + 1} 批")
        return {"rows": total}            # 會存進 job.result(要能 JSON 序列化)

狀態存 Redis 而不是記憶體:多 worker 時查詢請求不一定打到執行的那個 worker,取消旗標也一樣。
BackgroundTasks 跟著 worker 程序;worker 重啟時跑到一半的 job 會停在 running,直到 TTL 到期。
需要「重啟後續跑」或大量排隊時,就該換成真正的 task queue。
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Concatenate

import redis
from loguru import logger

from app.common.core.config import config
from app.common.exceptions import NotFoundException
from app.jobs.schemas import JobRecord, JobStatus

_KEY = "job:{id}"
_CANCEL_KEY = "job:{id}:cancel"
_FINISHED = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}


class JobCancelled(Exception):  # noqa: N818  # 是控制流程訊號,不是錯誤
    """工作函式在 check_cancelled() 收到取消旗標時拋出,由 JobService.run 轉成 cancelled 狀態。"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class JobService:
    def __init__(self, client: redis.Redis, ttl_seconds: int | None = None) -> None:
        self.redis = client
        self.ttl = ttl_seconds or config.job_ttl_seconds

    def create(self, kind: str, owner_id: int | None = None) -> JobRecord:
        now = _now()
        job = JobRecord(
            id=uuid.uuid4().hex, kind=kind, owner_id=owner_id, status=JobStatus.PENDING, created_at=now, updated_at=now
        )
        self._save(job)
        logger.info(f"[Service] Job created - job_id: {job.id}, kind: {kind}, owner_id: {owner_id}")
        return job

    def get(self, job_id: str) -> JobRecord:
        raw = self.redis.get(_KEY.format(id=job_id))
        if not isinstance(raw, str | bytes):
            logger.warning(f"[Service] Job not found - job_id: {job_id}")
            raise NotFoundException(f"Job {job_id} not found")
        return JobRecord.model_validate_json(raw)

    def get_for(self, job_id: str, user_id: int) -> JobRecord:
        """只有發起者看得到;別人的 job(含 admin)一律回 404,不透露它存在。"""
        job = self.get(job_id)
        if job.owner_id != user_id:
            logger.warning(f"[Service] Job access denied - job_id: {job_id}, user_id: {user_id}")
            raise NotFoundException(f"Job {job_id} not found")
        return job

    def request_cancel(self, job_id: str) -> JobRecord:
        """設取消旗標;工作函式下一次 check_cancelled() 時停下。已結束的 job 不受影響。"""
        job = self.get(job_id)
        if job.status in _FINISHED:
            return job
        self.redis.set(_CANCEL_KEY.format(id=job_id), "1", ex=self.ttl)
        if job.status == JobStatus.PENDING:  # 還沒開始跑:直接標成已取消,run() 開始時會看到
            job = self._update(job, status=JobStatus.CANCELLED, message="已取消")
        logger.info(f"[Service] Job cancel requested - job_id: {job_id}")
        return job

    def is_cancel_requested(self, job_id: str) -> bool:
        return bool(self.redis.exists(_CANCEL_KEY.format(id=job_id)))

    def progress(self, job_id: str, percent: int, message: str | None = None) -> None:
        self._update(self.get(job_id), progress=max(0, min(100, percent)), message=message)

    def run[**P](
        self, job_id: str, func: Callable[Concatenate[JobContext, P], Any], *args: P.args, **kwargs: P.kwargs
    ) -> None:
        """BackgroundTasks 執行的進入點。任何結果都寫回狀態,不往外拋(背景工作沒有人接例外)。"""
        job = self.get(job_id)
        if job.status == JobStatus.CANCELLED or self.is_cancel_requested(job_id):
            self._update(job, status=JobStatus.CANCELLED, message="已取消")
            return
        job = self._update(job, status=JobStatus.RUNNING)
        try:
            result = func(JobContext(self, job_id), *args, **kwargs)
        except JobCancelled:
            self._update(self.get(job_id), status=JobStatus.CANCELLED, message="已取消")
            logger.info(f"[Service] Job cancelled - job_id: {job_id}")
            return
        except Exception as e:  # noqa: BLE001  # 背景工作的終點:記錄並把失敗寫進狀態給前端看
            logger.exception(f"[Service] Job failed - job_id: {job_id}, kind: {job.kind}")
            # 只給例外類別,不給訊息:訊息可能含 SQL、路徑、個資
            self._update(self.get(job_id), status=JobStatus.FAILED, error=type(e).__name__, message="執行失敗")
            return
        self._update(self.get(job_id), status=JobStatus.SUCCEEDED, progress=100, result=result)
        logger.info(f"[Service] Job succeeded - job_id: {job_id}, kind: {job.kind}")

    def _update(self, job: JobRecord, **changes: Any) -> JobRecord:
        job = job.model_copy(update={**changes, "updated_at": _now()})
        self._save(job)
        return job

    def _save(self, job: JobRecord) -> None:
        self.redis.set(_KEY.format(id=job.id), job.model_dump_json(), ex=self.ttl)


class JobContext:
    """傳給工作函式:回報進度、檢查取消。"""

    def __init__(self, service: JobService, job_id: str) -> None:
        self._service = service
        self.job_id = job_id

    def progress(self, percent: int, message: str | None = None) -> None:
        self._service.progress(self.job_id, percent, message)

    def check_cancelled(self) -> None:
        if self._service.is_cancel_requested(self.job_id):
            raise JobCancelled(self.job_id)
