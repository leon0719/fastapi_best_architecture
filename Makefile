.PHONY: pre-commit-install pre-commit
.PHONY: help install update all format lint type-check test coverage clean audit secrets-scan sast
.PHONY: up down build rebuild logs logs-app logs-db logs-redis db-up docker-clean
.PHONY: prod-up prod-down prod-build prod-logs prod-backup prod-migrate prod-deploy prod-llm-cost
.PHONY: migrate makemigrations downgrade migration-history
.PHONY: import-holidays nginx-check perf perf-seed llm-cost

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
	@echo "  make prod-backup       - 備份生產 DB (pg_dump -Fc,留最近 14 份)"
	@echo "  make prod-migrate      - 先備份,再用新映像套用 migration (在 prod-up 之前)"
	@echo "  make prod-up           - 先備份,再啟動生產容器"
	@echo "  make prod-deploy       - 備份 → build → migrate → up (CD 用這個)"
	@echo "  make prod-down         - 停止生產容器"
	@echo "  make prod-logs         - 查看生產日誌"
	@echo "  make prod-llm-cost     - 生產環境每月 LLM 花費"
	@echo ""
	@echo "資料庫遷移 (Alembic, 在 app 容器內執行):"
	@echo "  make migrate           - 套用所有遷移 (alembic upgrade head)"
	@echo "  make makemigrations MSG=\"訊息\" - 自動產生遷移檔"
	@echo "  make downgrade         - 回退一個遷移"
	@echo "  make migration-history - 查看遷移歷史與目前版本"
	@echo ""
	@echo "營運 / 維運:"
	@echo "  make import-holidays YEAR=2027 - 抓政府辦公日曆匯入假日 (會連外網,開發環境)"
	@echo "  make llm-cost          - 開發環境每月 LLM 花費 (token 與美金,按模型)"
	@echo "  make nginx-check       - 用 docker 跑 nginx -t 驗證 nginx/app.conf"
	@echo "  make perf-seed         - 建立壓測帳號與 token (寫到 perf/.perf_users.json)"
	@echo "  make perf [ARGS=...]   - Locust 壓測 (預設開 web UI: http://localhost:8089)"
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
	@echo "  make pre-commit-install - 安裝 git pre-commit hook (commit 時自動跑 ruff/mypy/gitleaks)"
	@echo "  make pre-commit        - 對所有檔案跑一次 pre-commit hook"
	@echo "  make update            - 更新所有套件至最新版本"
	@echo "  make clean             - 清理快取檔案"
	@echo "  make docker-clean      - 停止並清理開發環境 Docker 資料卷"

# ===================
# Local Setup
# ===================

install:
	uv sync

# pre-commit 不在 dev 依賴裡，用 uvx 臨時跑
pre-commit-install:
	uvx pre-commit install

pre-commit:
	uvx pre-commit run --all-files

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

# migration 沒有回頭路,所以 prod-migrate / prod-up 前一律先備份;備份失敗就中止。
# 用 pg_dump 自訂格式(-Fc,已壓縮)而不是 "pg_dump | gzip":make 的 sh 沒有 pipefail,
# pg_dump 失敗時 gzip 仍會成功,留下一個看起來正常的空備份。先寫 .partial 再改名也是同樣的考量。
# 傾印檔是未加密的完整資料庫:umask 077 只有擁有者可讀。db 沒在跑(首次部署)就略過。
# 這是同一台機器上的備份(磁碟壞掉一樣會掉);異地備份由 compose 的 backup 服務每日上傳 S3。
PROD_BACKUP_DIR ?= $(HOME)/backups/$(notdir $(CURDIR))
PROD_BACKUP_KEEP ?= 14
prod-backup:
	@if [ -z "$$($(COMPOSE_PROD) ps -q db 2>/dev/null)" ]; then \
		echo "db 沒有在執行(首次部署?),略過備份"; \
	else \
		mkdir -p $(PROD_BACKUP_DIR) && chmod 700 $(PROD_BACKUP_DIR); \
		umask 077 && $(COMPOSE_PROD) exec -T db sh -c 'pg_dump -Fc -U "$$POSTGRES_USER" "$$POSTGRES_DB"' > $(PROD_BACKUP_DIR)/.partial \
			|| { rm -f $(PROD_BACKUP_DIR)/.partial; echo "資料庫備份失敗,中止"; exit 1; }; \
		f=$(PROD_BACKUP_DIR)/$$(date +%Y%m%d-%H%M%S).dump; mv $(PROD_BACKUP_DIR)/.partial $$f; \
		ls -1t $(PROD_BACKUP_DIR)/*.dump | tail -n +$$(($(PROD_BACKUP_KEEP) + 1)) | xargs -r rm --; \
		echo "備份完成:$$f"; \
	fi

# 用剛 build 好的新映像、一次性容器跑 migration;舊的 app 容器照常服務。
# 一定要在 prod-up 之前,且 migration 必須 expand-safe(見 docs/database-migrations.md)。
prod-migrate: prod-backup
	$(COMPOSE_PROD) run --rm -T app alembic upgrade head

prod-up: prod-backup
	$(COMPOSE_PROD) up -d
	@echo ""
	@echo "生產環境已啟動！"
	@echo "  API: http://127.0.0.1:$${APP_PORT:-8000} (經 host nginx 對外)"

# 同一次 make 內 prod-backup 只會跑一次:順序是 備份 → build → migrate → up
prod-deploy: prod-backup prod-build prod-migrate prod-up

prod-down:
	$(COMPOSE_PROD) down

prod-logs:
	$(COMPOSE_PROD) logs -f

prod-llm-cost:
	$(COMPOSE_PROD) exec -T db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -c "$(LLM_COST_SQL)"'

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
# 營運 / 維運
# ===================

import-holidays: up
ifndef YEAR
	$(error 請提供西元年: make import-holidays YEAR=2027)
endif
	$(COMPOSE_DEV) exec -T app python -m scripts.import_holidays $(YEAR)

# 每月 LLM 花費(台北月份 × 模型,含小計);單價見 app/llm/utils.py 的 PRICES
LLM_COST_SQL = SELECT t.month, coalesce(t.model, '合計') AS model, count(*) AS calls, \
	sum(t.input_tokens) AS input_tokens, sum(t.cached_tokens) AS cached_tokens, \
	sum(t.output_tokens) AS output_tokens, round(sum(t.cost_usd), 2) AS usd \
	FROM (SELECT *, to_char(created_at AT TIME ZONE 'Asia/Taipei', 'YYYY-MM') AS month FROM llm_usage) t \
	GROUP BY GROUPING SETS ((t.month, t.model), (t.month)) ORDER BY t.month DESC, GROUPING(t.model), t.model;

llm-cost:
	$(COMPOSE_DEV) exec -T db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -c "$(LLM_COST_SQL)"'

# 用 docker 跑 nginx -t;站台設定引用的憑證在本機/CI 不存在,先產生自簽憑證頂替。
# NGINX_IMAGE 請對齊正式機的 nginx 大版本。
NGINX_IMAGE ?= nginx:1.27-alpine
nginx-check:
	@docker run --rm -i $(NGINX_IMAGE) sh -c '\
		set -e; cat > /etc/nginx/conf.d/default.conf; \
		apk add --no-cache openssl >/dev/null; mkdir -p /etc/ssl/app; \
		openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=example.com" \
			-keyout /etc/ssl/app/privkey.pem -out /etc/ssl/app/fullchain.pem >/dev/null 2>&1; \
		nginx -t' < nginx/app.conf

# 壓測(手動、定期跑,不進 CI)。Locust 不是專案依賴,用 uvx 跑。
PERF_HOST ?= http://localhost:8000
PERF_USERS ?= 20
perf-seed: up
	$(COMPOSE_DEV) exec -T app python -m scripts.seed_perf $(PERF_USERS) > perf/.perf_users.json
	@echo "已建立 $(PERF_USERS) 個壓測帳號 → perf/.perf_users.json(含 token,勿 commit)"

perf:
	uvx locust -f perf/locustfile.py --host $(PERF_HOST) $(ARGS)

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
	@uv run mypy .

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
