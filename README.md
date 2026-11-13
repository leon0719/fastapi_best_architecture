# FastAPI Backend Template

FastAPI + SQLAlchemy 2.1 + Alembic + PostgreSQL + Redis + SQLAdmin 的後端模板，採 **Django-style app 結構**：
每個功能是一個自足的 `app/<name>/`（models／schemas／services／views／admin／tests）。

開發規則的正本是 [CLAUDE.md](./CLAUDE.md)（人與 AI 共用）；本檔只講怎麼跑起來。

## 需求

- Python 3.15、[uv](https://docs.astral.sh/uv/)
- Docker 與 Docker Compose（macOS 可用 colima）

## 快速開始

```bash
cp .env.local.example .env.local   # 把 CHANGEME 換成實際值
uv sync                            # 本機安裝依賴（給編輯器補完與本機測試用）
uvx pre-commit install             # commit 前自動跑 ruff、mypy、gitleaks
make up                            # 啟動 app + db + redis（hot-reload）
make migrate                       # 第一次啟動時建立資料表
```

第一個 admin：在 `/admin` 的 Users 建一筆（填 email、role 選 `admin`），設定好 `GOOGLE_OAUTH_*` 後用該 email 登入。
`/api/v1/users` 只有 admin 能呼叫；登入流程見 [docs/auth.md](./docs/auth.md)。

| 服務 | 網址 |
|---|---|
| API | http://localhost:8000 |
| API 文件 | http://localhost:8000/docs |
| Admin | http://localhost:8000/admin（帳密為 `.env.local` 的 `ADMIN_USERNAME`／`ADMIN_PASSWORD`） |

## 常用指令

```bash
make help                              # 所有指令
make logs-app                          # 看 API log
make test                              # 測試（不需要 Docker）
make test TEST=app/users/tests         # 只跑某個目錄或檔案
make all                               # format + lint + type-check + test
make makemigrations MSG="Add products" # 依 model 變更產生 migration
make secrets-scan / audit / sast       # 與 CI 相同的安全檢查
```

## 專案結構

```
app/
├── main.py                 # 進入點：middleware、router、admin 註冊、排程、健康檢查
├── common/
│   ├── core/               # config、log_config（loguru + Sentry）、redis、rate_limit、retry、request_context、admin 登入
│   ├── db/database.py      # engine、SessionLocal、Base、get_db、get_session_factory
│   ├── exceptions/         # AppException 與各 HTTP 錯誤
│   ├── middleware/         # 全域錯誤處理、request ID + 請求 log
│   ├── storage/            # S3 / 本機檔案儲存、上傳檢查
│   ├── exports.py          # xlsx / 中文 PDF / ZIP 下載
│   └── schemas.py          # BaseResponse[T]（統一回應格式）
├── users/                  # 參考實作：新功能照抄它的形狀（含角色、稽核、匯出範例）
├── auth/                   # Google OAuth + PKCE 登入、current_user、require_role
├── audit/                  # 稽核軌跡（AdminAuditMixin、record_audit）
├── jobs/                   # 輕量排程（PeriodicTask）與長任務（Redis 狀態）
├── notifications/          # Email、LINE、outbox 重送
├── holidays/               # 台灣工作日
├── llm/                    # LLM fallback chain 與用量（選用）
└── chatbots/
alembic/                    # migration
scripts/                    # 營運腳本（匯入假日、壓測帳號）
nginx/ · db_backup/ · perf/ # 站台設定範例、備份 sidecar、Locust 壓測
docs/                       # 特定主題的規範（見 CLAUDE.md 的 Docs 清單）
.claude/                    # AI 協作設定：skills 與權限
```

## API 回應格式

與團隊 .NET 後端、前端 `axiosService` 使用相同的 `BaseResponse<T>` 契約：

```json
{ "data": { "id": 1, "name": "alice" }, "error": null }
{ "data": null, "error": { "code": 409, "message": "User with name 'alice' already exists" } }
```

健康檢查 `/health/live`（程序存活）與 `/health/ready`（DB + Redis）是探針，不包這層格式。

## 環境設定

- `ENV` 決定載入 `.env.local` 或 `.env.prod`（`app/common/core/config.py`），未設定時是 `local`。
- 只有 `*.example` 進版控；`.env.local`／`.env.prod` 絕不 commit（2026-07 曾外洩，見 [docs/security-incident-2026-07.md](./docs/security-incident-2026-07.md)）。
- `DEBUG=False` 時，若 `ADMIN_SECRET_KEY`／`ADMIN_USERNAME`／`ADMIN_PASSWORD`／`DB_PASSWORD`／`REDIS_PASSWORD`
  仍是 placeholder 或開發預設值，服務會**拒絕啟動**並指出是哪一項。
- `DB_PASSWORD`／`REDIS_PASSWORD` 同時是 app 的連線密碼與 compose 初始化 `db`／`redis` 容器的密碼。
  volume 已用舊密碼初始化後再改密碼，兩邊不會自動同步：改回原密碼，或 `make docker-clean` 清空 volume 重建。

## Log

- Console：DEBUG 以上（`make logs-app`）
- `logs/app.log`：INFO 以上，10MB 輪替、保留 10 份
- `logs/error.log`：ERROR 以上，含完整 stack trace
- 每一行都帶 request ID（`X-Request-ID`，回應 header 也有）；每個 API 請求由 `RequestLoggingMiddleware` 自動記一行
  `[API] POST /api/v1/users - status: 201, duration: 0.032s, user_id: 1`
- 設 `SENTRY_DSN` 後 error 以上送 Sentry（已去識別化，見 `docs/observability.md`）

## 和 AI 一起開發

本專案已針對 Claude Code 設定好，clone 下來即可使用：

| 檔案 | 作用 |
|---|---|
| `CLAUDE.md` | 每回合都載入的硬規則：分層、回應格式、刻意決策、Git 規範、只能由人執行的操作 |
| `.claude/skills/scaffold-app` | 新增 app／資源的步驟、模板與完成清單（說「新增 products 模組」即觸發） |
| `.claude/skills/check` | 品質關卡：ruff、mypy、pytest |
| `.claude/skills/conventions-review` | 依專案規則審查 diff（搭配內建 `/code-review` 找 bug） |
| `.claude/settings.json` | 禁止 AI 執行 prod 指令、`git push`、讀取 `.env.prod` |
| `docs/*.md` | 特定任務才需要的細節，由 `CLAUDE.md` 指向 |

分層規則另外由 ruff `TID251` 強制（`httpx` 只能在 `external_services.py`、stdlib `logging` 只能在 `log_config.py`），AI 放錯層會當場報錯。

新增規則時先問「**是不是每種任務都會踩到**」：是就寫進 `CLAUDE.md`；不是就放進對應的 skill 或 `docs/`，並確認有地方指向它。

## 正式環境

```bash
make prod-deploy    # 備份 → build → migrate → up（使用 docker-compose.yml 與 .env.prod）
```

部署前確認 `.env.prod` 已填妥（`DEBUG=False` 時不安全的設定會擋下啟動）。nginx、備份還原、GitHub Actions 自動部署
（預設關閉，`DEPLOY_ENABLED=true` 才啟用）見 [docs/deployment.md](./docs/deployment.md)。

prod 操作一律由人執行；AI 被 `.claude/settings.json` 禁止執行 `make prod-*`。
