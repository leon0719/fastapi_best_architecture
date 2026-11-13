"""長任務與排程狀態端點。回應形狀是前端模板的契約:{id, status, progress, result, error}。"""

import pytest

from app.jobs.dependencies import get_job_service, get_scheduler
from app.jobs.scheduler import PeriodicTask, Scheduler
from app.jobs.services import JobService

pytestmark = pytest.mark.unit

URL = "/api/v1/jobs"


@pytest.fixture()
def jobs(client, fake_redis):
    service = JobService(fake_redis)
    client.app.dependency_overrides[get_job_service] = lambda: service
    return service


def test_get_job_returns_contract_shape(client, jobs, make_user):
    user, headers = make_user()
    job = jobs.create("export", owner_id=user.id)

    resp = client.get(f"{URL}/{job.id}", headers=headers)

    assert resp.status_code == 200
    assert resp.json() == {
        "data": {"id": job.id, "status": "pending", "progress": None, "result": None, "error": None},
        "error": None,
    }


def test_other_users_job_is_404_even_for_admin(client, jobs, make_user):
    owner, _ = make_user()
    _, other = make_user("admin")
    job = jobs.create("export", owner_id=owner.id)

    assert client.get(f"{URL}/{job.id}", headers=other).status_code == 404
    assert client.post(f"{URL}/{job.id}/cancel", headers=other).status_code == 404


def test_missing_job_returns_404(client, jobs, make_user):
    _, headers = make_user()

    resp = client.get(f"{URL}/nope", headers=headers)

    assert resp.status_code == 404
    assert resp.json()["error"]["reason"] == "not_found"


def test_cancel_job(client, jobs, make_user):
    user, headers = make_user()
    job = jobs.create("export", owner_id=user.id)

    resp = client.post(f"{URL}/{job.id}/cancel", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "cancelled"
    assert set(resp.json()["data"]) == {"id", "status", "progress", "result", "error"}


def test_jobs_require_login(client, jobs):
    assert client.get(f"{URL}/x").status_code == 401


class _Task(PeriodicTask):
    name = "demo"
    interval_seconds = 60

    def run(self, db):
        return "ok"


def test_scheduler_status_admin_only(client, make_user, fake_redis):
    scheduler = Scheduler([_Task()], redis_client=lambda: fake_redis)
    client.app.dependency_overrides[get_scheduler] = lambda: scheduler
    _, user_headers = make_user()
    _, admin_headers = make_user("admin")

    assert client.get("/api/v1/scheduler/tasks", headers=user_headers).status_code == 403
    resp = client.get("/api/v1/scheduler/tasks", headers=admin_headers)

    assert resp.status_code == 200
    assert resp.json()["data"][0]["name"] == "demo"
    assert resp.json()["data"][0]["running"] is False
