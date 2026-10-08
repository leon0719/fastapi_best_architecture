# CLAUDE.md

本檔只列**每種任務都會踩到的硬規則**。特定任務的流程與模板在 `.claude/skills/` 與 `docs/`——
動手前先讀指向的檔案，不要憑記憶寫。

## 回應語言

**一律使用繁體中文，採台灣本地化用語**——用 程式碼／資料／函式／物件／介面／型別／快取／預設／效能，
不用 代碼／數據／函數／對象／接口／類型／緩存／默認／性能。即使以英文提問，回應仍用繁體中文。
程式碼識別字、檔名、目錄名、套件名保持英文不翻譯。

## 專案概要

FastAPI + SQLAlchemy 2.0（sync）+ Alembic + PostgreSQL + Redis + SQLAdmin，Python 3.13，套件管理用 `uv`（不用 pip／poetry）。
**Django-style app**：每個功能是一個自足的 `app/<name>/`。開發環境跑在 Docker（hot-reload）。

## 指令（`make help` 看全部）

- `make up` / `make down` / `make rebuild`（改 Dockerfile 或依賴後）/ `make logs-app`
- `make test` — 本機直接跑，**不需要 Docker**（in-memory SQLite）；`make test TEST=app/users/tests/test_views.py` 跑單檔
- `make all` — format + lint + type-check + test
- `make migrate` / `make makemigrations MSG="Add email to users"` — 在 app 容器內執行，需先 `make up` 且有 `.env.local`
- `make secrets-scan` / `make audit` / `make sast` — 與 CI 的安全檢查相同
- 加依賴：`uv add <pkg>` / `uv add --dev <pkg>`

## ⛔ 只能由人執行

不要自己執行——停下來，把完整指令交給使用者：
- 任何碰 prod 的操作：`make prod-*`、`docker-compose.yml`（prod compose）、連線到 prod DB／Redis
- `git push`（任何分支）、force-push、改寫已推送的歷史
- `make docker-clean`（清空本機 DB volume）
- 刪除或修改可能已在任何環境套用的 migration
- 呼叫真實的第三方 API／webhook、寄出真實 email

## 架構

```
Client → RequestLoggingMiddleware → router (app/<name>/views.py) → services.py → SQLAlchemy Session → PostgreSQL
                                          └─ 任何例外 → app/common/middleware/error_handler.py → BaseResponse
```

### 各檔職責

- **views.py** — 只做 HTTP：取依賴、呼叫 service、`return BaseResponse(data=...)`。不寫 ORM、不寫業務邏輯、不寫 try/except。
- **schemas.py** — Pydantic 請求／回應：`XxxCreate` / `XxxUpdate` / `XxxRead`（`from_attributes=True`）。
- **services.py** — 業務邏輯，`XxxService(db)`；commit／rollback 在這層；失敗一律 raise `AppException` 子類別。
- **models.py** — SQLAlchemy 2.0 `Mapped[...]`。**不要寫 `class Meta`**——那是 Django 寫法，SQLAlchemy 會直接忽略：
  index 用 `mapped_column(index=True)` 或 `__table_args__`，排序寫在查詢的 `order_by()`。
- **admin.py** — SQLAdmin `ModelView`；每個 model 都要註冊。
- **external_services.py** — 第三方 HTTP 呼叫**唯一**能放的地方（ruff `TID251` 強制）。需要時才建立。
- **utils.py** — 純函式，不碰 DB 與外部 API。需要時才建立。
- **tests/** — `test_services.py`（每條業務規則、每個例外分支）＋ `test_views.py`（狀態碼與回應 body）。

新 app 或新資源 → **scaffold-app** skill。**參考實作是 `app/users`**——照抄它的形狀，不要另創寫法。

### 回應格式（團隊契約，與 .NET 後端、前端 `axiosService` 相同）

```
成功 {"data": <T>, "error": null}
失敗 {"data": null, "error": {"code": <HTTP 狀態碼>, "message": "..."}}
```

- 所有 `/api` 端點：`response_model=BaseResponse[XxxRead]`，回傳 `BaseResponse(data=...)`（`app/common/schemas.py`）。
  刪除回 200 + `BaseResponse()`，不回 204。
- 錯誤一律 **raise**，由 `error_handler.py` 統一轉換（含 422 驗證錯誤、404 未知路由）。**不要手寫錯誤的 `JSONResponse`**。
- 例外對應：`NotFoundException` 404、`ValidationException` / `BadRequestException` 400、`UnauthorizedException` 401、
  `ForbiddenException` 403、`ConflictException` 409（例如名稱重複）、`ExternalAPIException` 502。新類別繼承 `AppException`。
- `/health/live`、`/health/ready` 是探針：不包 `BaseResponse`、不掛 `/api/v1`。

### 刻意的決策——不是技術債，不要在任務中順手「修正」

- **沒有 Repository 層**：Service 直接操作 Session（`views → services → DB`）。
- **同步 SQLAlchemy ＋ sync 端點**：FastAPI 會把 sync 端點丟進 threadpool。改 async 要整套換 driver 與 session，另案評估。
- **沒有 DI 容器**：依賴注入就是 FastAPI 的 `Depends`。
- **錯誤只有 HTTP 狀態碼，沒有字串錯誤碼**：對齊團隊 `BaseResponse` 契約。
- **JSON 欄位 snake_case**。

要改這些，另外提出來討論，不要夾在無關的任務裡做。

## 程式碼風格

- 行寬 120；ruff 規則在 `pyproject.toml`（含 `DTZ`、`S`、`BLE`、`TID`）。
- **時間一律 UTC**：Python 端用 timezone-aware（`datetime.now(UTC)`，ruff `DTZ` 會擋）；DB 欄位一律 `DateTime(timezone=True)`（timestamptz）。
- **只用 loguru `logger`**，不用 stdlib `logging`（ruff `TID251`）。前綴：`[Service]`、`[External]`；`[API]` 由 middleware 自動記錄，view 不手動 log。
  4xx 情境用 `logger.warning`，非預期錯誤用 `logger.exception`（自帶 stack trace）。
- 每行 log 帶上下文：資源 ID（`user_id: {id}`）、數量（`total: {n}`）、耗時（`duration: {d:.3f}s`）。
  **絕不 log 密碼、金鑰、token**（必要時遮罩成 `token[:10]...`）。
- `except Exception` 只在兩種地方合理：service 寫入失敗時 rollback 後 re-raise，以及快取／健康檢查失敗時降級。其他地方不吞例外。
- `# noqa` / `# type: ignore` 只能精準指定規則，並附理由。

## 資料庫

- **改 model 一定要產 migration**：`make makemigrations MSG="..."` → review 產出的檔案 → `make migrate`。CI 會擋 model 與 migration 不同步。
- 寫或改 migration 前先讀 `docs/database-migrations.md`（expand／contract、新增 NOT NULL 欄位的三步驟）。
- 新 model 要加進 `alembic/env.py` 的 import，否則 autogenerate 看不到它。
- 資料表 snake_case 複數（`users`、`chat_sessions`）。
- 列表查詢一定要 `order_by()`，否則 `offset` 分頁的結果不穩定。

## 設定與機密

- 所有設定都經過 `app/common/core/config.py` 的 `Config`；不要寫裸 `os.getenv()`。
- `.env.*` 不進版控（只有 `*.example`）。2026-07 曾外洩，見 `docs/security-incident-2026-07.md`。
- 新增機密欄位時，同步加進 `Config.security_issues()`，否則 `DEBUG=False` 的啟動檢查保護不到它。

## 開發流程

- **由內向外**：model → migration → schema → service ＋ 測試通過 → view ＋ 測試通過。不要從 view 開始。
- 團隊慣例不明確時**先問**，確認後一次套用到所有檔案。
- 收尾前跑 **check** skill（format、lint、mypy、pytest）。審查用 **conventions-review**（專案規則），可搭配內建 `/code-review`（找 bug）。
- 回報時沒實際跑過的項目標「未驗證」，不要打勾。

## Git

- Commit 格式 `<type>: <中文說明>`，type 只有 `feat`／`fix`／`docs`／`style`／`refactor`／`test`／`chore`。
  **說明用中文**、**不使用 scope**（不寫 `feat(auth):`）。
- 破壞性變更（呼叫端不改程式就會壞）在 type 後加 `!`：`feat!: 移除 GET /api/v1/users 的 name 欄位`。
- 分支 `<類型>/<描述>`，類型只有 `feat`／`fix`／`refactor`／`docs`／`chore`；從 `master` 切出、PR 回 `master`，不直接 commit 到 `master`／`main`。

## 文件（動手前先讀）

- `docs/database-migrations.md` — 改 model、寫 migration 之前
- `docs/redis-cache.md` — 使用 Redis 快取之前
- `docs/security-incident-2026-07.md` — 動到 `.env`、機密、admin 登入之前
