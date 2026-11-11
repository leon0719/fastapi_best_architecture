---
name: scaffold-app
description: Add a new FastAPI app, or a CRUD resource in an existing app, following this project's layering — model, migration, schema, service, views, SQLAdmin, tests — and register it in main.py and alembic/env.py. Use when the user asks to "create a new app", "add an endpoint", "add a resource", "開新 app", "新增模組", "新增 table", "建立 model", "加端點", "新增 API", "新增 CRUD".
---

# Add an app / resource

The reference implementation is **`app/users`** — copy its shape, don't invent another. When adding a
resource to an existing app, skip step 0 and the registration items already done.

Before starting, confirm the app name and the main model's fields with the user. When any other
convention is unclear, **ask first**, then apply the answer to every file at once — do not invent a
separate rule per file.

Write **inside out**, and do not start a layer until the previous layer's tests pass:
model → migration → schema → service (+ tests) → views (+ tests).
Starting from views hides service bugs behind HTTP noise.

## Steps

### 0. Create the directory

```bash
mkdir -p app/products/tests
touch app/products/__init__.py app/products/tests/__init__.py
```

Create only the files you need. `external_services.py`, `utils.py`, etc. are created when actually
used, never "for later".

### 1. Model (`models.py`)

```python
"""Product ORM models."""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.common.db.database import Base


class Product(Base):
    """Product database model."""

    __tablename__ = "products"  # snake_case plural

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

- Time columns are always `DateTime(timezone=True)`.
- **No `class Meta`** (SQLAlchemy ignores it). Multi-column index:
  `__table_args__ = (Index("ix_products_owner_created", "owner_id", "created_at"),)`.
- FKs state `ForeignKey(..., ondelete=...)`; indexes match real query paths — no low-selectivity
  single-column index (e.g. a bare boolean).

Then generate the migration (needs `make up` first):

```bash
make makemigrations MSG="Add products"
```

**Always review the generated file** (autogenerate misses custom indexes/constraints). Rules are in
`docs/database-migrations.md`. Then `make migrate`.

### 2. Schema (`schemas.py`)

```python
"""Product Pydantic schemas for request/response."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):
    """Schema for creating a product."""

    name: str = Field(..., min_length=1, max_length=100, description="Product name")


class ProductUpdate(BaseModel):
    """Schema for updating a product."""

    name: str = Field(..., min_length=1, max_length=100, description="Product name")


class ProductRead(BaseModel):
    """Schema for reading product data."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
```

`XxxRead` lists only the fields meant for callers — an unlisted field (hash, internal state) never
appears in a response.

### 3. Service (`services.py`) + tests

Follow `app/users/services.py`:

- `class ProductService:` with `__init__(self, db: Session)`.
- List queries always `order_by()` (usually `Product.id.desc()`), then `offset/limit`.
- Not found → `NotFoundException`; duplicate name → `ConflictException`; input violating a business
  rule → `ValidationException`.
- Failures the frontend must distinguish carry their own `reason`: add the code to `ErrorCode` first, then
  `ConflictException(msg, reason=ErrorCode.XXX_NAME_TAKEN)` (see `app/users/services.py`).
- Writes: `add` → `commit` → `refresh`, wrapped in `try / except Exception: rollback; logger.exception(...); raise`.
- Log prefix `[Service]`, with the resource ID.

**Gate**: in `app/products/tests/test_services.py`, write a test for every business rule and exception
branch (follow `app/users/tests/test_services.py`, using the `db_session` fixture from the root
`conftest.py`). `make test TEST=app/products/tests/test_services.py` must pass before the next step.

### 4. Views (`views.py`) + tests

```python
"""Product API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.db.database import get_db
from app.common.schemas import BaseResponse
from app.products.schemas import ProductCreate, ProductRead
from app.products.services import ProductService

router = APIRouter(prefix="/products", tags=["products"])  # kebab-case plural noun


def get_product_service(db: Annotated[Session, Depends(get_db)]) -> ProductService:
    """Get product service instance."""
    return ProductService(db)


@router.get("", response_model=BaseResponse[list[ProductRead]])
def list_products(
    service: Annotated[ProductService, Depends(get_product_service)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
):
    """List products, newest first."""
    return BaseResponse(data=service.list_products(skip=skip, limit=limit))


@router.post("", response_model=BaseResponse[ProductRead], status_code=201)
def create_product(product: ProductCreate, service: Annotated[ProductService, Depends(get_product_service)]):
    """Create a product."""
    return BaseResponse(data=service.create_product(product))


@router.delete("/{product_id}", response_model=BaseResponse[None])
def delete_product(product_id: int, service: Annotated[ProductService, Depends(get_product_service)]):
    """Delete a product."""
    service.delete_product(product_id)
    return BaseResponse()
```

- Import `get_db` from `app.common.db.database`; **never redefine it in views**.
- IDs are path params (`/{product_id}`); query params are for dynamic filters only.
- Views have no try/except and no hand-built error responses — raise and let `error_handler.py` convert.

**Gate**: `app/products/tests/test_views.py` (follow `app/users/tests/test_views.py`, using the `client`
fixture). Assert the **status code and `BaseResponse` body** of every endpoint; after a write, read it
back through the API; cover 404, 409, 422.

### 5. Admin (`admin.py`)

```python
"""Admin view for Product model."""

from sqladmin import ModelView

from app.products.models import Product


class ProductAdmin(ModelView, model=Product):
    """Admin view for managing products."""

    name = "Product"
    name_plural = "Products"
    icon = "fa-solid fa-box"
    column_list = [Product.id, Product.name, Product.created_at]
    column_searchable_list = [Product.name]
    column_sortable_list = [Product.id, Product.created_at]
    form_columns = [Product.name]  # no timestamps or id in the form
```

Secret fields (token, hash) stay out of `column_list` and `form_columns`.

## Registration (do every item)

1. `app/main.py`:
   ```python
   from app.products import views as product_views
   from app.products.admin import ProductAdmin

   admin.add_view(ProductAdmin)
   app.include_router(product_views.router, prefix="/api/v1")
   ```
2. `alembic/env.py`: `from app.products.models import Product  # noqa`

## When a third-party API is needed (`external_services.py`)

`httpx` may be imported only in this file (ruff `TID251`). Every call needs a timeout, `[External]`
logs, and failures converted to `ExternalAPIException`:

```python
"""Third-party API calls for products."""

import httpx
from loguru import logger

from app.common.exceptions import ExternalAPIException

_TIMEOUT = httpx.Timeout(10.0)


def fetch_price(sku: str) -> dict:
    """Fetch the current price from the pricing service."""
    url = f"https://pricing.example.com/skus/{sku}"
    logger.info(f"[External] Calling API - endpoint: {url}")
    try:
        resp = httpx.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.exception(f"[External] API call failed - endpoint: {url}, error: {e}")
        raise ExternalAPIException("Pricing service unavailable") from e
    return resp.json()
```

Call it from the service, never directly from views. Tests replace the function with `monkeypatch`;
**never call the real API**.

## Completion checklist

Report each item in one of three states; never tick something you did not run:
`[x]` verified · `[ ]` not done · `[ ] ⛔ <reason>` could not verify (e.g. Docker not running).

- [ ] Migration generated, reviewed, `make migrate` succeeded
- [ ] Model added to `alembic/env.py`
- [ ] Router added with `include_router`; admin added with `add_view`
- [ ] Service tests pass (before writing views)
- [ ] Endpoint tests pass, including 404 / 409 / 422 and the `BaseResponse` body
- [ ] No unused empty files created
- [ ] The **check** skill passes

## Common pitfalls

- Missing import in `alembic/env.py`: autogenerate cannot see the new model and emits an empty
  migration — or a `drop_table` when the table already exists.
- Missing `include_router`: every endpoint returns 404.
- Returning an ORM object instead of `BaseResponse(data=...)`: response validation fails with a 500.
- Raising `ValidationException` (400) for a duplicate name: it should be `ConflictException` (409).
- A list without `order_by()`: pagination results differ on every call.
- A time column without `timezone=True`: stored as `timestamp without time zone`, breaking "time is always UTC".
- Adding a `NOT NULL` column to an existing table in one migration: old code is still writing during the
  deploy and does not fill it. Split into nullable → backfill → add constraint.
- `make makemigrations` runs inside the app container: `make up` first, and `.env.local` must exist.
