"""Locust 壓測:登入後的常見讀寫流量。手動/定期跑,刻意不進 CI(結果慢且受環境影響)。

準備(每個環境一次;make docker-clean 清掉 DB 後要重跑):
    make up && make migrate
    make perf-seed                         # 建帳號 + token → perf/.perf_users.json

執行:
    make perf                                           # web UI: http://localhost:8089
    make perf ARGS="--headless -u 20 -r 5 -t 2m"        # 無 UI,跑 2 分鐘

登入端點(/auth/exchange)有 rate limit(RATE_LIMIT_AUTH,依 IP),從單一壓測機打只會量到限速本身,
所以這裡用 seed 好的 session token,不壓登入。
"""

import itertools
import json
import os
import threading
from pathlib import Path

from locust import HttpUser, between, task

_USERS_FILE = Path(os.environ.get("PERF_USERS_FILE", "perf/.perf_users.json"))


def _load_pool() -> list[dict[str, str]]:
    if not _USERS_FILE.exists():
        raise RuntimeError(f"{_USERS_FILE} not found — run `make perf-seed` first")
    return json.loads(_USERS_FILE.read_text())


_pool = _load_pool()
_admins = [a for a in _pool if a["role"] == "admin"]
_cycle = itertools.cycle(_pool)
_lock = threading.Lock()


def _next_account() -> dict[str, str]:
    with _lock:  # itertools.cycle 本身不是 thread-safe
        return next(_cycle)


class ApiUser(HttpUser):
    """一般使用者:讀自己的資料、操作 chatbots。"""

    weight = 9
    wait_time = between(1, 3)
    headers: dict[str, str]

    def on_start(self) -> None:
        self.headers = {"Authorization": f"Bearer {_next_account()['token']}"}

    @task(5)
    def me(self) -> None:
        self.client.get("/api/v1/auth/me", headers=self.headers)

    @task(3)
    def list_chatbots(self) -> None:
        self.client.get("/api/v1/chatbots", headers=self.headers)

    @task(1)
    def create_and_delete_chatbot(self) -> None:
        resp = self.client.post(
            "/api/v1/chatbots",
            json={"name": f"perf-{os.urandom(4).hex()}", "description": "load test"},
            headers=self.headers,
        )
        if resp.status_code == 201:
            self.client.delete(f"/api/v1/chatbots/{resp.json()['data']['id']}", headers=self.headers)


class AdminUser(HttpUser):
    """admin:使用者清單與匯出(匯出吃 CPU,權重低)。"""

    weight = 1
    wait_time = between(3, 6)
    headers: dict[str, str]

    def on_start(self) -> None:
        if not _admins:
            raise RuntimeError("perf/.perf_users.json 沒有 admin 帳號,重跑 make perf-seed")
        self.headers = {"Authorization": f"Bearer {_admins[0]['token']}"}

    @task(4)
    def list_users(self) -> None:
        self.client.get("/api/v1/users", headers=self.headers)

    @task(1)
    def export_users(self) -> None:
        self.client.get("/api/v1/users/export", params={"format": "xlsx"}, headers=self.headers)
