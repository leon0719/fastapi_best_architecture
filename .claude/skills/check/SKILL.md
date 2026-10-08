---
name: check
description: 執行本專案完整的本機品質關卡——ruff format、ruff lint、mypy、pytest——並回報結果。Use when the user asks to "跑檢查"、"品質檢查"、"跑測試"、"確認會過"、"run checks"、"check the code"，以及完成任何變更、commit 之前。
---

# 品質關卡

依序執行，回報簡短的通過／失敗摘要。遇到第一個硬失敗就停下來並附上輸出；否則四項都跑完。

```bash
uv run ruff format .          # 格式化
uv run ruff check --fix .     # lint（自動修正）
uv run mypy .                 # 型別檢查（與 CI 相同範圍）
uv run pytest                 # 測試；不需要 Docker（in-memory SQLite）
```

## 依變更內容加跑

| 變更了什麼 | 加跑 |
|---|---|
| `models.py` | 確認有對應的 migration 檔，並已 `make migrate`（需 Docker）。model 與 migration 是否一致由 CI 的 drift check 在真 Postgres 上驗證 |
| `pyproject.toml` / `uv.lock` 的依賴 | `make audit`（pip-audit） |
| 涉及輸入處理、SQL、檔案、子行程 | `make sast`（bandit） |
| `.env*`、設定、機密相關 | `make secrets-scan`（gitleaks，需 Docker） |

## 備註

- CI 另外要求覆蓋率 ≥ 70%（`uv run pytest --cov=app --cov-fail-under=70`）。新增程式碼沒有測試，這關會擋。
- 單檔快速回饋：`uv run pytest app/<app>/tests/test_views.py`。
- ruff 規則與 per-file ignores 在 `pyproject.toml`。不要加全面性的 `# noqa`——優先修正；確定是框架慣用寫法，才加精準的 per-file ignore。
- `TID251` 報錯代表 import 放錯層（`httpx` 只能在 `external_services.py`、stdlib `logging` 只能在 `log_config.py`）。修正方式是搬到正確的層，不是加 noqa。

## 回報格式

摘要寫成：`format: OK · ruff: OK · mypy: OK · pytest: N passed`。
任何失敗都附上相關的幾行輸出並提出修正。沒跑的步驟寫 `⛔ 未執行：<原因>`，絕不寫 `OK`。
失敗的測試要判斷是「測試過時」還是「真的回歸」並說明是哪一種；不要自行決定忽略真的回歸。
