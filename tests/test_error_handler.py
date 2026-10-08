"""框架層錯誤(未知路由、錯誤 method)也必須回 BaseResponse,前端才能用同一套 axiosService 處理。"""

import pytest

pytestmark = pytest.mark.unit


def test_unknown_route_returns_base_response_404(client):
    resp = client.get("/api/v1/does-not-exist")

    assert resp.status_code == 404
    assert resp.json() == {"data": None, "error": {"code": 404, "message": "Not Found"}}


def test_wrong_method_returns_base_response_405_with_allow_header(client):
    resp = client.patch("/api/v1/users")

    assert resp.status_code == 405
    assert resp.json()["error"]["code"] == 405
    assert "allow" in resp.headers
