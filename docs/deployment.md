# 部署、備份、CD

正式環境的操作一律由人執行(CLAUDE.md 的 Human-only operations)。這份說明架構與第一次設定。

## 架構

```
Internet ─▶ host nginx(TLS、安全 header、/admin 白名單)─▶ 127.0.0.1:APP_PORT ─▶ app 容器(uvicorn, WEB_CONCURRENCY workers)
                                                                             ├▶ db(postgres)
                                                                             ├▶ redis(快取、rate limit、排程鎖、長任務)
                                                         backup 容器 ─pg_dump─▶ S3(每日)
```

- `docker-compose.yml` 的 app 只綁 `127.0.0.1`,所有服務 log 輪替(json-file 10MB × 5)。
- 多 worker 安全:rate limit 計數、排程鎖、長任務狀態都在 Redis;session token 在 DB。

## Graceful shutdown

`docker-entrypoint.sh` 以 `exec uvicorn ...` 讓 uvicorn 成為 PID 1,SIGTERM 直接送到它:停止收新連線 → 等進行中的請求
(最多 `GRACEFUL_TIMEOUT`,預設 25 秒)→ lifespan shutdown(停排程、關 Redis)。compose 的 `stop_grace_period: 30s`
要比它長,否則會被 SIGKILL。給容器傳參數時(dev 的 `--reload`、`compose run app alembic ...`)entrypoint 直接執行該指令。

## nginx

範例在 `nginx/app.conf`(TLS、HSTS、nosniff、X-Frame-Options、Referrer-Policy、`client_max_body_size`、`/admin` 獨立 location)。
改完跑 `make nginx-check`(docker 內 `nginx -t`,CI 也會跑),再由人在主機上 `sudo cp` + `nginx -t` + `reload`。
`proxy_set_header X-Real-IP $remote_addr` 不能拿掉:rate limit 與稽核的 IP 靠它。

## 備份與還原

| 備份 | 何時 | 存哪 |
|---|---|---|
| `make prod-backup` | `prod-migrate` / `prod-up` / `prod-deploy` 前自動跑;db 沒在跑就略過,失敗就中止 | 主機 `~/backups/<repo 目錄名>/`,留最近 14 份 |
| compose `backup` 服務 | 啟動時一次,之後每 24 小時 | `BACKUP_S3_URI`(SSE-S3 加密) |

- S3 權限優先用 EC2 instance role(只給該 prefix 的 `s3:PutObject`),容器裡不放 key;保留期用 bucket lifecycle rule 設定
  (例如 365 天),腳本不刪檔。
- 格式是 `pg_dump -Fc`,還原:
  ```bash
  # 先停 app,避免還原期間有寫入
  docker compose --env-file .env.prod -f docker-compose.yml stop app
  docker compose --env-file .env.prod -f docker-compose.yml exec -T db \
    sh -c 'pg_restore --clean --if-exists -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backup.dump
  ```
- 每季至少演練一次還原到測試環境;備份沒還原過等於沒有備份。

## 手動部署

```bash
git pull --ff-only
make prod-deploy        # 備份 → build → migrate(一次性容器)→ up
curl -fsS http://127.0.0.1:8000/health/ready
```

migration 在新容器起來前跑,所以必須 expand-safe(見 `docs/database-migrations.md`)。

## CD(GitHub Actions)

`.github/workflows/ci.yml` 的 `deploy` job:所有 CI job 通過、push 到預設分支、且 repo variable `DEPLOY_ENABLED == 'true'`
才跑(模板預設不部署)。流程:SSH → `git pull --ff-only` → `make prod-deploy` → 輪詢 `/health/ready` 最多 30 次 × 5 秒,
失敗印 app 容器最後 100 行 log 並讓 job 失敗。

第一次設定(由人做):
1. 主機:clone repo、放好 `.env.prod`(`chmod 600`)、部署用帳號能跑 docker 與 make,且對 repo 有 pull 權限(deploy key)。
2. GitHub → Settings → Secrets:`DEPLOY_HOST`、`DEPLOY_USER`、`DEPLOY_SSH_KEY`(專用 key)、`DEPLOY_HOST_FINGERPRINT`。
3. Variables:`DEPLOY_PATH`、`DEPLOY_APP_PORT`(預設 8000)、最後 `DEPLOY_ENABLED=true`。
4. 建議在 Environments → production 設 required reviewers,部署前多一道人工確認。

## 壓測

`make perf-seed` 建帳號與 token(只在 DEBUG 環境)→ `make perf`(Locust,`perf/locustfile.py`)。不進 CI。
