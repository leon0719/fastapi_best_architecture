"""長任務查詢/取消,與排程狀態。"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.dependencies import current_user, require_role
from app.common.schemas import BaseResponse
from app.jobs.dependencies import get_job_service, get_scheduler
from app.jobs.scheduler import Scheduler
from app.jobs.schemas import JobRead, ScheduledTaskRead
from app.jobs.services import JobService
from app.users.models import Role, User

router = APIRouter(prefix="/jobs", tags=["jobs"])
scheduler_router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("/{job_id}", response_model=BaseResponse[JobRead])
def get_job(
    job_id: str,
    user: Annotated[User, Depends(current_user)],
    service: Annotated[JobService, Depends(get_job_service)],
):
    """查詢 job 狀態與進度(前端輪詢)。只有發起者看得到,其他人 404。"""
    return BaseResponse(data=JobRead.from_record(service.get_for(job_id, user.id)))


@router.post("/{job_id}/cancel", response_model=BaseResponse[JobRead])
def cancel_job(
    job_id: str,
    user: Annotated[User, Depends(current_user)],
    service: Annotated[JobService, Depends(get_job_service)],
):
    """要求取消;工作函式在下一個檢查點停下。"""
    service.get_for(job_id, user.id)
    return BaseResponse(data=JobRead.from_record(service.request_cancel(job_id)))


@scheduler_router.get(
    "/tasks", response_model=BaseResponse[list[ScheduledTaskRead]], dependencies=[Depends(require_role(Role.ADMIN))]
)
def list_scheduled_tasks(scheduler: Annotated[Scheduler, Depends(get_scheduler)]):
    """排程任務狀態:這個 worker 是否在跑,以及全叢集最後一次執行結果。"""
    return BaseResponse(data=scheduler.status())
