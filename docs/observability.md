# 可觀測性與安全基礎(Request ID、Sentry、CORS、啟動檢查)

## Request ID

- `RequestLoggingMiddleware` 讀 `X-Request-ID`(只接受 `[A-Za-z0-9._-]{1,64}`),沒有就產生,存進 contextvar,回寫到回應 header
  (500 也有)。nginx 範例設定會把自己的 `$request_id` 往下傳。
- loguru 每一行都帶 request ID(格式欄 `{extra[request_id]}`,請求外是 `-`);`[API]` 那行另外帶 `user_id`
  (`current_user` 驗證成功時放進 `request.state`)。
- 稽核紀錄(`audit_logs.request_id`)與 Sentry 事件(tag `request_id`)也帶同一個值:使用者回報問題時請前端顯示/附上它。
- 背景工作要串 log 時,自己 `set_request_id()` 一個值(例如 job id)。

## Sentry

- `SENTRY_DSN` 有設才啟用(`app/common/core/log_config.py` 的 `setup_sentry()`)。`logger.error` / `logger.exception` 會成為事件,
  不用另外 `capture_exception`。
- 只送「哪裡壞了」:`send_default_pii=False`、`max_request_body_size="never"`、不送區域變數與 breadcrumb;
  `_scrub_event` 只留訊息第一行、遮 email 與 bearer token、拿掉 request header/cookie/query string。
  新增會進事件的資料前先想:這會不會把個資或金鑰送到境外服務?
- 驗證:本機在 `.env.local` 設 DSN 後打 `GET /debug/sentry`(只有 `DEBUG=True` 才註冊這個路由)。

## CORS

`CORS_ORIGINS`(逗號分隔)是唯一允許的前端來源;不開 `allow_credentials`(前端用 Bearer token,不靠 cookie)。
expose `Content-Disposition`(下載檔名)與 `X-Request-ID`。`DEBUG=False` 時 `*` 或非 https 的 origin 會擋下啟動。

## 啟動安全檢查

`Config.enforce_secure_settings()`:`DEBUG=False` 時任何不安全設定(placeholder、開發預設密碼、短金鑰、CORS `*`、
已啟用的選用功能缺機密)都會讓服務拒絕啟動;`DEBUG=True` 只警告。正式環境同時關閉 `/docs`、`/redoc`、`/openapi.json`。
新增機密設定時記得加進 `security_issues()`(選用功能:有啟用才檢查)。
