"""長任務與排程狀態的回應 schema。"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobRecord(BaseModel):
    """存在 Redis 的完整狀態(含擁有者等內部欄位);API 只回 JobRead。"""

    id: str
    kind: str
    owner_id: int | None = None
    status: JobStatus
    progress: int | None = None  # 0–100;工作函式回報前是 None
    message: str | None = None
    result: Any = None
    error: str | None = None  # 只有例外類別,不含訊息
    created_at: str
    updated_at: str


class JobRead(BaseModel):
    """與前端模板的契約:形狀固定為 {id, status, progress, result, error}。"""

    id: str
    status: JobStatus
    progress: int | None
    result: Any
    error: str | None

    @classmethod
    def from_record(cls, record: JobRecord) -> JobRead:
        return cls(
            id=record.id, status=record.status, progress=record.progress, result=record.result, error=record.error
        )


class ScheduledTaskRead(BaseModel):
    name: str
    interval_seconds: int
    skip_non_working_days: bool
    running: bool
    last_run_at: str | None
    last_duration_seconds: float | None
    last_result: str | None
    last_error: str | None
    last_worker: str | None
