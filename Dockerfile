FROM python:3.14-slim

WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安裝 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 複製依賴文件
COPY pyproject.toml uv.lock .python-version ./

# 使用 uv 安裝依賴（直接安裝到系統）
RUN uv sync --no-dev
# 依賴在 build 時就裝好;不設的話 CMD 的 `uv run` 每次啟動都會重新 sync,把 dev 依賴也裝進來(需連外網)
ENV UV_NO_SYNC=1

# 複製應用代碼
COPY app/ ./app/
# migration 也要進 image,prod 才能在 app 容器內 alembic upgrade head
COPY alembic.ini ./
COPY alembic/ ./alembic/

# 創建非 root 用戶
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]