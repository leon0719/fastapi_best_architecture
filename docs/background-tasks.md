# 背景工作:排程、長任務、外部 API 重試、工作日

不引入 Celery。需要「重啟後續跑」、大量排隊或跨服務的工作流程時,再另提換 task queue。

## 週期排程(`app/jobs/scheduler.py`)

```python
# app/<name>/tasks.py
class DailyDigestTask(PeriodicTask):
    name = "reports.daily_digest"
    interval_seconds = 24 * 3600
    skip_non_working_days = True  # 台灣非工作日不跑(補班日照跑)

    def run(self, db: Session) -> str:  # 同步函式,在 threadpool 跑;commit 自己負責
        return f"sent: {ReportService(db).send_digest()}"
```

然後加進 `app/main.py` 的 `Scheduler([...])`。

- lifespan 啟動/停止;每輪自己開 session;例外只寫 log(`logger.exception` → Sentry)與 status,下一輪照常。
- 多 worker / 多機器:每輪先 `SET scheduler:lock:<name> NX EX interval`,搶到的才跑 → 全叢集約每個 interval 一次。
  Redis 連不上就跳過這輪。執行時間可能超過 interval 的任務,run() 本身要能承受重疊(例如 `FOR UPDATE SKIP LOCKED`)。
- 固定時刻(例如每天 09:00 台北):覆寫 `should_run(now)` 判斷時間,`lock_key(now)` 改成含日期、`lock_ttl()` 設 2 天。
- 狀態:`GET /api/v1/scheduler/tasks`(admin):本 worker 迴圈是否在跑 + 全叢集最後一次執行結果。
- `SCHEDULER_ENABLED=False` 可關閉(例如只想讓某一台跑)。
- 內建任務:通知 outbox 重送與保留期清理、稽核保留期清理、過期 token 清理。

## 長任務(`app/jobs/services.py`)

前端契約(`react-frontend-template`):`GET /api/v1/jobs/{id}` 與 `POST /api/v1/jobs/{id}/cancel` 回
`{id, status, progress, result, error}`,status ∈ `pending|running|succeeded|failed|cancelled`,progress 是 0–100 或 null。
只有發起者查得到/取消得了,其他人(含 admin)一律 404。

```python
@router.post("/reports", response_model=BaseResponse[JobRead], status_code=202)
def start_report(
    background: BackgroundTasks,
    user: Annotated[User, Depends(current_user)],
    jobs: Annotated[JobService, Depends(get_job_service)],
):
    job = jobs.create(kind="report", owner_id=user.id)
    background.add_task(jobs.run, job.id, build_report, user.id)
    return BaseResponse(data=JobRead.from_record(job))


def build_report(ctx: JobContext, user_id: int) -> dict:  # 自己開 session:get_session_factory()()
    for i, chunk in enumerate(chunks):
        ctx.check_cancelled()  # 取消旗標在這裡生效
        ...
        ctx.progress(100 * (i + 1) // len(chunks))
    return {"file_key": key}  # 存進 result,要能 JSON 序列化
```

狀態存 Redis(`JOB_TTL_SECONDS` 後過期);worker 重啟時跑到一半的 job 會停在 running。`error` 只放例外類別,不放訊息。

## 外部 API 重試(`app/common/core/retry.py`)

`external_services.py` 裡的呼叫用 decorator 包:

| decorator | 重試用完 |
|---|---|
| `retry_external` / `retry_external_async` | raise `ExternalAPIException`(502) |
| `retry_or_default` / `retry_or_default_async` | 記 log、回傳 `default` |

只重試 `retry_on` 列出的例外(httpx 呼叫通常是 `httpx.TransportError`);4xx、驗證失敗這類重試也不會好的錯誤不要列。
非冪等的呼叫(付款、寄信)只有在對方支援 idempotency key 時才重試(例如 LINE 的 `X-Line-Retry-Key`)。

## 台灣工作日(`app/holidays`)

- `holidays` 表只存例外日:平日放假(`is_holiday=True`)與週末補班(`False`);其他日子週一到週五上班。
- `is_working_day(db, date)`;排程用 `skip_non_working_days = True`。
- 每年公告後匯入:`make import-holidays YEAR=2027`(抓人事行政總處辦公日曆的 JSON 整理版,會連外網,由人執行);
  正式環境:`docker compose ... run --rm app python -m scripts.import_holidays 2027`。
  颱風假等臨時異動在後台 Holidays 手動加;匯入不覆寫已存在的日期。
