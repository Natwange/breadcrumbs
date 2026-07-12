"""add embedding vector and text snapshot columns

Revision ID: a1b2c3d4e5f6
Revises: 135d922b7017
Create Date: 2026-07-12 16:05:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "135d922b7017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "embedding_records",
        sa.Column(
            "embedding",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )
    op.add_column(
        "embedding_records",
        sa.Column("text_snapshot", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("embedding_records", "text_snapshot")
    op.drop_column("embedding_records", "embedding")
