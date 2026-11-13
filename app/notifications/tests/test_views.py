"""LINE webhook 端點。"""

import json

import pytest

from app.notifications.services import LineWebhookService
from app.notifications.utils import line_signature
from app.notifications.views import get_line_webhook_service

pytestmark = pytest.mark.unit

URL = "/api/v1/line/webhook"
SECRET = "line-test-secret"
BODY = json.dumps({"destination": "x", "events": [{"type": "message"}]}).encode()


@pytest.fixture()
def configured(client):
    client.app.dependency_overrides[get_line_webhook_service] = lambda: LineWebhookService(SECRET)
    return client


def test_valid_signature_returns_200(configured):
    resp = configured.post(URL, content=BODY, headers={"X-Line-Signature": line_signature(BODY, SECRET)})

    assert resp.status_code == 200
    assert resp.json() == {"data": None, "error": None}


def test_invalid_signature_returns_401(configured):
    resp = configured.post(URL, content=BODY, headers={"X-Line-Signature": "forged"})

    assert resp.status_code == 401
    assert resp.json()["error"]["reason"] == "invalid_signature"


def test_missing_signature_returns_401(configured):
    assert configured.post(URL, content=BODY).status_code == 401


def test_unconfigured_secret_rejects_everything(client):
    resp = client.post(URL, content=BODY, headers={"X-Line-Signature": line_signature(BODY, "")})

    assert resp.status_code == 401
