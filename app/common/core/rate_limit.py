"""Rate limit(slowapi),依來源 IP 計數。

用法(端點必須有 `request: Request` 參數,slowapi 從它取 IP):

    @router.post("/exchange")
    @limiter.limit(auth_rate)
    def exchange(request: Request, ...): ...

計數存在 Redis(RATE_LIMIT_STORAGE_URI 留空時用 REDIS_* 設定),多個 uvicorn worker / 多台機器共用
同一份計數;改成 memory:// 時每個 worker 各算各的,實際上限會變成「設定值 × worker 數」。
Redis 暫時連不上時退回各 worker 的記憶體計數(in_memory_fallback),不讓限速把登入整個擋掉。
"""

from slowapi import Limiter
from starlette.requests import Request

from app.common.core.config import config
from app.common.core.request_context import client_ip


def _client_key(request: Request) -> str:
    return client_ip(request) or "unknown"


def auth_rate() -> str:
    """登入相關端點的速率;用函式讓測試與設定變更在下一個請求就生效。"""
    return config.rate_limit_auth


limiter = Limiter(
    key_func=_client_key,
    storage_uri=config.rate_limit_storage_uri or config.redis_url,
    in_memory_fallback_enabled=True,
    enabled=config.rate_limit_enabled,
    key_prefix="ratelimit",
)
