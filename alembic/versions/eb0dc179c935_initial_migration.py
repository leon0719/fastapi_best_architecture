"""Initial migration

Revision ID: eb0dc179c935
Revises:
Create Date: 2025-10-22 22:06:39.918284

這支 migration 原本是空的(`pass`)。當時 app 啟動時會呼叫
`Base.metadata.create_all()` 建表,所以 alembic autogenerate 是對著「已經存在的
資料庫」產生的 —— 只產得出差異,建表本身從未進到 migration 裡。
後來 create_all 被移除(改由 Alembic 全權管理 schema),就留下一個破口:
乾淨的資料庫跑 `alembic upgrade head` 會在下一支 migration 的
`ALTER TABLE chatbots` 直接失敗,因為那張表根本沒被建立過。

這裡補回當時應該產生的建表語句。刻意只建「該時點」的欄位:
chatbots 的 name/description/created_at/updated_at 由 a6c712365498 補上,
system_prompt/is_active 由 eae3995f6a19 補上 —— 保持 migration 鏈的語意正確,
已經套用過舊版鏈的資料庫也不受影響。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "eb0dc179c935"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_name"), "users", ["name"], unique=False)

    # 僅有 id:其餘欄位由後續兩支 migration 依序加上。
    op.create_table(
        "chatbots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("chatbots")
    op.drop_index(op.f("ix_users_name"), table_name="users")
    op.drop_table("users")
