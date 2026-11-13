#!/bin/sh
# 容器進入點。用 exec 讓 uvicorn 取代 shell 成為 PID 1:docker stop 送的 SIGTERM 會直接送到 uvicorn,
# 它停止收新連線、等進行中的請求做完(最多 GRACEFUL_TIMEOUT 秒)、跑 lifespan shutdown(停排程、關 Redis)
# 才結束。若由 shell 或 `uv run` 包一層,訊號可能送不到,等滿 stop_grace_period 後被 SIGKILL。
#
# 有傳參數(例如 dev compose 的 --reload 指令、`docker compose run app alembic upgrade head`)就照跑那個指令。
set -e

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

# --proxy-headers / --forwarded-allow-ips "*":信任 nginx 傳來的 X-Forwarded-Proto,url_for 才會產生 https 網址
# (Google 登入的 redirect_uri)。可以信任所有來源,是因為 prod compose 只把 app 綁在 127.0.0.1,外面只有 nginx 連得到。
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers "${WEB_CONCURRENCY:-1}" \
  --proxy-headers \
  --forwarded-allow-ips "*" \
  --timeout-graceful-shutdown "${GRACEFUL_TIMEOUT:-25}" \
  --no-access-log
