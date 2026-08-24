.PHONY: help install update all format lint type-check test coverage clean audit secrets-scan sast
.PHONY: up down build rebuild logs logs-app logs-db logs-redis db-up docker-clean
.PHONY: prod-up prod-down prod-build prod-logs
.PHONY: migrate makemigrations downgrade migration-history

# Docker compose files
# --env-file 讓 compose 變數替換(${DB_PASSWORD}、${REDIS_PASSWORD} 等)讀得到
# 對應環境的 .env 檔;檔案不存在時省略(例如 CI 只做 build)。
COMPOSE_DEV = docker compose $(if $(wildcard .env.local),--env-file .env.local) -f docker-compose-dev.yml
COMPOSE_PROD = docker compose $(if $(wildcard .env.prod),--env-file .env.prod) -f docker-compose.yml

# ===================
# Help
# ===================

help:
	@echo "========================================"
	@echo "  FastAPI Best Architecture"
	@echo "========================================"
	@echo ""
	@echo "開發環境 (Docker):"
	@echo "  make up                - 啟動開發容器 (日常開發用, hot-reload)"
	@echo "  make down              - 停止開發容器"
	@echo "  make build             - 僅建構開發映像 (不啟動)"
	@echo "  make rebuild           - 重新建構並啟動 (修改 Dockerfile 或 pyproject.toml 後使用)"
	@echo "  make db-up             - 只啟動 DB + Redis (本地跑 app 或 alembic 用)"
	@echo "  make logs              - 查看所有服務日誌"
	@echo "  make logs-app          - 查看 API 日誌"
	@echo "  make logs-db           - 查看資料庫日誌"
	@echo "  make logs-redis        - 查看 Redis 日誌"
	@echo ""
	@echo "生產環境 (Docker):"
	@echo "  make prod-build        - 建構生產映像"
	@echo "  make prod-up           - 啟動生產容器"
	@echo "  make prod-down         - 停止生產容器"
	@echo "  make prod-logs         - 查看生產日誌"
	@echo ""
	@echo "資料庫遷移 (Alembic, 在 app 容器內執行):"
	@echo "  make migrate           - 套用所有遷移 (alembic upgrade head)"
	@echo "  make makemigrations MSG=\"訊息\" - 自動產生遷移檔"
	@echo "  make downgrade         - 回退一個遷移"
	@echo "  make migration-history - 查看遷移歷史與目前版本"
	@echo ""
	@echo "程式碼品質:"
	@echo "  make all               - 執行所有檢查 (format + lint + type-check + test)"
	@echo "  make format            - 格式化程式碼 (ruff format)"
	@echo "  make lint              - 執行 ruff 檢查 (--fix)"
	@echo "  make type-check        - 執行 mypy 型別檢查"
	@echo "  make test              - 執行測試 (可用 TEST=\"path\" 指定測試)"
	@echo "  make coverage          - 執行測試並產生覆蓋率報告"
	@echo ""
	@echo "安全性 (對等 CI):"
	@echo "  make secrets-scan      - gitleaks 掃描機密外洩 (工作目錄 + git 歷史)"
	@echo "  make audit             - 掃描鎖定依賴的已知漏洞 (pip-audit)"
	@echo "  make sast              - 靜態掃描程式碼安全弱點 (bandit)"
	@echo ""
	@echo "其他:"
	@echo "  make install           - 安裝本地依賴"
	@echo "  make update            - 更新所有套件至最新版本"
	@echo "  make clean             - 清理快取檔案"
	@echo "  make docker-clean      - 停止並清理開發環境 Docker 資料卷"

# ===================
# Local Setup
# ===================

install:
	uv sync

update:
	@echo "Updating all packages..."
	uv lock --upgrade
	uv sync
	@echo "All packages updated!"

# ===================
# Development (Docker)
# ===================

up:
	$(COMPOSE_DEV) up -d
	@echo ""
	@echo "開發環境已啟動！"
	@echo "  API:      http://localhost:8000"
	@echo "  API Docs: http://localhost:8000/docs"
	@echo "  Admin:    http://localhost:8000/admin"
	@echo ""
	@echo "首次啟動請執行: make migrate"

down:
	$(COMPOSE_DEV) down

build:
	$(COMPOSE_DEV) build

rebuild:
	$(COMPOSE_DEV) up -d --build

db-up:
	$(COMPOSE_DEV) up -d db redis

logs:
	$(COMPOSE_DEV) logs -f

logs-app:
	$(COMPOSE_DEV) logs -f app

logs-db:
	$(COMPOSE_DEV) logs -f db

logs-redis:
	$(COMPOSE_DEV) logs -f redis

docker-clean:
	$(COMPOSE_DEV) down -v
	@echo "開發環境 Docker 資料卷已清理"

# ===================
# Production (Docker)
# ===================

prod-build:
	$(COMPOSE_PROD) build

prod-up:
	$(COMPOSE_PROD) up -d
	@echo ""
	@echo "生產環境已啟動！"
	@echo "  API: http://localhost:8000"

prod-down:
	$(COMPOSE_PROD) down

prod-logs:
	$(COMPOSE_PROD) logs -f

# ===================
# Database Migrations (Alembic, 在 app 容器內執行)
# ===================
# 一律用 docker compose exec 在 app 容器內跑,而不是本機 host 跑 —— 這樣
# DB_HOST=db 永遠正確,不需要另外維護一份 localhost 設定給本機直連用。

migrate: up
	$(COMPOSE_DEV) exec app uv run alembic upgrade head

makemigrations: up
ifndef MSG
	$(error 請提供遷移訊息: make makemigrations MSG="Add email to users")
endif
	$(COMPOSE_DEV) exec app uv run alembic revision --autogenerate -m "$(MSG)"

downgrade: up
	$(COMPOSE_DEV) exec app uv run alembic downgrade -1

migration-history: up
	$(COMPOSE_DEV) exec app uv run alembic history
	@echo ""
	$(COMPOSE_DEV) exec app uv run alembic current

# ===================
# Code Quality
# ===================

all:
	@echo "Running all code quality checks..."
	@echo ""
	@$(MAKE) format
	@echo ""
	@$(MAKE) lint
	@echo ""
	@$(MAKE) type-check
	@echo ""
	@$(MAKE) test
	@echo ""
	@echo "All checks completed!"

format:
	@echo "Formatting code with ruff..."
	@uv run ruff format .

lint:
	@echo "Linting code with ruff..."
	@uv run ruff check --fix .

type-check:
	@echo "Running type checks with mypy..."
	@uv run mypy app

test:
	@echo "Running tests..."
	@uv run pytest $(TEST)

coverage:
	@echo "Running tests with coverage..."
	@uv run pytest --cov=app --cov-report=term-missing --cov-report=html $(TEST)
	@echo ""
	@echo "HTML 報告已產生至 htmlcov/ 目錄"

# ===================
# Security (mirrors CI)
# ===================

# 與 CI 的 secrets job 跑同一個 image、同一份 .gitleaks.toml。
secrets-scan:
	@echo "Scanning for leaked secrets (working tree + git history)..."
	@docker run --rm -v "$(PWD):/repo" ghcr.io/gitleaks/gitleaks:latest \
		detect --source /repo --config /repo/.gitleaks.toml --redact --verbose --exit-code 1

# 與 CI 的 audit job 等價:掃 uv.lock 鎖定的執行期依賴。
audit:
	@echo "Auditing locked dependencies for known vulnerabilities..."
	@uv export --frozen --no-dev --no-emit-project --format requirements-txt -o requirements-audit.txt
	@uvx pip-audit --disable-pip -r requirements-audit.txt; status=$$?; rm -f requirements-audit.txt; exit $$status

# 與 CI 的 sast job 等價:靜態掃程式碼常見弱點模式(SQL/命令注入、硬編碼密碼等)。
sast:
	@echo "Running static analysis for security issues (bandit)..."
	@uvx bandit -r app -ll

# ===================
# Cleanup
# ===================

clean:
	@echo "Cleaning cache files..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@rm -rf htmlcov .coverage 2>/dev/null || true
	@echo "Cache cleaned!"
