"""add postmortem structured sections columns

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-12 17:15:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "postmortems",
        sa.Column("investigation_run_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        op.f("ix_postmortems_investigation_run_id"),
        "postmortems",
        ["investigation_run_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_postmortems_investigation_run_id",
        "postmortems",
        "investigation_runs",
        ["investigation_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "postmortems",
        sa.Column(
            "sections",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("postmortems", "sections")
    op.drop_constraint("fk_postmortems_investigation_run_id", "postmortems", type_="foreignkey")
    op.drop_index(op.f("ix_postmortems_investigation_run_id"), table_name="postmortems")
    op.drop_column("postmortems", "investigation_run_id")
