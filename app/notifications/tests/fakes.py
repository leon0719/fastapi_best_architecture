"""測試用假寄送端:記錄呼叫,可設定失敗。不寄真信、不打 LINE。"""

from app.common.exceptions import ExternalAPIException


class FakeMailer:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[tuple[list[str], str, str]] = []

    def send(self, to: list[str], subject: str, body: str) -> None:
        if self.fail:
            raise ExternalAPIException("通知信寄送失敗")
        self.sent.append((to, subject, body))


class FakeLine:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.pushed: list[tuple[str, list[dict], str]] = []

    def push(self, to: str, messages: list[dict], retry_key: str) -> None:
        if self.fail:
            raise ExternalAPIException("LINE 推播失敗(HTTP 429)")
        self.pushed.append((to, messages, retry_key))
