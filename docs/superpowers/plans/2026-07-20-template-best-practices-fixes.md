# Template Best-Practices Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修正模板中五個偏離最佳實踐的問題:config.py 誤用 pydantic-settings、log_config 未接線、get_db 重複定義、create_all 與 Alembic 並存、缺少 ruff/mypy/pytest 工具鏈設定。

**Architecture:** 不改變 Django-style app 結構,只修正 common 層的基礎設施:設定改用 pydantic-settings 原生 env 綁定、logging 包成 `setup_logging()` 在 main.py 接線、`get_db` 集中到 `common/db/database.py`、啟動流程移除 `create_all` 僅依賴 Alembic、pyproject 補上工具設定並建立最小測試基礎(conftest + 測試)。

**Tech Stack:** Python 3.12+, FastAPI, pydantic-settings 2.x, SQLAlchemy 2.0 (sync), loguru, pytest, ruff, uv

## Global Constraints

- 套件管理一律用 `uv`(`uv run pytest`、`uv add --dev <pkg>`)。
- 不引入 repository 層;維持 views → services → DB 的簡單分流(CLAUDE.md 規則)。
- 不遷移 async SQLAlchemy(本次範圍外)。
- Loguru log 需維持既有格式與 `[Service]`/`[External]` prefix 慣例。
- 測試不得依賴執行中的 PostgreSQL/Redis(單元測試層級)。

---

### Task 1: 建立測試基礎(conftest + pytest 設定)

**Files:**
- Create: `tests/__init__.py`(空檔)
- Create: `tests/conftest.py`
- Modify: `pyproject.toml`(加 `[tool.pytest.ini_options]`)

**Interfaces:**
- Produces: pytest 可從專案根目錄以 `uv run pytest` 執行;`tests/` 為共用測試目錄(app 內 `app/*/tests/` 保留給各 app 自己的測試)。

- [ ] **Step 1: 在 pyproject.toml 加入 pytest 設定**

在 `pyproject.toml` 檔尾加入:

```toml
[tool.pytest.ini_options]
testpaths = ["tests", "app"]
python_files = ["test_*.py"]
addopts = "--strict-markers -q"
markers = [
    "unit: 不需外部服務的單元測試",
    "integration: 需要 DB/Redis 的整合測試",
]
```

- [ ] **Step 2: 建立 tests/__init__.py 與 tests/conftest.py**

`tests/__init__.py` 為空檔。`tests/conftest.py`:

```python
"""Shared pytest fixtures."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """TestClient without lifespan (no DB/Redis needed)."""
    from app.main import app

    return TestClient(app)
```

(延遲 import `app.main`,避免收集階段就觸發 app 載入;不使用 `with TestClient(...)`,因此不會執行 lifespan,不需要 DB/Redis。)

- [ ] **Step 3: 執行 pytest 確認可跑(0 個測試也算成功)**

Run: `uv run pytest`
Expected: `no tests ran` 或收集到 0 項,exit code 5 屬正常(尚無測試)。

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml tests/
git commit -m "test: add pytest configuration and shared conftest"
```

---

### Task 2: config.py 改用正規 pydantic-settings

**Files:**
- Modify: `app/common/core/config.py`(整檔重寫)
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: 無(第一個程式碼任務)。
- Produces: `Config` 類別欄位名稱不變(`db_host`、`redis_url` property 等),`config = Config()` 單例照舊 — 所有既有 import(`from app.common.core.config import config`)不需改動。

- [ ] **Step 1: 寫失敗測試**

`tests/test_config.py`:

```python
"""Config 應由 pydantic-settings 直接綁定環境變數,而非 os.getenv 預設值。"""

import pytest

pytestmark = pytest.mark.unit


def test_config_reads_env_vars(monkeypatch):
    monkeypatch.setenv("DB_HOST", "example-db")
    monkeypatch.setenv("DB_PORT", "15432")
    monkeypatch.setenv("DEBUG", "true")

    from app.common.core.config import Config

    cfg = Config()
    assert cfg.db_host == "example-db"
    assert cfg.db_port == 15432
    assert cfg.debug is True


def test_db_url_and_redis_url(monkeypatch):
    monkeypatch.setenv("DB_HOST", "h")
    monkeypatch.setenv("DB_USER", "u")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("DB_NAME", "n")
    monkeypatch.setenv("DB_PORT", "5432")

    from app.common.core.config import Config

    cfg = Config()
    assert cfg.db_url == "postgresql+psycopg://u:p@h:5432/n"
    assert cfg.redis_url.startswith("redis://:")


def test_no_os_getenv_in_config_source():
    """防止退回 os.getenv 反模式。"""
    import inspect

    from app.common.core import config as config_module

    source = inspect.getsource(config_module)
    assert "os.getenv" not in source
    assert "load_dotenv" not in source
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `uv run pytest tests/test_config.py -v`
Expected: `test_config_reads_env_vars` FAIL — 現行寫法在 module import 時就把 `os.getenv` 的值烙進類別預設,`monkeypatch.setenv` 後重新實例化 `Config()` 不會反映新環境變數(`test_no_os_getenv_in_config_source` 也 FAIL)。

- [ ] **Step 3: 重寫 config.py**

`app/common/core/config.py` 整檔改為:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Application settings, bound to environment variables by pydantic-settings.

    Field names map to env vars case-insensitively (db_host <- DB_HOST).
    Values in the real environment override those in .env.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Best FastAPI Architecture"
    debug: bool = False

    # Database configuration
    db_host: str = "db"
    db_port: int = 5432
    db_user: str = "postgres"
    db_password: str = "postgres"
    db_name: str = "fastapi_db"

    # Redis configuration
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = "redis_password"
    redis_db: int = 0
    redis_decode_responses: bool = True

    # Admin panel configuration (optional for migrations)
    admin_secret_key: str = ""
    admin_username: str = ""
    admin_password: str = ""

    @property
    def db_url(self) -> str:
        """PostgreSQL database URL"""
        return f"postgresql+psycopg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def redis_url(self) -> str:
        """Redis connection URL"""
        return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"


config = Config()
```

- [ ] **Step 4: 執行測試確認通過**

Run: `uv run pytest tests/test_config.py -v`
Expected: 3 PASS。

- [ ] **Step 5: 確認 alembic/env.py 與其他呼叫端仍正常 import**

Run: `uv run python -c "from app.common.core.config import config; print(config.db_url)"`
Expected: 印出 DB URL,無例外。

- [ ] **Step 6: Commit**

```bash
git add app/common/core/config.py tests/test_config.py
git commit -m "fix: use native pydantic-settings env binding in Config"
```

---

### Task 3: 抽共用 get_db 到 common/db

**Files:**
- Modify: `app/common/db/database.py`(加 `get_db`)
- Modify: `app/users/views.py:13-19`(刪本地 `get_db`,改 import)
- Modify: `app/chatbots/views.py:13-18`(同上)
- Test: `tests/test_database.py`

**Interfaces:**
- Consumes: `SessionLocal`(既有)。
- Produces: `app.common.db.database.get_db()` — generator dependency,yield `Session`,finally close。兩個 views 改為 `from app.common.db.database import get_db`。

- [ ] **Step 1: 寫失敗測試**

`tests/test_database.py`:

```python
"""get_db 應集中定義於 common/db,而非各 app 重複定義。"""

import inspect

import pytest

pytestmark = pytest.mark.unit


def test_get_db_lives_in_common():
    from app.common.db.database import get_db

    assert inspect.isgeneratorfunction(get_db)


def test_views_reuse_common_get_db():
    from app.chatbots import views as chatbot_views
    from app.common.db.database import get_db
    from app.users import views as user_views

    assert user_views.get_db is get_db
    assert chatbot_views.get_db is get_db
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `uv run pytest tests/test_database.py -v`
Expected: FAIL — `cannot import name 'get_db' from app.common.db.database`。

- [ ] **Step 3: 在 database.py 加入 get_db**

`app/common/db/database.py` 檔尾(class Base 之後)加入:

```python
def get_db():
    """FastAPI dependency that yields a database session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 4: 改寫兩個 views 的 import 並刪除本地 get_db**

`app/users/views.py`:刪除第 13-19 行的本地 `get_db` 定義,並把

```python
from app.common.db.database import SessionLocal
```

改為

```python
from app.common.db.database import get_db
```

`app/chatbots/views.py`:同樣刪除第 13-18 行本地 `get_db`,把 `from app.common.db.database import SessionLocal` 改為 `from app.common.db.database import get_db`。兩檔其餘內容(`get_user_service` / `get_chatbot_service` 的 `Depends(get_db)`)不變。

- [ ] **Step 5: 執行測試確認通過**

Run: `uv run pytest tests/test_database.py -v`
Expected: 2 PASS。

- [ ] **Step 6: Commit**

```bash
git add app/common/db/database.py app/users/views.py app/chatbots/views.py tests/test_database.py
git commit -m "refactor: centralize get_db dependency in common/db"
```

---

### Task 4: 接上 log_config(包成 setup_logging 並在 main.py 呼叫)

**Files:**
- Modify: `app/common/core/log_config.py`(module-level side effects 包成函式)
- Modify: `app/main.py`(import 並呼叫)
- Test: `tests/test_logging.py`

**Interfaces:**
- Consumes: 無。
- Produces: `app.common.core.log_config.setup_logging() -> None`,冪等(重複呼叫不重複加 handler)。`app/main.py` 在建立 `FastAPI` app 前呼叫一次。

- [ ] **Step 1: 寫失敗測試**

`tests/test_logging.py`:

```python
"""log_config 必須實際被 main.py 接線,且 setup_logging 可安全重複呼叫。"""

import inspect

import pytest

pytestmark = pytest.mark.unit


def test_setup_logging_exists_and_idempotent():
    from app.common.core.log_config import setup_logging

    setup_logging()
    setup_logging()  # 第二次呼叫不得噴錯或重複累加 handler


def test_main_wires_up_logging():
    from app import main

    source = inspect.getsource(main)
    assert "setup_logging()" in source
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `uv run pytest tests/test_logging.py -v`
Expected: FAIL — `cannot import name 'setup_logging'`。

- [ ] **Step 3: 重構 log_config.py**

`app/common/core/log_config.py` 整檔改為(設定內容不變,只是包進函式並加冪等旗標):

```python
import logging
import os
import sys
from pathlib import Path

from loguru import logger

_configured = False


def setup_logging() -> None:
    """Configure loguru handlers and silence noisy stdlib loggers.

    Idempotent: calling more than once has no effect.
    """
    global _configured
    if _configured:
        return
    _configured = True

    # Remove default handler
    logger.remove()

    # Force color output in Docker (works with docker compose logs)
    os.environ.setdefault("COLORTERM", "truecolor")
    os.environ.setdefault("TERM", "xterm-256color")

    # Disable SQLAlchemy SQL query logging (we use loguru for application logs)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

    # Disable Uvicorn access logs (we have RequestLoggingMiddleware)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)

    # Console output with colors (always colorize in Docker)
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="DEBUG",
        colorize=True,
    )

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    # File handler - all logs with rotation
    logger.add(
        logs_dir / "app.log",
        rotation="10 MB",
        retention="10 files",
        compression="zip",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        enqueue=True,
    )

    # Separate error log file
    logger.add(
        logs_dir / "error.log",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        backtrace=True,
        diagnose=True,
        enqueue=True,
    )


if __name__ == "__main__":
    setup_logging()
    logger.info("Hello, World!")
    logger.debug("Hello, World!")
    logger.warning("Hello, World!")
    logger.error("Hello, World!")
    logger.critical("Hello, World!")
```

- [ ] **Step 4: 在 main.py 接線**

`app/main.py` 的 import 區加入:

```python
from app.common.core.log_config import setup_logging
```

並在 import 區之後、`@asynccontextmanager` 之前呼叫:

```python
# Configure logging before anything logs
setup_logging()
```

- [ ] **Step 5: 執行測試確認通過**

Run: `uv run pytest tests/test_logging.py -v`
Expected: 2 PASS。

- [ ] **Step 6: Commit**

```bash
git add app/common/core/log_config.py app/main.py tests/test_logging.py
git commit -m "fix: wire up loguru log configuration via setup_logging()"
```

---

### Task 5: 啟動流程移除 create_all,僅依賴 Alembic

**Files:**
- Modify: `app/main.py`(lifespan 移除 `init_db()` 呼叫)
- Delete: `app/common/db/init_db.py`
- Modify: `CLAUDE.md`(架構樹移除 init_db.py,說明改用 alembic)
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: Task 4 之後的 `app/main.py`。
- Produces: `app.main.app` 的 lifespan 不再建表;建表唯一途徑為 `uv run alembic upgrade head`。

- [ ] **Step 1: 寫失敗測試**

`tests/test_main.py`:

```python
"""啟動流程不得用 create_all 建表(schema 由 Alembic 管理)。"""

import inspect

import pytest

pytestmark = pytest.mark.unit


def test_lifespan_does_not_create_tables():
    from app import main

    source = inspect.getsource(main)
    assert "init_db" not in source
    assert "create_all" not in source


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `uv run pytest tests/test_main.py -v`
Expected: `test_lifespan_does_not_create_tables` FAIL(main.py 仍呼叫 `init_db()`);`test_health_endpoint` PASS。

- [ ] **Step 3: 修改 main.py 的 lifespan**

刪除 import:

```python
from app.common.db.init_db import init_db
```

lifespan 內把

```python
    # Startup: Initialize database
    logger.info("[Startup] Initializing database...")
    init_db()
    logger.info("[Startup] Database initialized")
```

改為

```python
    # Schema is managed by Alembic — run `uv run alembic upgrade head` to migrate.
    logger.info("[Startup] Starting application (schema managed by Alembic)")
```

- [ ] **Step 4: 刪除 init_db.py**

```bash
git rm app/common/db/init_db.py
```

Run: `rg -l "init_db" --glob '!docs/**'`
Expected: 只剩 CLAUDE.md(下一步處理);若 `app/common/db/__init__.py` 有 re-export `init_db`,一併移除該行。

- [ ] **Step 5: 更新 CLAUDE.md**

`CLAUDE.md` 架構樹中刪除 `│   └── init_db.py      # Database initialization` 一行;若「Adding New App」或其他段落提及 init_db/create_all,改為說明「schema 一律由 Alembic 管理(`uv run alembic upgrade head`)」。

- [ ] **Step 6: 執行測試確認通過**

Run: `uv run pytest tests/test_main.py -v`
Expected: 2 PASS。

- [ ] **Step 7: Commit**

```bash
git add app/main.py app/common/db/ CLAUDE.md tests/test_main.py
git commit -m "fix: remove create_all from startup; Alembic owns the schema"
```

---

### Task 6: 補 ruff / mypy 工具鏈設定

**Files:**
- Modify: `pyproject.toml`(加 `[tool.ruff]`、`[tool.mypy]`,dev 依賴加 mypy)
- Modify: 修 ruff/mypy 掃出的既有違規(預期集中在 import 排序與小型風格問題)

**Interfaces:**
- Consumes: 前面所有任務完成後的程式碼。
- Produces: `uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy app` 全數通過,可直接放進未來 CI。

- [ ] **Step 1: 加入 mypy dev 依賴**

Run: `uv add --dev mypy`
Expected: pyproject dev group 出現 `mypy>=...`。

- [ ] **Step 2: 在 pyproject.toml 加入工具設定**

檔尾加入(參考 django-ninja-project-tree 的規則集,依本專案調整):

```toml
[tool.ruff]
line-length = 120
target-version = "py312"
exclude = ["alembic/versions"]

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "N",   # pep8-naming
    "UP",  # pyupgrade
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "SIM", # flake8-simplify
    "T20", # no print statements (use loguru)
    "DTZ", # timezone-aware datetimes
]

[tool.ruff.lint.per-file-ignores]
"app/*/tests/*" = ["S", "DTZ"]
"tests/*" = ["S", "DTZ"]
"alembic/*" = ["I"]

[tool.mypy]
python_version = "3.12"
check_untyped_defs = true
warn_unused_ignores = true
exclude = ["alembic/versions"]
ignore_missing_imports = true
```

- [ ] **Step 3: 執行 ruff 並修正違規**

Run: `uv run ruff check . --fix` 然後 `uv run ruff format .`
Expected: 自動修正 import 排序等;殘餘違規逐一手動修正(不可用 `# noqa` 掩蓋,除非有明確理由並附註解)。

- [ ] **Step 4: 執行 mypy 並修正**

Run: `uv run mypy app`
Expected: 0 errors。若有少量既有型別問題,以最小修改補上型別註記。

- [ ] **Step 5: 全部測試 + lint 最終確認**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy app`
Expected: 全部通過。

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock app/ tests/
git commit -m "chore: add ruff and mypy configuration; fix violations"
```
