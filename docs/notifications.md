# 通知(Email、LINE、outbox)

實作在 `app/notifications/`。

## 規則

- **業務層只寫 outbox,不直接寄**:`NotificationService(db).enqueue_email(...)` / `enqueue_line(...)` 只加進 session,
  跟業務資料同一個 commit;資料 rollback 通知也不會送。排程(`OutboxDispatchTask`,每 `NOTIFICATION_RETRY_INTERVAL_SECONDS`)
  送出。
- 失敗重送:指數退避(間隔 × 2^(n-1),上限 6 小時),`retry_count` 達 `NOTIFICATION_MAX_RETRIES` 就填 `abandoned_at` 放棄並
  `logger.error`(Sentry 會收到)。後台 Notifications 可查 `last_error`。
- 保留期:已送出(`sent_at`)或已放棄(`abandoned_at`)超過 `NOTIFICATION_RETENTION_DAYS`(預設 30 天,0 = 永久)的列,
  由每日排程 `OutboxRetentionTask` 刪除;待送的列永遠不刪。payload 含收件人與內文(個資),不要調成永久保存而不設理由。
- 多 worker 不會重複送:每筆以 `SELECT … FOR UPDATE SKIP LOCKED` 取出;LINE 推播帶入列時產生的 `X-Line-Retry-Key`,
  重送時 LINE 端去重。Email 沒有這種機制:SMTP 回應遺失時可能重複寄,這是 at-least-once 的代價。

## Email(SMTP,stdlib smtplib)

- `SMTP_HOST` 留空 = 不寄、只寫 log(本機與測試預設如此,不會寄出真信)。587 走 STARTTLS,465 走 implicit TLS。
- 非正式環境(`ENV != prod`)標題自動加 `[DEV]`。
- 收件人與內文可能含個資:log 只記收件人數量,不記內容。

## LINE Messaging API

- 推播:`LINE_CHANNEL_ACCESS_TOKEN` 留空 = 不推播、只寫 log。
- Webhook:`POST /api/v1/line/webhook`,用 `LINE_CHANNEL_SECRET` 驗 `X-Line-Signature`(HMAC-SHA256 + `compare_digest`,
  對原始 body 計算);secret 未設定一律 401。事件處理寫在 `LineWebhookService.handle_event()`;有副作用的處理要以
  `webhookEventId` 去重(LINE 會重送)。LINE Developers Console 的 Webhook URL 填 `https://<api 網域>/api/v1/line/webhook`。

## 測試

用 `app/notifications/tests/fakes.py` 的 `FakeMailer` / `FakeLine` 注入 `NotificationService`;測 adapter 時以 monkeypatch
取代 `smtplib.SMTP` / `httpx.post`。絕不寄真信、不打真 API。
