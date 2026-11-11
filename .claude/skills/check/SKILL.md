---
name: check
description: Run the full local quality gate for this project — ruff format, ruff lint, mypy, and pytest — and summarize results. Use when the user asks to "run checks", "check the code", "make sure it passes", "跑檢查", "品質檢查", "跑測試", "確認會過", or before committing/finishing a change.
---

# Quality gate

Run these in order and report a concise pass/fail summary. Stop at the first hard failure and attach
its output; otherwise run all four.

```bash
uv run ruff format .          # format
uv run ruff check --fix .     # lint (auto-fix)
uv run mypy .                 # type check (same scope as CI)
uv run pytest                 # tests; no Docker needed (in-memory SQLite)
```

## Extra checks by what changed

| What changed | Also run |
|---|---|
| `models.py` | Confirm a matching migration file exists and `make migrate` ran (needs Docker). Model/migration consistency is verified by CI's drift check on real Postgres |
| Dependencies in `pyproject.toml` / `uv.lock` | `make audit` (pip-audit) |
| Input handling, SQL, files, subprocesses | `make sast` (bandit) |
| `.env*`, settings, secrets | `make secrets-scan` (gitleaks, needs Docker) |

## Notes

- CI also requires coverage ≥ 70% (`uv run pytest --cov=app --cov-fail-under=70`). New code without
  tests fails that gate.
- Fast single-file feedback: `uv run pytest app/<app>/tests/test_views.py`.
- ruff rules and per-file ignores are in `pyproject.toml`. Do not add blanket `# noqa` — fix it first;
  add a precise per-file ignore only for a genuine framework idiom.
- A `TID251` error means an import sits in the wrong layer (`httpx` only in `external_services.py`,
  stdlib `logging` only in `log_config.py`). The fix is moving it to the right layer, not a noqa.

## Report format

Summarize as: `format: OK · ruff: OK · mypy: OK · pytest: N passed`.
For any failure, attach the relevant lines and propose a fix. A step that was not run is written
`⛔ not run: <reason>`, never `OK`.
For a failing test, decide whether the test is stale or the failure is a real regression and say which;
never decide on your own to ignore a real regression.
