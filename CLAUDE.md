# CLAUDE.md

This file holds only the hard rules every task touches. Task-specific procedures and templates live in
`.claude/skills/` and `docs/` — read the pointed-to file before working in that area instead of guessing.

## Response language

Always reply in Traditional Chinese (繁體中文) with Taiwan-localized wording, even when asked in English —
use 程式碼／資料／函式／物件／介面／型別／快取／預設／效能, never 代碼／數據／函數／對象／接口／類型／緩存／默認／性能.
Code identifiers, file names, directory names, and package names stay in English.

## Project Overview

FastAPI + SQLAlchemy 2.1 (sync) + Alembic + PostgreSQL + Redis + SQLAdmin, Python 3.15, `uv` as the
package manager (no pip/poetry). **Django-style apps**: each feature is a self-contained `app/<name>/`.
The dev environment runs in Docker (hot reload).

## Commands (`make help` lists all)

- `make up` / `make down` / `make rebuild` (after Dockerfile or dependency changes) / `make logs-app`
- `make test` — runs locally, **no Docker needed** (in-memory SQLite); `make test TEST=app/users/tests/test_views.py` for one file
- `make all` — format + lint + type-check + test
- `make migrate` / `make makemigrations MSG="Add email to users"` — run inside the app container; needs `make up` and `.env.local`
- `make secrets-scan` / `make audit` / `make sast` — the same security checks CI runs
- Add a dependency: `uv add <pkg>` / `uv add --dev <pkg>`

## Human-only operations ⛔

Never run these yourself — stop and hand the exact command to the user
(`.claude/settings.json` and `.claude/hooks/block-human-only.sh` also block them):
- Anything touching prod: `make prod-*`, `docker-compose.yml` (the prod compose file), connecting to a prod DB/Redis
- `git push` (any branch), force-push, rewriting published history
- `make docker-clean` (wipes the local DB volume)
- Deleting or rewriting migrations that may already be applied anywhere
- Calling real third-party APIs / webhooks, sending real email

## Architecture

```
Client → RequestLoggingMiddleware → router (app/<name>/views.py) → services.py → SQLAlchemy Session → PostgreSQL
                                          └─ any exception → app/common/middleware/error_handler.py → BaseResponse
```

### File responsibilities

- **views.py** — HTTP only: resolve dependencies, call the service, `return BaseResponse(data=...)`.
  No ORM, no business logic, no try/except.
- **schemas.py** — Pydantic request/response: `XxxCreate` / `XxxUpdate` / `XxxRead` (`from_attributes=True`).
- **services.py** — business logic, `XxxService(db)`; commit/rollback happen here; failures raise an
  `AppException` subclass.
- **models.py** — SQLAlchemy 2.1 `Mapped[...]`. **No `class Meta`** — that is Django; SQLAlchemy silently
  ignores it. Indexes: `mapped_column(index=True)` or `__table_args__`; ordering: `order_by()` in the query.
- **admin.py** — SQLAdmin `ModelView`; every model is registered.
- **external_services.py** — the *only* place third-party HTTP calls live (ruff `TID251`). Create it only when needed.
- **utils.py** — pure functions, no DB, no external APIs. Create it only when needed.
- **tests/** — `test_services.py` (every business rule and exception branch) + `test_views.py` (status code and response body).

New app or new resource → the **scaffold-app** skill. **The reference implementation is `app/users`** —
copy its shape, don't invent another.

### Response format (team contract, same as the Django Ninja template, the .NET backend, and frontend `shared/api`)

```
success {"data": <T>, "error": null}
failure {"data": null, "error": {"code": <HTTP status>, "message": "...", "reason": "<ErrorCode>" | null}}
```

- Every `/api` endpoint: `response_model=BaseResponse[XxxRead]`, returning `BaseResponse(data=...)`
  (`app/common/schemas.py`). Delete → 200 + `BaseResponse()`, not 204.
- Errors are always **raised** and converted by `error_handler.py` (including 422 validation errors and
  404 unknown routes). Never hand-build an error `JSONResponse`.
- Exception mapping: `NotFoundException` 404, `ValidationException` / `BadRequestException` 400,
  `UnauthorizedException` 401, `ForbiddenException` 403, `ConflictException` 409 (e.g. duplicate name),
  `ExternalAPIException` 502. New classes inherit `AppException`.
- `reason` is a stable machine-readable code (`ErrorCode` in `app/common/exceptions`) that lets the frontend
  tell causes apart under one status code and use it as an i18n key instead of matching `message`.
  Each exception class has a generic default; cases the frontend must distinguish carry their own code:
  `ConflictException(msg, reason=ErrorCode.USER_NAME_TAKEN)`. Add new codes to `ErrorCode`; never pass ad-hoc strings.
- `/health/live` and `/health/ready` are probes: not wrapped in `BaseResponse`, not under `/api/v1`.

### Deliberate decisions — not tech debt, don't "fix" them in a task

- **No Repository layer**: services use the Session directly (`views → services → DB`).
- **Sync SQLAlchemy + sync endpoints**: FastAPI runs sync endpoints in a threadpool. Going async means
  swapping the driver and session wholesale — a separate proposal.
- **No DI container**: dependency injection is FastAPI's `Depends`.
- **Errors are `BaseResponse` + a `reason` string code, not RFC 9457 Problem Details**: matches the team contract.
- **JSON fields are snake_case.**

To change any of these, raise it separately; never fold it into an unrelated task.

## Code Style

- Line length 120; ruff rules in `pyproject.toml` (incl. `DTZ`, `S`, `BLE`, `TID`).
- **Time is always UTC**: timezone-aware in Python (`datetime.now(UTC)`, enforced by ruff `DTZ`);
  DB columns are always `DateTime(timezone=True)` (timestamptz).
- **loguru `logger` only**, never stdlib `logging` (ruff `TID251`). Prefixes: `[Service]`, `[External]`;
  `[API]` is logged by the middleware, so views do not log by hand.
  4xx situations → `logger.warning`; unexpected errors → `logger.exception` (includes the stack trace).
- Every log line carries context: resource ID (`user_id: {id}`), counts (`total: {n}`), duration (`duration: {d:.3f}s`).
  **Never log passwords, keys, or tokens** (mask as `token[:10]...` if unavoidable).
- `except Exception` is legitimate in two places only: a service rolling back a failed write and
  re-raising, and degrading when cache/health checks fail. Nowhere else swallows exceptions.
- `# noqa` / `# type: ignore` must name the exact rule and give a reason.

## Database

- **A model change always needs a migration**: `make makemigrations MSG="..."` → review the generated
  file → `make migrate`. CI blocks model/migration drift.
- Read `docs/database-migrations.md` before writing or changing a migration (expand/contract, the three
  steps for adding a NOT NULL column).
- Add every new model to the imports in `alembic/env.py`, or autogenerate cannot see it.
- Table names are snake_case plural (`users`, `chat_sessions`).
- List queries always `order_by()`, otherwise `offset` pagination is unstable.

## Settings and secrets

- All settings flow through `Config` in `app/common/core/config.py`; no raw `os.getenv()`.
- `.env.*` is never committed (only `*.example`). It leaked in 2026-07 — see `docs/security-incident-2026-07.md`.
- When adding a secret field, also add it to `Config.security_issues()`, or the `DEBUG=False` startup
  check does not protect it.

## How to work

- **Inside out**: model → migration → schema → service + passing tests → view + passing tests. Never start from the view.
- When a team convention is unclear, **ask first**, then apply the answer to every file at once.
- Before you finish, run the **check** skill (format, lint, mypy, pytest). For review, **conventions-review**
  (project rules) complements the built-in `/code-review` (bugs).
- Report unverified items as unverified — never tick something you didn't run.

## Git

- Commit format `<type>: <description in Chinese>`; type is one of `feat` / `fix` / `docs` / `style` /
  `refactor` / `test` / `chore`. The description is written in Chinese. No scope (never `feat(auth):`).
- Breaking change (callers break unless they change code): add `!` after the type —
  `feat!: 移除 GET /api/v1/users 的 name 欄位`.
- Branch `<type>/<description>`, type one of `feat` / `fix` / `refactor` / `docs` / `chore`; branch from
  `master`, PR back to `master`, never commit directly to `master` / `main`.

## Docs — read before working in that area

- `docs/database-migrations.md` — before changing a model or writing a migration
- `docs/redis-cache.md` — before using the Redis cache
- `docs/security-incident-2026-07.md` — before touching `.env`, secrets, or admin login
