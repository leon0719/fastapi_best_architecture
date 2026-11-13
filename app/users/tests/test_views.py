"""User endpoint tests — the reference for endpoint tests.

Assert the status code AND the BaseResponse body; for writes, re-read through the API.
Protected endpoints: log in with the `admin_headers` / `make_user` fixtures (root conftest.py),
and cover 401 (not signed in) and 403 (wrong role).
"""

import io
import zipfile

import pytest
from openpyxl import load_workbook

pytestmark = pytest.mark.unit

URL = "/api/v1/users"


@pytest.fixture()
def api(client, admin_headers):
    """以 admin 身分呼叫的 client。"""
    client.headers.update(admin_headers)
    return client


def test_requires_login(client):
    resp = client.get(URL)

    assert resp.status_code == 401
    assert resp.json()["error"]["reason"] == "unauthenticated"


def test_requires_admin_role(client, make_user):
    _, headers = make_user("user")

    resp = client.get(URL, headers=headers)

    assert resp.status_code == 403
    assert resp.json()["error"] == {"code": 403, "message": "權限不足", "reason": "permission_denied"}


def test_create_user_returns_201_with_data(api):
    resp = api.post(URL, json={"name": "alice"})

    assert resp.status_code == 201
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["name"] == "alice"
    assert api.get(f"{URL}/{body['data']['id']}").json()["data"]["name"] == "alice"


def test_create_user_with_taken_name_returns_409(api):
    api.post(URL, json={"name": "alice"})

    resp = api.post(URL, json={"name": "alice"})

    assert resp.status_code == 409
    assert resp.json() == {
        "data": None,
        "error": {"code": 409, "message": "User with name 'alice' already exists", "reason": "user_name_taken"},
    }


def test_create_user_with_invalid_body_returns_422(api):
    resp = api.post(URL, json={"name": ""})

    assert resp.status_code == 422
    body = resp.json()
    assert body["data"] is None
    assert body["error"]["code"] == 422
    assert body["error"]["reason"] == "validation_error"
    assert body["error"]["message"].startswith("name:")


def test_get_missing_user_returns_404(api):
    resp = api.get(f"{URL}/999")

    assert resp.status_code == 404
    assert resp.json()["error"] == {"code": 404, "message": "User with id 999 not found", "reason": "not_found"}


def test_list_users(api):
    api.post(URL, json={"name": "a"})
    api.post(URL, json={"name": "b"})

    resp = api.get(URL)

    assert resp.status_code == 200
    assert [u["name"] for u in resp.json()["data"]] == ["b", "a", "admin"]


def test_update_user(api):
    user_id = api.post(URL, json={"name": "alice"}).json()["data"]["id"]

    resp = api.put(f"{URL}/{user_id}", json={"name": "alicia"})

    assert resp.status_code == 200
    assert api.get(f"{URL}/{user_id}").json()["data"]["name"] == "alicia"


def test_delete_user(api):
    user_id = api.post(URL, json={"name": "alice"}).json()["data"]["id"]

    resp = api.delete(f"{URL}/{user_id}")

    assert resp.status_code == 200
    assert resp.json() == {"data": None, "error": None}
    assert api.get(f"{URL}/{user_id}").status_code == 404


def test_export_xlsx_has_header_and_chinese_filename(api):
    api.post(URL, json={"name": "王小明"})

    resp = api.get(f"{URL}/export", params={"format": "xlsx"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/vnd.openxmlformats")
    disposition = resp.headers["content-disposition"]
    assert disposition.startswith("attachment; filename=")
    assert "filename*=UTF-8''%E4%BD%BF%E7%94%A8%E8%80%85" in disposition  # 使用者…
    ws = load_workbook(io.BytesIO(resp.content)).active
    assert [c.value for c in ws[1]] == ["ID", "名稱", "Email", "角色", "啟用"]
    assert "王小明" in [c.value for c in ws["B"]]


def test_export_pdf_and_zip(api):
    pdf = api.get(f"{URL}/export", params={"format": "pdf"})
    archive = api.get(f"{URL}/export", params={"format": "zip"})

    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF-")
    assert archive.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(archive.content)).namelist()
    assert sorted(n.rsplit(".", 1)[1] for n in names) == ["pdf", "xlsx"]


def test_export_rejects_unknown_format(api):
    resp = api.get(f"{URL}/export", params={"format": "csv"})

    assert resp.status_code == 422
