"""Request ID、Sentry 去識別化、CORS、正式環境關閉 /docs、DEBUG 才有的路由。"""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.common.core.log_config import _scrub_event, setup_sentry
from app.common.core.request_context import REQUEST_ID_HEADER, get_request_id, set_request_id

pytestmark = pytest.mark.unit


def test_generates_request_id(client):
    resp = client.get("/api/v1/chatbots")

    assert len(resp.headers[REQUEST_ID_HEADER]) == 32


def test_keeps_valid_incoming_request_id(client):
    resp = client.get("/api/v1/chatbots", headers={REQUEST_ID_HEADER: "abc-123"})

    assert resp.headers[REQUEST_ID_HEADER] == "abc-123"


def test_replaces_unsafe_incoming_request_id(client):
    resp = client.get("/api/v1/chatbots", headers={REQUEST_ID_HEADER: "bad\nid"})

    assert resp.headers[REQUEST_ID_HEADER] != "bad\nid"


def test_request_id_and_user_id_in_log_line(client, make_user):
    from loguru import logger

    lines: list[str] = []
    sink = logger.add(lambda m: lines.append(m), format="{extra[request_id]} {message}")
    try:
        _, headers = make_user()
        client.get("/api/v1/auth/me", headers={**headers, REQUEST_ID_HEADER: "trace-1"})
    finally:
        logger.remove(sink)

    api_lines = [line for line in lines if "[API]" in line]
    assert api_lines and api_lines[-1].startswith("trace-1 ")
    assert "user_id:" in api_lines[-1]


def test_500_carries_request_id(client):
    app = client.app
    safe = TestClient(app, raise_server_exceptions=False)

    resp = safe.get("/debug/sentry", headers={REQUEST_ID_HEADER: "boom-1"})

    assert resp.status_code == 500
    assert resp.json()["error"]["reason"] == "internal_error"
    assert resp.headers[REQUEST_ID_HEADER] == "boom-1"


def test_set_request_id():
    assert set_request_id("ok_1.2") == "ok_1.2"
    assert get_request_id() == "ok_1.2"
    assert set_request_id("x" * 65) != "x" * 65


def test_scrub_event_keeps_first_line_and_masks_secrets():
    set_request_id("req-9")
    event = {
        "exception": {"values": [{"value": "failed for a@b.com\nDETAIL: Key (email)=(a@b.com)"}]},
        "logentry": {"message": "Bearer abc.def leaked", "params": ["secret"]},
        "request": {"headers": {"Authorization": "Bearer x"}, "query_string": "code=1", "url": "/x"},
    }

    scrubbed: Any = _scrub_event(event, {})  # type: ignore[arg-type]  # 測試用的最小 event dict

    assert scrubbed["exception"]["values"][0]["value"] == "failed for [email]"
    assert scrubbed["logentry"] == {"message": "Bearer [token] leaked"}
    assert scrubbed["request"] == {"url": "/x"}
    assert scrubbed["tags"]["request_id"] == "req-9"


def test_setup_sentry_is_noop_without_dsn():
    import sentry_sdk

    setup_sentry()

    assert not sentry_sdk.get_client().is_active()


def test_cors_preflight_exposes_headers(client):
    resp = client.options(
        "/api/v1/chatbots",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    get = client.get("/api/v1/chatbots", headers={"Origin": "http://localhost:5173"})

    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "Content-Disposition" in get.headers["access-control-expose-headers"]
    assert REQUEST_ID_HEADER in get.headers["access-control-expose-headers"]


def test_cors_rejects_unknown_origin(client):
    resp = client.get("/api/v1/chatbots", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in resp.headers


def test_docs_closed_in_prod():
    from app.main import api_docs_kwargs

    assert api_docs_kwargs(False) == {"docs_url": None, "redoc_url": None, "openapi_url": None}
    assert api_docs_kwargs(True)["docs_url"] == "/docs"


def test_debug_routes_only_when_debug():
    from app.main import add_debug_routes

    app = FastAPI()
    add_debug_routes(app, debug=False)

    assert not [r for r in app.routes if getattr(r, "path", "") == "/debug/sentry"]
