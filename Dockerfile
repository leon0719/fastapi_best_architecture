FROM python:3.15-slim

WORKDIR /app

# 安裝系統依賴
# fonts-arphic-uming:PDF 匯出嵌入的繁體中文字型(TrueType 外框;reportlab 不支援 Noto CJK 的 CFF 外框)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    fonts-arphic-uming \
    && rm -rf /var/lib/apt/lists/*

# 安裝 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 複製依賴文件
COPY pyproject.toml uv.lock .python-version ./

# 使用 uv 安裝依賴到 /app/.venv。要用 LLM 模組時加上 --extra llm(anthropic / openai / google-genai)。
RUN uv sync --frozen --no-dev
# 依賴在 build 時就裝好;不設的話 `uv run` 每次啟動都會重新 sync,把 dev 依賴也裝進來(需連外網)
ENV UV_NO_SYNC=1
# venv 的執行檔(uvicorn、alembic)直接可用,entrypoint 不需要經過 uv run
ENV PATH="/app/.venv/bin:$PATH"

# 複製應用代碼
COPY app/ ./app/
# migration 也要進 image,prod 才能在 app 容器內 alembic upgrade head
COPY alembic.ini ./
COPY alembic/ ./alembic/
# 營運腳本(例如 python -m scripts.import_holidays 2027)
COPY scripts/ ./scripts/
COPY docker-entrypoint.sh ./

# 創建非 root 用戶
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
