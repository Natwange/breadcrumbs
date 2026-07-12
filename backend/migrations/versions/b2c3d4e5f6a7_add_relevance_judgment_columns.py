"""add relevance judgment columns

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-12 16:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("evidence", sa.Column("relevance_label", sa.String(length=20), nullable=True))
    op.add_column(
        "evidence", sa.Column("relevance_confidence", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "evidence", sa.Column("relevance_source", sa.String(length=50), nullable=True)
    )
    op.create_index(
        op.f("ix_evidence_relevance_source"), "evidence", ["relevance_source"], unique=False
    )
    op.add_column(
        "investigation_runs",
        sa.Column(
            "relevance_tracking",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("investigation_runs", "relevance_tracking")
    op.drop_index(op.f("ix_evidence_relevance_source"), table_name="evidence")
    op.drop_column("evidence", "relevance_source")
    op.drop_column("evidence", "relevance_confidence")
    op.drop_column("evidence", "relevance_label")
