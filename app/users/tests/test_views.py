"""User endpoint tests — the reference for endpoint tests.

Assert the status code AND the BaseResponse body; for writes, re-read through the API.
"""

import pytest

pytestmark = pytest.mark.unit

URL = "/api/v1/users"


def test_create_user_returns_201_with_data(client):
    resp = client.post(URL, json={"name": "alice"})

    assert resp.status_code == 201
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["name"] == "alice"
    assert client.get(f"{URL}/{body['data']['id']}").json()["data"]["name"] == "alice"


def test_create_user_with_taken_name_returns_409(client):
    client.post(URL, json={"name": "alice"})

    resp = client.post(URL, json={"name": "alice"})

    assert resp.status_code == 409
    assert resp.json() == {
        "data": None,
        "error": {"code": 409, "message": "User with name 'alice' already exists"},
    }


def test_create_user_with_invalid_body_returns_422(client):
    resp = client.post(URL, json={"name": ""})

    assert resp.status_code == 422
    body = resp.json()
    assert body["data"] is None
    assert body["error"]["code"] == 422
    assert body["error"]["message"].startswith("name:")


def test_get_missing_user_returns_404(client):
    resp = client.get(f"{URL}/999")

    assert resp.status_code == 404
    assert resp.json()["error"] == {"code": 404, "message": "User with id 999 not found"}


def test_list_users(client):
    client.post(URL, json={"name": "a"})
    client.post(URL, json={"name": "b"})

    resp = client.get(URL)

    assert resp.status_code == 200
    assert [u["name"] for u in resp.json()["data"]] == ["b", "a"]


def test_update_user(client):
    user_id = client.post(URL, json={"name": "alice"}).json()["data"]["id"]

    resp = client.put(f"{URL}/{user_id}", json={"name": "alicia"})

    assert resp.status_code == 200
    assert client.get(f"{URL}/{user_id}").json()["data"]["name"] == "alicia"


def test_delete_user(client):
    user_id = client.post(URL, json={"name": "alice"}).json()["data"]["id"]

    resp = client.delete(f"{URL}/{user_id}")

    assert resp.status_code == 200
    assert resp.json() == {"data": None, "error": None}
    assert client.get(f"{URL}/{user_id}").status_code == 404
