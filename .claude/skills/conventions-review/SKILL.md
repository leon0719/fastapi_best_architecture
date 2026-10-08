---
name: conventions-review
description: 依本專案的分層慣例與後端檢查清單審查目前的 diff（或指定的 app）——分層、BaseResponse 回應格式、例外對應、migration、時間 UTC、logging、機密、測試。Use when the user asks to "審查"、"review"、"code review"、"檢查慣例"、"review my app/PR"。與內建 /code-review（找一般 bug）互補，這個只管專案規則。
---

# 專案慣例審查

範圍：預設是工作目錄的 diff（`git diff` ＋ 未追蹤檔案）。使用者指定 app 時，審查 `app/<name>/`。
讀完變更的檔案後逐項對照下列清單。依嚴重度分組回報（Blocker／Should-fix／Nit），附 `file:line`。
只列出缺口，不重述沒問題的地方。發現確定的正確性 bug，建議另外跑內建的 `/code-review`。

參考實作是 `app/users`；跟它形狀不同的地方都要有理由。

## 分層

- [ ] `views.py` 只做 HTTP：沒有 ORM 查詢、沒有業務邏輯、沒有 try/except、沒有手寫錯誤回應。
- [ ] 業務邏輯在 `services.py`；失敗 raise `AppException` 子類別，不回傳 HTTP 物件。
- [ ] `get_db` 從 `app.common.db.database` import，沒有在 views 重新定義。
- [ ] 第三方 HTTP 只在 `external_services.py`，有 timeout、`[External]` log、失敗轉 `ExternalAPIException`
      （`httpx` 放錯層 ruff `TID251` 已經會擋，不必人工再查）。
- [ ] 沒有為「以後可能用到」而建立的空檔案或抽象層。

## API 回應

- [ ] `/api` 端點的 `response_model` 是 `BaseResponse[...]`，回傳 `BaseResponse(data=...)`；刪除回 200 ＋ `BaseResponse()`。
- [ ] 狀態碼語意正確：201 新增、404 找不到、409 重複／衝突、400 業務規則不符、422 由框架處理。
- [ ] `XxxRead` 沒有洩漏不該對外的欄位（hash、token、內部狀態）。
- [ ] 路由是 kebab-case 複數名詞、ID 用路徑參數；列表有 `skip`／`limit` 上限。

## 資料庫

- [ ] model 有改就有 migration，且 migration 內容與 model 相符（不是空的、沒有意外的 `drop_*`）。
- [ ] 新 model 已加進 `alembic/env.py`、`app/main.py`（router ＋ admin）。
- [ ] Migration 是 expand／contract：部署期間新舊版本會短暫並存，每個 migration 都要讓上一版程式碼繼續運作；
      在既有表新增 NOT NULL 欄位要 nullable → backfill → 加約束（見 `docs/database-migrations.md`）。
- [ ] 沒有 `class Meta`；index 對應實際查詢路徑。
- [ ] 時間欄位是 `DateTime(timezone=True)`；Python 端沒有 naive datetime。
- [ ] 列表查詢有 `order_by()`；迴圈內存取關聯沒有 N+1（需要時用 `selectinload`／`joinedload`）。
- [ ] 多步驟寫入在同一個交易裡，失敗會 rollback。

## Logging 與機密

- [ ] 用 loguru，前綴 `[Service]`／`[External]`，帶資源 ID；view 沒有手動 log。
- [ ] 4xx 情境 `warning`、非預期錯誤 `logger.exception`。
- [ ] log、回應、例外訊息裡沒有密碼、金鑰、token。
- [ ] 新的機密設定已加進 `Config.security_issues()`；沒有 `.env*` 被加進版控。

## 測試與工具

- [ ] 新 service 每條業務規則、每個例外分支都有測試；新端點驗狀態碼與 `BaseResponse` body，含 404／409／422。
- [ ] 測試沒有打真實第三方 API。
- [ ] **check** skill 通過；沒有全面性的 `# noqa`／`# type: ignore`。
