"""JobService:狀態、進度、取消、失敗都存 Redis(測試用 fakeredis)。"""

import pytest

from app.common.exceptions import NotFoundException
from app.jobs.schemas import JobStatus
from app.jobs.services import JobContext, JobService

pytestmark = pytest.mark.unit


@pytest.fixture()
def jobs(fake_redis):
    return JobService(fake_redis, ttl_seconds=60)


def test_create_and_get(jobs, fake_redis):
    job = jobs.create("export", owner_id=1)

    assert jobs.get(job.id).status == JobStatus.PENDING
    assert jobs.get(job.id).progress is None
    assert 0 < fake_redis.ttl(f"job:{job.id}") <= 60


def test_get_missing_raises_not_found(jobs):
    with pytest.raises(NotFoundException):
        jobs.get("nope")


def test_only_owner_can_see_job(jobs):
    job = jobs.create("export", owner_id=1)

    assert jobs.get_for(job.id, 1).id == job.id
    with pytest.raises(NotFoundException):
        jobs.get_for(job.id, 2)


def test_run_success_records_progress_and_result(jobs):
    job = jobs.create("export", owner_id=1)

    def work(ctx: JobContext, n: int) -> dict:
        ctx.progress(50, "half")
        return {"rows": n}

    jobs.run(job.id, work, 3)

    done = jobs.get(job.id)
    assert (done.status, done.progress, done.result) == (JobStatus.SUCCEEDED, 100, {"rows": 3})


def test_run_failure_records_only_exception_type(jobs):
    job = jobs.create("export")

    def work(ctx: JobContext) -> None:
        raise RuntimeError("secret detail")

    jobs.run(job.id, work)

    failed = jobs.get(job.id)
    assert (failed.status, failed.error) == (JobStatus.FAILED, "RuntimeError")


def test_cancel_while_running_stops_at_checkpoint(jobs):
    job = jobs.create("export")
    seen = []

    def work(ctx: JobContext) -> None:
        for i in range(5):
            if i == 2:
                jobs.request_cancel(job.id)  # 模擬使用者在第 2 步按取消
            ctx.check_cancelled()
            seen.append(i)

    jobs.run(job.id, work)

    assert seen == [0, 1]
    assert jobs.get(job.id).status == JobStatus.CANCELLED


def test_cancel_pending_job_never_runs(jobs):
    job = jobs.create("export")
    assert jobs.request_cancel(job.id).status == JobStatus.CANCELLED
    called = []

    jobs.run(job.id, lambda ctx: called.append(1))

    assert called == []
    assert jobs.get(job.id).status == JobStatus.CANCELLED


def test_cancel_finished_job_is_noop(jobs):
    job = jobs.create("export")
    jobs.run(job.id, lambda ctx: None)

    assert jobs.request_cancel(job.id).status == JobStatus.SUCCEEDED


def test_progress_is_clamped(jobs):
    job = jobs.create("export")

    jobs.progress(job.id, 150)

    assert jobs.get(job.id).progress == 100
