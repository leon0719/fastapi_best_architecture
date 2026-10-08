# 資料庫遷移（Alembic）

改 model、寫或改 migration 之前讀這份。

## 指令

Migration 一律在 app 容器內執行（`DB_HOST=db` 永遠正確），需先 `make up` 且 `.env.local` 存在。

| 目的 | 指令 |
|---|---|
| 依 model 變更產生 migration | `make makemigrations MSG="Add email to users"` |
| 套用所有 migration | `make migrate` |
| 回退一版 | `make downgrade` |
| 查看歷史與目前版本 | `make migration-history` |

## 流程

1. 改 model；新 model 要加進 `alembic/env.py` 的 import。
2. `make makemigrations MSG="..."`——訊息要具體（「Add email unique constraint」，不是「Update」）。
3. **review 產出的檔案**：
   - autogenerate 會漏掉自訂 index／constraint、型別細節、server default。
   - 不應出現的 `drop_table`／`drop_column`，通常代表某個 model 沒在 `alembic/env.py` import。
4. `make migrate`，接著 `make downgrade` → `make migrate` 驗證來回都能跑。
5. CI 會在真 Postgres 上 `alembic upgrade head`，並用 autogenerate 檢查 model 與 migration 是否一致。

## 規則

- **不要修改已套用的 migration**（任何環境套用過就算）——另外新增一個 migration 修正。
- **Expand／contract**：部署期間新舊版本程式碼會與同一份 schema 短暫並存，所以每個 migration 都要讓**上一版**程式碼繼續運作。
  - 刪欄位、改名：等程式碼不再使用後，放到下一個 release。
  - 在既有資料表新增 NOT NULL 欄位：分成 nullable → backfill → 加約束（見下方範例）。
- 時間欄位一律 `DateTime(timezone=True)`（Postgres `timestamptz`）。
- 資料表 snake_case 複數。
- 改 prod 資料前先備份：`docker compose exec db pg_dump -U postgres fastapi_db > backup.sql`（prod 操作由人執行）。

## 常用寫法

```python
# 在既有資料表新增 NOT NULL 欄位：nullable → backfill → 加約束
def upgrade() -> None:
    op.add_column("users", sa.Column("role", sa.String(20), nullable=True))
    op.execute("UPDATE users SET role = 'user' WHERE role IS NULL")
    op.alter_column("users", "role", nullable=False)


# 新增 index
def upgrade() -> None:
    op.create_index("ix_users_email", "users", ["email"])


# timestamp 轉 timestamptz（既有值以 UTC 解讀），參考 3f9c2d7a1b84
def upgrade() -> None:
    op.alter_column(
        "chatbots",
        "created_at",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )
```

## 疑難排解

- **`make makemigrations` 連不上 DB**：`.env.local` 的 `DB_PASSWORD` 與 DB volume 初始化時的密碼不一致。
  改回 volume 當初用的密碼，或由人執行 `make docker-clean` 清空 volume 後重建（本機資料會消失）。
- **想看 SQL**：暫時把 `app/common/db/database.py` 的 `echo=False` 改成 `True`，用完改回。
