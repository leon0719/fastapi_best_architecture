---
name: conventions-review
description: Review the current diff (or a named app) against THIS project's layering conventions and backend checklist — layering, BaseResponse format, exception mapping, migrations, UTC time, logging, secrets, tests. Use when the user asks to "review", "code review", "check conventions", "review my app/PR", "審查", "檢查慣例". Complements the built-in /code-review (which hunts general bugs) by enforcing project-specific rules.
---

# Conventions review

Scope: by default the working diff (`git diff` + untracked files). If the user names an app, review
`app/<name>/`. Read the changed files, then check each item below. Report grouped by severity
(Blocker / Should-fix / Nit) with `file:line`. List gaps only; do not restate what is fine. If you find
a definite correctness bug, suggest running the built-in `/code-review` separately.

The reference implementation is `app/users`; any difference in shape needs a reason.

## Layering

- [ ] `views.py` is HTTP only: no ORM queries, no business logic, no try/except, no hand-built error responses.
- [ ] Business logic is in `services.py`; failures raise an `AppException` subclass, never return an HTTP object.
- [ ] Failures the frontend must distinguish carry their own `reason=ErrorCode.X` (defined in `ErrorCode`, no ad-hoc strings).
- [ ] `get_db` is imported from `app.common.db.database`, not redefined in views.
- [ ] Third-party HTTP lives only in `external_services.py`, with a timeout, `[External]` logs, and failures
      converted to `ExternalAPIException` (`httpx` in the wrong layer is already a ruff `TID251` error — no need to re-check by hand).
- [ ] No empty files or abstraction layers created "for later".

## API responses

- [ ] `/api` endpoints use `response_model=BaseResponse[...]` and return `BaseResponse(data=...)`; delete returns 200 + `BaseResponse()`.
- [ ] Status codes mean what they say: 201 created, 404 not found, 409 duplicate/conflict, 400 business rule violated, 422 left to the framework.
- [ ] `XxxRead` leaks no internal field (hash, token, internal state).
- [ ] Routes are kebab-case plural nouns, IDs are path params; lists cap `skip` / `limit`.

## Database

- [ ] A model change has a migration whose content matches the model (not empty, no unexpected `drop_*`).
- [ ] New models are added to `alembic/env.py` and `app/main.py` (router + admin).
- [ ] Migrations are expand/contract: old and new code briefly coexist during deploy, so every migration
      must keep the previous version working; a NOT NULL column on an existing table goes nullable →
      backfill → add constraint (see `docs/database-migrations.md`).
- [ ] No `class Meta`; indexes match real query paths.
- [ ] Time columns are `DateTime(timezone=True)`; no naive datetimes in Python.
- [ ] List queries have `order_by()`; no N+1 when reading relations in a loop (`selectinload` / `joinedload` when needed).
- [ ] Multi-step writes share one transaction and roll back on failure.

## Logging and secrets

- [ ] loguru with `[Service]` / `[External]` prefixes and resource IDs; views do not log by hand.
- [ ] 4xx situations use `warning`; unexpected errors use `logger.exception`.
- [ ] No passwords, keys, or tokens in logs, responses, or exception messages.
- [ ] New secret settings are added to `Config.security_issues()`; no `.env*` file is committed.

## Tests and tooling

- [ ] Every business rule and exception branch of a new service is tested; new endpoints assert the status
      code and `BaseResponse` body, including 404 / 409 / 422.
- [ ] Tests never call a real third-party API.
- [ ] The **check** skill passes; no blanket `# noqa` / `# type: ignore`.
