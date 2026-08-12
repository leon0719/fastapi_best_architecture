# FastAPI Best Architecture

A FastAPI project with **Django-style app structure** - each feature is a self-contained module.

## Requirements

- Python 3.13
- Docker & Docker Compose
- uv (package manager)

## Quick Start

docker compose -f docker-compose-dev.yml up -d --build 

1. Setup environment variables:
```bash
cp .env.example .env
```

2. Install dependencies (for editor syntax highlighting and autocomplete):
```bash
uv sync
```

3. Run the application with Docker:
```bash
docker compose -f docker-compose-dev.yml up -d --build
```

The API will be available at `http://localhost:8000`

**Useful commands:**

View logs:
```bash
docker compose -f docker-compose-dev.yml logs -f app
```

Stop containers:
```bash
docker compose -f docker-compose-dev.yml down
```

## Viewing Logs

### Console Logs (Docker)

**Recommended method** - View logs with colors using `docker compose`:
```bash
# View application logs with colors
docker compose -f docker-compose-dev.yml logs -f app

# View all services logs
docker compose -f docker-compose-dev.yml logs -f

# View last 100 lines
docker compose -f docker-compose-dev.yml logs --tail=100 app

# View database logs
docker compose -f docker-compose-dev.yml logs -f db

# View Redis logs
docker compose -f docker-compose-dev.yml logs -f redis
```

**Alternative method** - Direct docker logs (no colors):
```bash
docker logs -f fastapi-best-architecture-dev
```

### File Logs

Application logs are stored in the `logs/` directory with automatic rotation:

```bash
# View all logs in real-time
docker compose -f docker-compose-dev.yml exec app tail -f logs/app.log

# View error logs only
docker compose -f docker-compose-dev.yml exec app tail -f logs/error.log

# Search logs for specific patterns
docker compose -f docker-compose-dev.yml exec app grep "ERROR" logs/app.log

# View logs by layer
docker compose -f docker-compose-dev.yml exec app grep "\[Service\]" logs/app.log
docker compose -f docker-compose-dev.yml exec app grep "\[Repository\]" logs/app.log
docker compose -f docker-compose-dev.yml exec app grep "\[API\]" logs/app.log
```

### Log Levels and Formats

**Console Output** (with colors):
```
2025-01-15 10:30:45 | INFO     | app.services.user_service:create_user:25 - [Service] Creating user - name: John
2025-01-15 10:30:45 | DEBUG    | app.repositories.user_repository:get_by_name:15 - [Repository] Query - name: John
2025-01-15 10:30:45 | INFO     | app.middleware.request_logging:dispatch:54 - [API] POST /api/v1/users - status: 201, duration: 0.123s
```

**Log Levels:**
- `DEBUG`: Detailed diagnostic information (query params, cache hits)
- `INFO`: General informational messages (operations success, resource creation)
- `WARNING`: Warning messages (validation failures, slow queries)
- `ERROR`: Error messages with stack traces

**Layer Prefixes:**
- `[API]` - API layer (auto-logged by middleware)
- `[Service]` - Business logic layer
- `[Repository]` - Data access layer
- `[External]` - External API calls

### Log Rotation

Logs are automatically rotated to prevent disk space issues:
- **app.log**: Rotates at 10MB, keeps last 10 files, compressed as `.zip`
- **error.log**: Dedicated error log with full stack traces
- Location: `logs/` directory in the project root

### Production

```bash
docker compose up -d --build
```

## Testing

```bash
uv run pytest
```

## API Documentation

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Project Structure (Django-Style Apps)

```
app/
├── main.py                      # FastAPI entry point
├── common/                      # Shared modules (all apps)
│   ├── core/                    # Core configuration
│   │   ├── config.py            # Environment variables
│   │   ├── log_config.py        # Loguru logging
│   │   ├── redis.py             # Redis connection
│   │   └── admin.py             # Admin panel setup
│   ├── db/                      # Database
│   │   ├── database.py          # SQLAlchemy engine/session
│   ├── middleware/              # Middleware
│   │   ├── error_handler.py     # Global error handling
│   │   └── request_logging.py   # Request logging
│   └── exceptions/              # Custom exceptions
│       └── __init__.py          # AppException base class
├── users/                       # User app (self-contained)
│   ├── models.py                # ORM models
│   ├── schemas.py               # Pydantic schemas
│   ├── services.py              # Business logic
│   ├── views.py                 # API routes
│   ├── admin.py                 # User admin interface
│   └── tests/                   # Unit tests
└── chatbots/                    # Chatbot app (self-contained)
    ├── models.py                # ORM models
    ├── schemas.py               # Pydantic schemas
    ├── services.py              # Business logic
    ├── views.py                 # API routes
    ├── admin.py                 # Chatbot admin interface
    ├── external_services.py     # Third-party APIs
    ├── utils.py                 # Helper functions
    └── tests/                   # Unit tests
```

**Shared modules in `common/`:**
- `core/` - Configuration, logging, Redis, admin panel
- `db/` - Database connection and initialization
- `middleware/` - Global middleware
- `exceptions/` - Custom exceptions

**Each app is self-contained with:**
- `models.py` - Database models (SQLAlchemy)
- `schemas.py` - Request/response validation (Pydantic)
- `services.py` - Business logic
- `views.py` - API routes (FastAPI)
- `admin.py` - Admin panel interface (SQLAdmin)
- `tests/` - Unit and integration tests

## Architecture Flow (Simplified 3-Layer)

### Request Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client Request                           │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Views (users/views.py)                                         │
│  - API routes & request validation                              │
│  - Get DB session via Depends(get_db)                           │
│  - Create service instance                                      │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Services (users/services.py)                                   │
│  - Business logic & validation                                  │
│  - Direct database queries (SQLAlchemy)                         │
│  - Call external_services if needed                             │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Models (users/models.py)                                       │
│  - SQLAlchemy ORM models                                        │
│  - Table definitions & relationships                            │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Database (PostgreSQL)                                          │
└─────────────────────────────────────────────────────────────────┘
```

**Simple Flow:** `views.py` → `services.py` → `models.py` → `database`

### Key Principles

1. **Self-Contained Apps**
   - Each feature is a separate app folder
   - All related code in one place (models, schemas, services, views)
   - Easy to find and maintain

2. **3-Layer Architecture**
   - Views: API routes & request handling
   - Services: Business logic & database queries
   - Models: ORM definitions

3. **Session Management**
   ```python
   def get_db():
       db = SessionLocal()
       try:
           yield db  # Injected into views
       finally:
           db.close()  # Auto-cleanup
   ```

4. **Exception Handling**
   - Raise custom exceptions in services
   - Global middleware catches and converts to HTTP responses
   - No try/catch needed in views

## Example: Creating a User (New Architecture)

```python
# 1. Client sends POST request
POST /api/v1/users
Content-Type: application/json
{"name": "John Doe"}

# 2. Views (users/views.py) - Route handler
@router.post("", response_model=UserRead, status_code=201)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    service = UserService(db)
    return service.create_user(user)

# 3. Services (users/services.py) - Business logic
def create_user(self, user_data: UserCreate) -> User:
    # Check for duplicates
    existing = self.db.query(User).filter(User.name == user_data.name).first()
    if existing:
        raise ValidationException(f"User '{user_data.name}' already exists")

    # Create and save
    user = User(name=user_data.name)
    self.db.add(user)
    self.db.commit()
    self.db.refresh(user)
    return user

# 4. Response returned to client
{"id": 1, "name": "John Doe"}
```

**That's it! Only 3 layers, no repository needed.**

## Development Workflows

### How to Add a New App (Feature)

**Example: Adding a "products" app**

**Step 1: Create app directory**
```bash
mkdir -p app/products/tests
touch app/products/{__init__,models,schemas,services,views}.py
```

**Step 2: Create Model** (`app/products/models.py`)
```python
from sqlalchemy import String, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from app.common.db.database import Base

class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    price: Mapped[float] = mapped_column(Numeric(10, 2))
```

**Step 3: Create Schemas** (`app/products/schemas.py`)
```python
from pydantic import BaseModel, ConfigDict

class ProductCreate(BaseModel):
    name: str
    price: float

class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    price: float
```

**Step 4: Create Service** (`app/products/services.py`)
```python
from sqlalchemy.orm import Session
from app.products.models import Product
from app.products.schemas import ProductCreate
from app.common.exceptions import ValidationException

class ProductService:
    def __init__(self, db: Session):
        self.db = db

    def create_product(self, data: ProductCreate) -> Product:
        # Business logic
        existing = self.db.query(Product).filter(Product.name == data.name).first()
        if existing:
            raise ValidationException(f"Product '{data.name}' exists")

        product = Product(name=data.name, price=data.price)
        self.db.add(product)
        self.db.commit()
        self.db.refresh(product)
        return product

    def list_products(self) -> list[Product]:
        return self.db.query(Product).all()
```

**Step 5: Create Views** (`app/products/views.py`)
```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.common.db.database import SessionLocal
from app.products.services import ProductService
from app.products.schemas import ProductCreate, ProductRead

router = APIRouter(prefix="/products", tags=["products"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("", response_model=ProductRead, status_code=201)
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    service = ProductService(db)
    return service.create_product(product)

@router.get("", response_model=list[ProductRead])
def list_products(db: Session = Depends(get_db)):
    service = ProductService(db)
    return service.list_products()
```

**Step 6: Create Admin Interface** (`app/products/admin.py`)
```python
from sqladmin import ModelView
from app.products.models import Product

class ProductAdmin(ModelView, model=Product):
    name = "Product"
    name_plural = "Products"
    icon = "fa-solid fa-box"
    column_list = [Product.id, Product.name, Product.price]
    column_searchable_list = [Product.name]
    can_create = True
    can_edit = True
    can_delete = True
```

**Step 7: Register in main.py** (`app/main.py`)
```python
from app.products import views as product_views
from app.products.admin import ProductAdmin

app.include_router(product_views.router, prefix="/api/v1")
admin.add_view(ProductAdmin)  # Add to admin panel
```

**Step 8: Update Alembic** (`alembic/env.py`)
```python
from app.products.models import Product  # noqa
```

**Step 9: Create Migration**
```bash
uv run alembic revision --autogenerate -m "Add products"
uv run alembic upgrade head
```

**Done! Only 5 files needed:**
- `models.py` - Database table
- `schemas.py` - API validation
- `services.py` - Business logic
- `views.py` - API routes
- `admin.py` - Admin panel interface

---

### How to Add a Database Table

**Step 1: Create SQLAlchemy Model** (in your app's `models.py`)
```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.common.db.database import Base

class Category(Base):
    """Category database model."""
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=True)

    # Relationships (if needed)
    # products: Mapped[list["Product"]] = relationship(back_populates="category")
```

**Step 2: Update Database Initialization**

Database schema is managed exclusively by Alembic:
```bash
# Generate migration
uv run alembic revision --autogenerate -m "Add category table"

# Apply migration
uv run alembic upgrade head
```

**Step 3: Add Relationships (if needed)**

Update related models:
```python
# app/models/product.py
from sqlalchemy import ForeignKey

class Product(Base):
    # ... existing fields ...
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=True)

    # Relationship
    category: Mapped["Category"] = relationship(back_populates="products")
```

---

### How to Add API Schemas

**Basic Schema Structure:**

```python
# app/schemas/order.py
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator

class OrderBase(BaseModel):
    """Base schema with common fields."""
    customer_name: str = Field(..., min_length=1, max_length=100)
    total_amount: float = Field(..., gt=0)
    status: str = Field(default="pending")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate status field."""
        allowed_statuses = ["pending", "confirmed", "shipped", "delivered"]
        if v not in allowed_statuses:
            raise ValueError(f"Status must be one of {allowed_statuses}")
        return v

class OrderCreate(OrderBase):
    """Schema for creating an order."""
    items: list[int]  # List of product IDs

class OrderUpdate(BaseModel):
    """Schema for updating an order (all fields optional)."""
    customer_name: str | None = None
    status: str | None = None

class OrderRead(OrderBase):
    """Schema for reading order data."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime

class OrderWithItems(OrderRead):
    """Schema with nested relationships."""
    items: list["ProductRead"]  # Nested schema
```

**Schema Best Practices:**

1. **Base Schema**: Common fields shared across Create/Update
2. **Create Schema**: Required fields for creation
3. **Update Schema**: Optional fields for partial updates
4. **Read Schema**: All fields including auto-generated (id, timestamps)
5. **Nested Schemas**: For relationships (e.g., OrderWithItems)

---

### How to Add a Service

**Service Structure:**

```python
# app/orders/services.py
from sqlalchemy.orm import Session
from app.orders.models import Order
from app.products.models import Product
from app.common.exceptions import NotFoundException, ValidationException

class OrderService:
    """Business logic for Order operations."""

    def __init__(self, db: Session):
        self.db = db

    def create_order(self, customer_name: str, product_ids: list[int]) -> Order:
        """Create a new order with business validation."""

        # 1. Validate products exist
        products = []
        for product_id in product_ids:
            product = self.db.query(Product).filter(Product.id == product_id).first()
            if not product:
                raise NotFoundException(f"Product {product_id} not found")
            products.append(product)

        # 2. Business logic: calculate total
        total_amount = sum(p.price for p in products)

        # 3. Business rule: minimum order amount
        if total_amount < 10.0:
            raise ValidationException("Minimum order amount is $10")

        # 4. Create order
        order = Order(
            customer_name=customer_name,
            total_amount=total_amount,
            status="pending"
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)

        # 5. Associate products (if using relationships)
        for product in products:
            # Create order_items relationship
            pass

        return order

    def update_order_status(self, order_id: int, new_status: str) -> Order:
        """Update order status with validation."""
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise NotFoundException(f"Order {order_id} not found")

        # Business rule: status transitions
        valid_transitions = {
            "pending": ["confirmed", "cancelled"],
            "confirmed": ["shipped", "cancelled"],
            "shipped": ["delivered"],
            "delivered": [],
            "cancelled": []
        }

        if new_status not in valid_transitions.get(order.status, []):
            raise ValidationException(
                f"Cannot transition from {order.status} to {new_status}"
            )

        order.status = new_status
        self.db.commit()
        self.db.refresh(order)
        return order
```

**Service Best Practices:**

1. **Single Responsibility**: One service per domain entity
2. **Business Logic**: Validation, calculations, workflows
3. **Direct Database Access**: Query database directly (no repository layer)
4. **Error Handling**: Raise custom exceptions (from `app.common.exceptions`)
5. **Transaction Management**: Use db.commit() and db.refresh()

---

### How to Add Middleware

**Example: Request Logging Middleware**

**Step 1: Create Middleware** (`app/common/middleware/logging_middleware.py`)
```python
import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger

class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all HTTP requests."""

    async def dispatch(self, request: Request, call_next):
        # Before request
        start_time = time.time()

        logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "client": request.client.host if request.client else None
            }
        )

        # Process request
        response = await call_next(request)

        # After request
        process_time = time.time() - start_time
        logger.info(
            f"Request completed: {request.method} {request.url.path} - "
            f"Status: {response.status_code} - Duration: {process_time:.3f}s",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration": process_time
            }
        )

        response.headers["X-Process-Time"] = str(process_time)
        return response
```

**Step 2: Register in main.py** (`app/main.py`)
```python
from app.common.middleware.logging_middleware import LoggingMiddleware

app = FastAPI(title=config.app_name)

# Add middleware (order matters - first added = outermost)
app.add_middleware(LoggingMiddleware)
```

**Example: Error Handling Middleware**

```python
# app/common/middleware/error_handler.py
from fastapi import Request, status
from fastapi.responses import JSONResponse
from loguru import logger
from app.common.exceptions import (
    NotFoundException,
    ConflictException,
    ValidationException
)

async def error_handling_middleware(request: Request, call_next):
    """Global error handler middleware."""
    try:
        return await call_next(request)
    except NotFoundException as e:
        logger.warning(f"Resource not found: {e}")
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "Not Found", "detail": str(e)}
        )
    except ConflictException as e:
        logger.warning(f"Duplicate resource: {e}")
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": "Conflict", "detail": str(e)}
        )
    except ValidationException as e:
        logger.warning(f"Validation error: {e}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Bad Request", "detail": str(e)}
        )
    except Exception as e:
        logger.exception(f"Unhandled exception: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Internal Server Error", "detail": "An unexpected error occurred"}
        )

# Register as middleware
app.middleware("http")(error_handling_middleware)
```

**Example: CORS Middleware**

```python
# app/main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,  # ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Middleware Order (Important!):**

```python
# app/main.py
app = FastAPI()

# 1. CORS (outermost)
app.add_middleware(CORSMiddleware, ...)

# 2. Logging
app.add_middleware(LoggingMiddleware)

# 3. Error handling (innermost - catches errors from routes)
app.middleware("http")(error_handling_middleware)

# Routes
app.include_router(...)
```

Middleware execution order:
```
Request → CORS → Logging → Error Handler → Route Handler → Error Handler → Logging → CORS → Response
```

---

## Common Development Tasks

### Adding Custom Exceptions

```python
# app/common/exceptions/__init__.py
class AppException(Exception):
    """Base exception for application."""
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)

class NotFoundException(AppException):
    """Raised when a resource is not found."""
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404)

class ConflictException(AppException):
    """Raised when attempting to create a duplicate resource."""
    def __init__(self, message: str = "Resource already exists"):
        super().__init__(message, status_code=409)

class ValidationException(AppException):
    """Raised when validation fails."""
    def __init__(self, message: str = "Validation failed"):
        super().__init__(message, status_code=400)
```

### Adding Database Seeders

```python
# app/db/seeders.py
from sqlalchemy.orm import Session
from app.models.user import User

def seed_users(db: Session):
    """Seed initial users."""
    users = [
        User(name="Admin User"),
        User(name="Test User"),
    ]
    db.add_all(users)
    db.commit()
```

### Adding Background Tasks

```python
from fastapi import BackgroundTasks

@router.post("/orders")
def create_order(
    order: OrderCreate,
    background_tasks: BackgroundTasks,
    service: OrderService = Depends(get_order_service)
):
    new_order = service.create_order(order)

    # Add background task
    background_tasks.add_task(send_order_confirmation_email, new_order.id)

    return new_order

def send_order_confirmation_email(order_id: int):
    """Background task to send email."""
    # Email sending logic
    pass
```
