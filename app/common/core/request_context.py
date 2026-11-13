"""每個請求的脈絡:request ID(contextvar)與來源 IP。

request ID 由 RequestLoggingMiddleware 設定,loguru 每一行、Sentry 事件、500 回應都會帶上,
前端回報問題時給 X-Request-ID 就能在 log 撈到同一個請求的每一行。
"""

import re
import uuid
from contextvars import ContextVar

from starlette.requests import Request

REQUEST_ID_HEADER = "X-Request-ID"

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
# 前端/上游 proxy 帶來的 ID 會寫進 log,只接受安全字元與合理長度,避免 log injection
_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


def get_request_id() -> str | None:
    return _request_id.get()


def set_request_id(incoming: str | None = None) -> str:
    """沿用合法的上游 ID,否則產生新的;回傳實際使用的值。"""
    request_id = incoming if incoming and _SAFE_ID.fullmatch(incoming) else uuid.uuid4().hex
    _request_id.set(request_id)
    return request_id


def client_ip(request: Request) -> str | None:
    """操作者的真實 IP:優先讀 nginx 設的 X-Real-IP,沒有(本機直連)才退回連線對端。

    不直接用 request.client.host:uvicorn 以 --proxy-headers 啟動時,client 會被換成
    X-Forwarded-For 最左邊那段,而 nginx 的 $proxy_add_x_forwarded_for 只是在使用者送來的值後面追加,
    使用者自己帶一個就能偽造。X-Real-IP 由 nginx 以 $remote_addr 無條件覆寫,且 prod 的 app 只綁
    127.0.0.1,除了 nginx 沒人送得進來,所以可信。沒有 nginx 直接對外時,這個 header 就不可信。
    """
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip[:45]  # IPv6 文字表示最長 45 字元
    return request.client.host if request.client else None
