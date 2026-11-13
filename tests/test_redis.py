"""ping_redis:連線錯誤由 tenacity 重試後降級為 False,其他錯誤不重試也不往外拋。"""

import pytest
import redis

from app.common.core import redis as redis_module

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    import tenacity

    monkeypatch.setattr(tenacity.nap.time, "sleep", lambda _s: None)


class FakeClient:
    def __init__(self, errors: list[Exception]) -> None:
        self.errors = errors
        self.calls = 0

    def ping(self) -> bool:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return True


def test_retries_connection_errors_then_succeeds(monkeypatch):
    client = FakeClient([redis.ConnectionError("down"), redis.TimeoutError("slow")])
    monkeypatch.setattr(redis_module, "get_redis", lambda: client)

    assert redis_module.ping_redis() is True
    assert client.calls == 3


def test_gives_up_after_three_attempts(monkeypatch):
    client = FakeClient([redis.ConnectionError("down")] * 5)
    monkeypatch.setattr(redis_module, "get_redis", lambda: client)

    assert redis_module.ping_redis() is False
    assert client.calls == 3


def test_other_redis_error_is_not_retried(monkeypatch):
    client = FakeClient([redis.ResponseError("WRONGTYPE")])
    monkeypatch.setattr(redis_module, "get_redis", lambda: client)

    assert redis_module.ping_redis() is False
    assert client.calls == 1
