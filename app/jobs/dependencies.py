"""長任務與排程的 FastAPI 依賴。"""

from fastapi import Request

from app.common.core.redis import get_redis
from app.jobs.scheduler import Scheduler
from app.jobs.services import JobService


def get_job_service() -> JobService:
    return JobService(get_redis())


def get_scheduler(request: Request) -> Scheduler:
    return request.app.state.scheduler
