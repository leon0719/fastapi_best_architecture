"""SMTP / LINE adapter:httpx 與 smtplib 都以 monkeypatch 取代,不寄真信、不打真 API。"""

import smtplib
from typing import Any

import httpx
import pytest

from app.common.exceptions import ExternalAPIException
from app.notifications import external_services
from app.notifications.external_services import LineMessagingClient, SmtpMailer

pytestmark = pytest.mark.unit


def _response(status: int) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("POST", "https://api.line.me/v2/bot/message/push"))


def test_smtp_not_configured_only_logs(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: pytest.fail("should not connect"))

    SmtpMailer("", 587, "", "", "noreply@example.com").send(["a@example.com"], "s", "b")


def test_smtp_failure_raises_external_api_exception(monkeypatch):
    def refuse(*args, **kwargs):
        raise ConnectionRefusedError

    monkeypatch.setattr(smtplib, "SMTP", refuse)

    with pytest.raises(ExternalAPIException):
        SmtpMailer("smtp.example.com", 587, "u", "p", "noreply@example.com").send(["a@example.com"], "s", "b")


def test_smtp_sends_with_starttls(monkeypatch):
    calls: list[tuple[Any, ...]] = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, context):
            calls.append(("starttls",))

        def login(self, username, password):
            calls.append(("login", username))

        def send_message(self, message):
            calls.append(("send", message["To"], message["Subject"]))

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

    SmtpMailer("smtp.example.com", 587, "u", "p", "noreply@example.com").send(["a@x.com", "b@x.com"], "主旨", "b")

    assert calls == [
        ("connect", "smtp.example.com", 587),
        ("starttls",),
        ("login", "u"),
        ("send", "a@x.com, b@x.com", "主旨"),
    ]


def test_line_not_configured_skips(monkeypatch):
    monkeypatch.setattr(external_services.httpx, "post", lambda *a, **k: pytest.fail("should not call"))

    LineMessagingClient("").push("U1", [], "key")


def test_line_push_sends_retry_key(monkeypatch):
    seen: dict[str, Any] = {}

    def fake_post(url, headers, json, timeout):
        seen.update(headers=headers, json=json)
        return _response(200)

    monkeypatch.setattr(external_services.httpx, "post", fake_post)

    LineMessagingClient("token").push("U1", [{"type": "text", "text": "hi"}], "retry-1")

    assert seen["headers"]["X-Line-Retry-Key"] == "retry-1"
    assert seen["json"] == {"to": "U1", "messages": [{"type": "text", "text": "hi"}]}


def test_line_push_409_means_already_sent(monkeypatch):
    monkeypatch.setattr(external_services.httpx, "post", lambda *a, **k: _response(409))

    LineMessagingClient("token").push("U1", [], "retry-1")


def test_line_push_error_raises(monkeypatch):
    monkeypatch.setattr(external_services.httpx, "post", lambda *a, **k: _response(429))

    with pytest.raises(ExternalAPIException, match="429"):
        LineMessagingClient("token").push("U1", [], "retry-1")
