#!/bin/sh
# 異地備份:啟動時先備份一次,之後每 BACKUP_INTERVAL_SECONDS(預設 24 小時)一次,把資料庫傾印上傳 S3。
#
# - 權限優先用 EC2 instance role(容器裡不放任何 AWS key);非 EC2 主機才在 .env.prod 設
#   AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY(只給這個 bucket prefix 的 s3:PutObject)。
# - 保留期交給 bucket lifecycle rule(例如 db-backups/ 365 天後刪除),這裡不刪檔。
# - 資料庫連線用 libpq 環境變數(PGHOST、PGUSER、PGPASSWORD、PGDATABASE),由 docker-compose.yml 給。
# ponytail: 從容器啟動時間起算每 24 小時,不對齊固定時刻;要固定時刻再換 crond。
# ponytail: 失敗只寫在容器 log、不會告警;要告警就在成功後打一個 heartbeat(例如 Uptime Kuma push monitor)。
set -u

if [ -z "${BACKUP_S3_URI:-}" ]; then
  echo "$(date -u +%FT%TZ) BACKUP_S3_URI 未設定,異地備份停用(本機備份請用 make prod-backup)"
  exec sleep infinity  # 不讓 restart: always 一直重啟刷 log
fi

INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"
TMP="${TMPDIR:-/tmp}"
umask 077  # 傾印檔是未加密的完整資料庫

while true; do
  name="${PGDATABASE}_$(date -u +%Y%m%d_%H%M%S).dump"
  # 先寫到暫存檔再上傳:pg_dump 中途失敗才不會在 S3 留下不完整的備份。
  # -Fc(自訂格式,已壓縮)而不是 "pg_dump | gzip":sh 沒有 pipefail,pg_dump 失敗時 gzip 仍會成功。
  # 還原一律用 pg_restore(見 docs/deployment.md)。
  if pg_dump -Fc -f "$TMP/$name" \
    && aws s3 cp --only-show-errors --sse AES256 "$TMP/$name" "${BACKUP_S3_URI%/}/$name"; then
    echo "$(date -u +%FT%TZ) backup uploaded: ${BACKUP_S3_URI%/}/$name"
  else
    echo "$(date -u +%FT%TZ) backup FAILED: $name"
  fi
  rm -f "$TMP/$name"
  sleep "$INTERVAL"
done
