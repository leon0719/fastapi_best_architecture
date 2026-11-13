"""外部 API 重試 decorator:sync/async × 丟例外/回預設值。"""

import asyncio

import pytest

from app.common.core.retry import retry_external, retry_external_async, retry_or_default, retry_or_default_async
from app.common.exceptions import ExternalAPIException

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """tenacity 的等待改成不睡,測試不拖時間。"""
    import tenacity

    monkeypatch.setattr(tenacity.nap.time, "sleep", lambda _s: None)

    async def fast_sleep(_s):
        return None

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)


class Flaky:
    def __init__(self, failures: int, exc: type[Exception] = ConnectionError) -> None:
        self.failures, self.exc, self.calls = failures, exc, 0

    def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise self.exc("down")
        return "ok"


def test_sync_retries_then_succeeds():
    flaky = Flaky(2)

    assert retry_external("svc", attempts=3, max_seconds=5)(flaky)() == "ok"
    assert flaky.calls == 3


def test_sync_gives_up_with_external_api_exception():
    flaky = Flaky(5)

    with pytest.raises(ExternalAPIException, match="svc"):
        retry_external("svc", attempts=3, max_seconds=5)(flaky)()
    assert flaky.calls == 3


def test_non_retryable_exception_propagates_immediately():
    flaky = Flaky(5, exc=ValueError)

    with pytest.raises(ValueError):
        retry_external("svc", attempts=3, max_seconds=5)(flaky)()
    assert flaky.calls == 1


def test_sync_default_on_failure():
    assert retry_or_default("svc", default="fallback", attempts=3, max_seconds=5)(Flaky(5))() == "fallback"
    assert retry_or_default("svc", default="fallback", attempts=3, max_seconds=5)(Flaky(1))() == "ok"


def test_async_variants():
    flaky = Flaky(1)

    async def call() -> str:
        return flaky()

    assert asyncio.run(retry_external_async("svc", attempts=3, max_seconds=5)(call)()) == "ok"

    always = Flaky(9)

    async def failing() -> str:
        return always()

    with pytest.raises(ExternalAPIException):
        asyncio.run(retry_external_async("svc", attempts=3, max_seconds=5)(failing)())
    assert asyncio.run(retry_or_default_async("svc", default=None, attempts=3, max_seconds=5)(failing)()) is None
