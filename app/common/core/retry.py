"""外部 API 呼叫的重試 decorator(tenacity),給各 app 的 external_services.py 使用。

四種組合:sync / async × 最後失敗時「丟 ExternalAPIException」/「回傳預設值」。

    @retry_external("LINE", retry_on=(httpx.TransportError,))
    def push(...): ...

    @retry_or_default("天氣", default=None, retry_on=(httpx.TransportError,))
    def fetch_weather(...): ...

- 只重試 `retry_on` 列出的例外(預設是網路層的 TimeoutError / ConnectionError);4xx 這類
  重試也不會好的錯誤應該直接 raise,不要列進去。
- 重試用完後:丟版本把最後一個例外包成 ExternalAPIException(502,前端看到統一錯誤格式);
  預設值版本只記 log 並回傳 default,用在「拿不到也沒關係」的輔助資料。
- 不在 retry_on 內的例外照常往外拋(程式錯誤不該被吞掉)。
- httpx 只能在 external_services.py import(ruff TID251),所以 retry_on 由呼叫端傳入。
"""

import functools
from collections.abc import Awaitable, Callable

from loguru import logger
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
)

from app.common.exceptions import ExternalAPIException

DEFAULT_RETRY_ON: tuple[type[BaseException], ...] = (TimeoutError, ConnectionError)


def _policy(service: str, retry_on: tuple[type[BaseException], ...], attempts: int, max_seconds: float) -> dict:
    def _log_retry(state: RetryCallState) -> None:
        exc = state.outcome.exception() if state.outcome else None
        logger.warning(
            f"[External] {service} retrying - attempt: {state.attempt_number}, error_type: {type(exc).__name__}"
        )

    return {
        "stop": stop_after_attempt(attempts) | stop_after_delay(max_seconds),
        "wait": wait_exponential(multiplier=0.5, min=0.5, max=8),
        "retry": retry_if_exception_type(retry_on),
        "before_sleep": _log_retry,
        "reraise": True,
    }


def _give_up(service: str, attempts: int, exc: BaseException) -> ExternalAPIException:
    # 只記例外類別:第三方錯誤訊息可能夾帶 token 或個資
    logger.error(f"[External] {service} failed after retries - attempts: {attempts}, error_type: {type(exc).__name__}")
    return ExternalAPIException(f"{service} 服務暫時無法使用,請稍後再試")


def retry_external[**P, R](
    service: str,
    *,
    retry_on: tuple[type[BaseException], ...] = DEFAULT_RETRY_ON,
    attempts: int = 3,
    max_seconds: float = 30,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """sync:重試後仍失敗 → raise ExternalAPIException。"""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                for attempt in Retrying(**_policy(service, retry_on, attempts, max_seconds)):
                    with attempt:
                        return func(*args, **kwargs)
            except retry_on as e:
                raise _give_up(service, attempts, e) from e
            raise AssertionError("unreachable")  # pragma: no cover  # Retrying 一定 return 或 raise

        return wrapper

    return decorator


def retry_external_async[**P, R](
    service: str,
    *,
    retry_on: tuple[type[BaseException], ...] = DEFAULT_RETRY_ON,
    attempts: int = 3,
    max_seconds: float = 30,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """async:重試後仍失敗 → raise ExternalAPIException。"""

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                async for attempt in AsyncRetrying(**_policy(service, retry_on, attempts, max_seconds)):
                    with attempt:
                        return await func(*args, **kwargs)
            except retry_on as e:
                raise _give_up(service, attempts, e) from e
            raise AssertionError("unreachable")  # pragma: no cover

        return wrapper

    return decorator


def retry_or_default[**P, R, D](
    service: str,
    default: D,
    *,
    retry_on: tuple[type[BaseException], ...] = DEFAULT_RETRY_ON,
    attempts: int = 3,
    max_seconds: float = 30,
) -> Callable[[Callable[P, R]], Callable[P, R | D]]:
    """sync:重試後仍失敗 → 記 log、回傳 default。"""

    def decorator(func: Callable[P, R]) -> Callable[P, R | D]:
        retried = retry_external(service, retry_on=retry_on, attempts=attempts, max_seconds=max_seconds)(func)

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | D:
            try:
                return retried(*args, **kwargs)
            except ExternalAPIException:
                return default

        return wrapper

    return decorator


def retry_or_default_async[**P, R, D](
    service: str,
    default: D,
    *,
    retry_on: tuple[type[BaseException], ...] = DEFAULT_RETRY_ON,
    attempts: int = 3,
    max_seconds: float = 30,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R | D]]]:
    """async:重試後仍失敗 → 記 log、回傳 default。"""

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R | D]]:
        retried = retry_external_async(service, retry_on=retry_on, attempts=attempts, max_seconds=max_seconds)(func)

        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | D:
            try:
                return await retried(*args, **kwargs)
            except ExternalAPIException:
                return default

        return wrapper

    return decorator
