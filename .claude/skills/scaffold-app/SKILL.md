---
name: scaffold-app
description: 依本專案分層慣例新增 FastAPI app 或在既有 app 加一組 CRUD 資源——model、migration、schema、service、views、SQLAdmin、測試，並完成 main.py 與 alembic/env.py 的註冊。Use when the user asks to "開新 app"、"新增模組"、"新增 table"、"建立 model"、"加端點"、"新增 API"、"新增 CRUD"、"create a new app"、"add an endpoint"、"add a resource"。
---

# 新增 app／資源

參考實作是 **`app/users`**——照抄它的形狀，不要另創寫法。既有 app 加資源時，跳過步驟 0 與「註冊」中已經做過的項目。

開始前先向使用者確認 app 名稱與主要 model 的欄位。其他慣例不明確時**先問**，確認後一次套用到所有檔案——不要每個檔案各自發明一條規則。

**由內向外**寫，前一層的測試沒過不要開始下一層：model → migration → schema → service（＋測試）→ views（＋測試）。
從 views 開始寫，service 的 bug 會藏在 HTTP 的雜訊後面。

## 步驟

### 0. 建目錄

```bash
mkdir -p app/products/tests
touch app/products/__init__.py app/products/tests/__init__.py
```

只建需要的檔案。`external_services.py`、`utils.py` 等真的要用時才建立，不要「先放著以後用」。

### 1. Model（`models.py`）

```python
"""Product ORM models."""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.common.db.database import Base


class Product(Base):
    """Product database model."""

    __tablename__ = "products"  # snake_case 複數

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

- 時間欄位一律 `DateTime(timezone=True)`。
- **不要寫 `class Meta`**（SQLAlchemy 會忽略）。多欄位 index 用 `__table_args__ = (Index("ix_products_owner_created", "owner_id", "created_at"),)`。
- FK 寫明 `ForeignKey(..., ondelete=...)`；index 對應實際查詢路徑，不建低選擇性的單欄位 index（例如裸 boolean）。

接著產生 migration（需先 `make up`）：

```bash
make makemigrations MSG="Add products"
```

**一定要 review 產出的檔案**（autogenerate 會漏自訂 index／constraint）。規則見 `docs/database-migrations.md`。然後 `make migrate`。

### 2. Schema（`schemas.py`）

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

`XxxRead` 只列要對外的欄位——沒列的欄位（例如 hash、內部狀態）就不會出現在回應裡。

### 3. Service（`services.py`）＋ 測試

照 `app/users/services.py`：

- `class ProductService:`，`__init__(self, db: Session)`。
- 列表查詢一定 `order_by()`（通常 `Product.id.desc()`），再 `offset/limit`。
- 找不到 → `NotFoundException`；名稱重複 → `ConflictException`；輸入不合業務規則 → `ValidationException`。
- 寫入：`add` → `commit` → `refresh`，包在 `try / except Exception: rollback; logger.exception(...); raise`。
- log 前綴 `[Service]`，帶資源 ID。

**關卡**：在 `app/products/tests/test_services.py` 為每條業務規則、每個例外分支寫測試（照 `app/users/tests/test_services.py`，用根目錄 `conftest.py` 的 `db_session` fixture），
`make test TEST=app/products/tests/test_services.py` 通過才進下一步。

### 4. Views（`views.py`）＋ 測試

```python
"""Product API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.db.database import get_db
from app.common.schemas import BaseResponse
from app.products.schemas import ProductCreate, ProductRead
from app.products.services import ProductService

router = APIRouter(prefix="/products", tags=["products"])  # kebab-case 複數名詞


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

- `get_db` 從 `app.common.db.database` import，**不要在 views 裡另外定義**。
- ID 用路徑參數（`/{product_id}`），只有動態篩選才用 query。
- views 不寫 try/except、不手寫錯誤回應——raise 交給 `error_handler.py`。

**關卡**：`app/products/tests/test_views.py`（照 `app/users/tests/test_views.py`，用 `client` fixture）。
每個端點驗**狀態碼與 `BaseResponse` body**；寫入後再透過 API 讀回確認；涵蓋 404、409、422。

### 5. Admin（`admin.py`）

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
    form_columns = [Product.name]  # 時間戳、id 不放進表單
```

機密欄位（token、hash）不放進 `column_list` 與 `form_columns`。

## 註冊（每一項都要做）

1. `app/main.py`：
   ```python
   from app.products import views as product_views
   from app.products.admin import ProductAdmin

   admin.add_view(ProductAdmin)
   app.include_router(product_views.router, prefix="/api/v1")
   ```
2. `alembic/env.py`：`from app.products.models import Product  # noqa`

## 需要呼叫第三方 API 時（`external_services.py`）

`httpx` 只能在這個檔案 import（ruff `TID251`）。每個呼叫都要 timeout、`[External]` log、失敗轉成 `ExternalAPIException`：

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

由 service 呼叫，不要從 views 直接呼叫。測試用 `monkeypatch` 替換這個函式，**不要打真實 API**。

## 完成清單

每一項用三種狀態之一回報，沒實際跑過的不要打勾：
`[x]` 已驗證 · `[ ]` 未完成 · `[ ] ⛔ <原因>` 無法驗證（例如 Docker 沒開）。

- [ ] migration 已產生、已 review、`make migrate` 成功
- [ ] model 已加進 `alembic/env.py`
- [ ] router 已 `include_router`；admin 已 `add_view`
- [ ] service 測試通過（在寫 views 之前）
- [ ] endpoint 測試通過，含 404／409／422 與 `BaseResponse` body
- [ ] 沒有建立用不到的空檔案
- [ ] **check** skill 通過

## 常見陷阱

- 忘了 `alembic/env.py` 的 import：autogenerate 看不到新 model，產生空的 migration；表已存在時甚至會產生 `drop_table`。
- 忘了 `include_router`：每個端點都回 404。
- 回傳 ORM 物件而不是 `BaseResponse(data=...)`：response validation 失敗變 500。
- 名稱重複丟 `ValidationException`（400）：應該是 `ConflictException`（409）。
- 列表沒 `order_by()`：分頁結果每次不同。
- 時間欄位沒加 `timezone=True`：存成 `timestamp without time zone`，違反「時間一律 UTC」。
- 在既有資料表新增 `NOT NULL` 欄位只用一個 migration：部署期間舊版程式碼還在寫入，不會填這個欄位。要分 nullable → backfill → 加約束。
- `make makemigrations` 跑在 app 容器內：要先 `make up`，且 `.env.local` 存在。
