# CLAUDE.md

## Project Overview

FastAPI best architecture using Python 3.13 + uv. **Django-style app structure** - each feature is a self-contained app with models, schemas, services, and views.

## Package Management & Commands

**uv** (not pip/poetry) for all dependencies. **Development runs in Docker** (hot-reload enabled).

**Makefile** wraps all common commands — run `make help` for the full list:

```bash
make up          # Start dev containers (hot-reload)
make db-up       # Start DB + Redis only (for local app / alembic)
make migrate     # alembic upgrade head
make makemigrations MSG="Add email to users"
make all         # format + lint + type-check + test
make test        # uv run pytest (TEST="path" to filter)
make coverage    # Tests with coverage report (htmlcov/)
```

Raw equivalents:

```bash
# Dependencies
uv add <package>              # Runtime dependency
uv add --dev <package>        # Dev dependency

# Docker Development
docker compose -f docker-compose-dev.yml up -d --build  # Start
docker compose -f docker-compose-dev.yml logs -f        # Logs
docker compose -f docker-compose-dev.yml down           # Stop

# Testing
uv run pytest                 # All tests
uv run pytest --cov=app       # With coverage

# Database Migrations (local with Docker DB)
docker compose -f docker-compose-dev.yml up -d db redis  # Start DB only
uv run alembic revision --autogenerate -m "message"      # Create migration
uv run alembic upgrade head                              # Apply migrations
```

## Architecture & Rules

**Django-Style App Structure:**
```
app/
├── main.py                  # FastAPI entry point
├── common/                  # Shared modules (all apps)
│   ├── core/                # Core configuration
│   │   ├── config.py        # Environment variables
│   │   ├── log_config.py    # Loguru logging
│   │   ├── redis.py         # Redis connection
│   │   └── admin.py         # Admin panel setup
│   ├── db/                  # Database
│   │   ├── database.py      # SQLAlchemy engine/session
│   ├── middleware/          # Middleware
│   │   ├── error_handler.py     # Global error handling
│   │   └── request_logging.py   # Request logging
│   └── exceptions/          # Custom exceptions
│       └── __init__.py      # AppException base class
├── users/                   # User app (self-contained)
│   ├── models.py            # ORM models
│   ├── schemas.py           # Pydantic request/response
│   ├── services.py          # Business logic
│   ├── views.py             # API routes
│   ├── admin.py             # User admin interface
│   └── tests/               # User tests
└── chatbots/                # Chatbot app (self-contained)
    ├── models.py            # ORM models
    ├── schemas.py           # Pydantic request/response
    ├── services.py          # Business logic
    ├── views.py             # API routes
    ├── admin.py             # Chatbot admin interface
    ├── external_services.py # Third-party APIs
    ├── utils.py             # Helper functions
    └── tests/               # Chatbot tests
```

**File Responsibilities:**
- **models.py**: ORM models, validation, Meta config (indexes, ordering)
- **schemas.py**: Pydantic request/response models
- **services.py**: Business logic, multi-model operations, call external_services
- **views.py**: API routes (FBV pattern), auth checks, call services
- **admin.py**: SQLAdmin ModelView for admin panel interface
- **external_services.py**: Third-party API integration with error handling (optional)
- **utils.py**: Pure helper functions (no models/API dependencies) (optional)
- **tests/**: Model, view, service tests

**Key Rules:**
1. **Simple Flow**: `views.py` → `services.py` → database (no repository layer)
2. **Session Management**: Each view gets DB session via `Depends(get_db)`
3. **Exceptions**: Extend `AppException`, let global handler convert to HTTP responses
4. **Self-Contained Apps**: Each app is independent with all its files

## Adding New App

**Step-by-Step (e.g., "products"):**

1. **Create app directory:**
```bash
mkdir -p app/products/tests
touch app/products/{__init__,models,schemas,services,views,admin}.py
```

2. **Create model** (`app/products/models.py`):
```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from app.common.db.database import Base

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
```

3. **Create schemas** (`app/products/schemas.py`):
```python
from pydantic import BaseModel, ConfigDict

class ProductCreate(BaseModel):
    name: str

class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
```

4. **Create service** (`app/products/services.py`):
```python
from sqlalchemy.orm import Session
from app.products.models import Product

class ProductService:
    def __init__(self, db: Session):
        self.db = db

    def list_products(self):
        return self.db.query(Product).all()
```

5. **Create views** (`app/products/views.py`):
```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.common.db.database import SessionLocal
from app.products.services import ProductService
from app.products.schemas import ProductRead

router = APIRouter(prefix="/products", tags=["products"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("", response_model=list[ProductRead])
def list_products(db: Session = Depends(get_db)):
    service = ProductService(db)
    return service.list_products()
```

6. **Create admin interface** (`app/products/admin.py`):
```python
from sqladmin import ModelView
from app.products.models import Product

class ProductAdmin(ModelView, model=Product):
    name = "Product"
    name_plural = "Products"
    icon = "fa-solid fa-box"
    column_list = [Product.id, Product.name]
    column_searchable_list = [Product.name]
    can_create = True
    can_edit = True
    can_delete = True
```

7. **Register in main.py:**
```python
from app.products import views as product_views
from app.products.admin import ProductAdmin

app.include_router(product_views.router, prefix="/api/v1")
admin.add_view(ProductAdmin)  # Add to admin panel
```

8. **Update alembic/env.py:**
```python
from app.products.models import Product  # noqa
```

9. **Create migration:**
```bash
uv run alembic revision --autogenerate -m "Add products"
uv run alembic upgrade head
```

**Tech Stack:**
FastAPI 0.118+, SQLAlchemy 2.0+, Pydantic Settings, Uvicorn, Loguru, PostgreSQL, Redis 7, Alembic, Python 3.13

## Logging Standards

**Setup:** `from loguru import logger`
**Outputs:** Console (DEBUG+), `logs/app.log` (INFO+, 10MB rotation), `logs/error.log` (ERROR+)

**Configuration:** (`app/common/core/log_config.py`)
```python
# SQLAlchemy SQL logging: DISABLED (too verbose)
# Uvicorn access logs: DISABLED (we use RequestLoggingMiddleware)
# Application logs: Loguru (colored console + file rotation)
```

**Log Levels:**
- `DEBUG`: Query params, cache hits, diagnostic info
- `INFO`: Operations success, resource creation, counts
- `WARNING`: Validation failures, slow queries (>1s), deprecated usage
- `ERROR`: Use `logger.exception()` for automatic stack traces

**Layer Prefixes (mandatory):**
- `[API]` - Middleware auto-logging (DO NOT use manually)
- `[Service]` - Business logic layer
- `[External]` - External API calls

**Required Context in ALL logs:**
- Resource IDs: `user_id: {user.id}`
- Counts: `total: {count}`
- Durations: `duration: {duration:.3f}s`

**Security:**
❌ NEVER log: passwords, API keys, tokens (unless masked: `token[:10]...`)

**API Layer:** NO manual logging - `RequestLoggingMiddleware` auto-logs all requests
**Service Layer:** Log entry point, validations (WARNING), success (INFO), errors (exception())

**Example:**
```python
# Service layer
logger.info(f"[Service] Creating user - name: {name}")
logger.exception(f"[Service] Failed - user_id: {user_id}, error: {e}")

# External services
logger.info(f"[External] Calling API - endpoint: {url}")
```

**Troubleshooting:**
- **Too many SQL logs?** → Already disabled in `log_config.py` (set to WARNING)
- **Enable SQL debugging:** Change `echo=False` to `echo=True` in `database.py`
- **Too many Uvicorn logs?** → Already disabled (we use RequestLoggingMiddleware)

## Redis Caching

**Import:** `from app.common.core.redis import RedisCache, cache_result`

**Basic Operations:**
```python
cache = RedisCache()
cache.set("key", "value", expire=300)                    # Set with TTL
cache.set_json("user:123", {"name": "John"}, expire=60)  # JSON serialize
value = cache.get("key")                                  # Get
user = cache.get_json("user:123")                        # JSON deserialize
cache.delete("key")                                       # Delete
cache.incr("counter")                                     # Increment
```

**Cache Decorator:**
```python
@cache_result(expire=3600, key_prefix="user")
def expensive_operation(user_id: int) -> dict:
    # Cached for 1 hour, key: "user:expensive_operation:{user_id}"
    return perform_expensive_query(user_id)
```

**Patterns:**
1. **Time-based**: `cache.set("key", value, expire=3600)` - Auto-expire after N seconds
2. **Manual invalidation**: `cache.delete(f"user:{user_id}")` after update/delete
3. **Cache-aside**: Try cache → if miss, fetch DB → store in cache → return

**Best Practices:**
- Use hierarchical keys: `user:123:profile`, `product:456:details`
- Always set expiration (prevent memory leaks)
- Handle failures gracefully (fallback to DB)
- Log cache HIT/MISS for monitoring

**Test API:** `/api/v1/cache/test`, `/api/v1/cache/stats`, `/api/v1/cache/decorator-test`

## Database Migrations (Alembic)

**Common Commands:**
```bash
# Create migration (auto-detect model changes)
uv run alembic revision --autogenerate -m "Add email to users"

# Apply migrations
uv run alembic upgrade head          # Apply all
uv run alembic upgrade +1            # Apply one

# Rollback
uv run alembic downgrade -1          # Rollback one
uv run alembic downgrade base        # Rollback all

# History
uv run alembic current               # Show current version
uv run alembic history               # Show all migrations
```

**Workflow:**
1. Modify model (e.g., add `email` field to `User`)
2. Generate: `uv run alembic revision --autogenerate -m "message"`
3. Review generated file in `alembic/versions/`
4. Apply: `uv run alembic upgrade head`

**Best Practices:**
- **Always review** autogenerated migrations (may miss custom indexes/constraints)
- **Test before production**: `upgrade head` → `downgrade -1` → `upgrade head`
- **Never edit applied** migrations (create new migration instead)
- **Descriptive messages**: "Add email unique constraint" not "Update"
- **Data migrations**: Add `op.execute("UPDATE ...")` for data transformations
- **Backup first**: `docker compose exec db pg_dump -U postgres fastapi_db > backup.sql`

**Common Patterns:**
```python
# Add column with default
def upgrade():
    op.add_column('users', sa.Column('role', sa.String(20), nullable=True))
    op.execute("UPDATE users SET role = 'user' WHERE role IS NULL")
    op.alter_column('users', 'role', nullable=False)

# Add index
def upgrade():
    op.create_index('ix_users_email', 'users', ['email'])
```

## Exception Handling

**Custom Exceptions** (extend `AppException` in `app/common/exceptions/`):
- `NotFoundException` → 404
- `ValidationException` → 400
- `ConflictException` → 409
- `ExternalAPIException` → 502

**Global Handler** (`app/common/middleware/error_handler.py`):
- Catches all `AppException` and converts to HTTP responses
- Logs errors automatically
- API routes should NOT catch exceptions (let middleware handle)

**Usage:**
```python
# Service layer
if not user:
    raise NotFoundException(f"User {user_id} not found")  # Auto-converts to 404

if len(name) < 2:
    raise ValidationException("Name too short")  # Auto-converts to 400
```

## Environment Config

**Files:**
- `.env.local.example` / `.env.prod.example` - 唯一進版控的範本
- `.env.local` - Local development（Docker Compose 內部連線：`DB_HOST=db`）
- `.env.prod` - Production

`ENV` 決定 `Config`（`app/common/core/config.py`）要載入哪個 `.env.{ENV}` 檔，
未設定時預設 `local`。Docker compose 用 `env_file` 明確指定該環境的檔案。

**App 一律在容器內執行**（`make migrate`/`makemigrations` 等都是
`docker compose exec app ...`），不需要另外維護一份給本機直連用的
`DB_HOST=localhost` 設定 —— 這也是舊版 `.env`（本機）/`.env.local`（容器）
雙檔並存時，兩邊密碼容易對不上而連線失敗的根因。

**機密絕不進版控。** `.gitignore` 已排除 `.env` / `.env.*`（`*.example` 除外）。
2026-07 曾因缺少這條規則，把 admin 金鑰與密碼 commit 進公開 repo，
詳見 [docs/security-incident-2026-07.md](docs/security-incident-2026-07.md)。

**Key Variables:**
```bash
ENV=local/prod                 # 選擇載入 .env.local 還是 .env.prod
DB_HOST=db                     # docker-compose 裡的 service name
REDIS_HOST=redis               # docker-compose 裡的 service name
ADMIN_SECRET_KEY=secret        # Admin panel session 簽章金鑰(每個環境各自一把)
```

**注意：** `DB_PASSWORD` / `REDIS_PASSWORD` 同時扮演兩種角色 —— 既是 app
容器讀取的連線密碼，也是 compose 拿去初始化 `db`/`redis` 容器的密碼（靠
Makefile 的 `--env-file` 做變數替換）。中途改密碼但資料庫 volume 已用舊密碼
初始化過時兩者不會自動同步，需 `make docker-clean` 清空 volume 重建，或把
`.env.local` 改回 volume 實際初始化時用的密碼。

**啟動時的安全驗證** (`Config.enforce_secure_settings()`，由 `app/main.py` 呼叫)：

- `DEBUG=False` 時，若 `ADMIN_SECRET_KEY` / `ADMIN_USERNAME` / `ADMIN_PASSWORD` /
  `DB_PASSWORD` / `REDIS_PASSWORD` 任一仍是 placeholder（含 `CHANGEME`、`your-`）
  或開發預設值（`postgres`、`admin123`…），**直接 raise 拒絕啟動**並指名是哪一項。
- `DEBUG=True` 時只印 warning，不擋本機開發。

新增機密欄位時，記得同步加進 `security_issues()` 的檢查清單，否則它不受保護。
