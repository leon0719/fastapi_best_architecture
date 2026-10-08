"""chatbot timestamps to timestamptz

既有的 created_at/updated_at 是 timestamp without time zone,由 server_default now()
寫入,值在 UTC 時區的 DB session 下產生,所以轉換時以 UTC 解讀。

Revision ID: 3f9c2d7a1b84
Revises: eae3995f6a19
Create Date: 2026-10-08 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3f9c2d7a1b84"
down_revision: Union[str, Sequence[str], None] = "eae3995f6a19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = ("created_at", "updated_at")


def upgrade() -> None:
    """Upgrade schema."""
    for column in _COLUMNS:
        op.alter_column(
            "chatbots",
            column,
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=False,
            existing_server_default=sa.text("now()"),
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    """Downgrade schema."""
    for column in _COLUMNS:
        op.alter_column(
            "chatbots",
            column,
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=False,
            existing_server_default=sa.text("now()"),
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )
