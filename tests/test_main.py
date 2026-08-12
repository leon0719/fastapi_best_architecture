"""啟動流程不得用 create_all 建表(schema 由 Alembic 管理)。"""

import inspect

import pytest

pytestmark = pytest.mark.unit


def test_lifespan_does_not_create_tables():
    from app import main

    source = inspect.getsource(main)
    assert "init_db" not in source
    assert "create_all" not in source


def test_health_live_endpoint(client):
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "alive"}


def test_health_ready_endpoint_reports_per_dependency_status(client):
    # No real DB/Redis in this test env, so we only assert the readiness
    # contract (per-dependency breakdown + 200/503 gating), not that deps are up.
    resp = client.get("/health/ready")
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert set(body["checks"]) == {"db", "redis"}
    assert body["status"] in ("ready", "not_ready")
