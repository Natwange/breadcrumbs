"""add incident reasoning columns

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-12 17:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "investigation_runs", sa.Column("executive_summary", sa.Text(), nullable=True)
    )
    op.add_column(
        "investigation_runs", sa.Column("reasoning_status", sa.String(length=50), nullable=True)
    )
    op.create_index(
        op.f("ix_investigation_runs_reasoning_status"),
        "investigation_runs",
        ["reasoning_status"],
        unique=False,
    )
    op.add_column(
        "investigation_runs",
        sa.Column(
            "reasoning_tracking",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )
    op.add_column("hypotheses", sa.Column("supporting_evidence_ids", sa.JSON(), nullable=True))
    op.add_column("hypotheses", sa.Column("contradicting_evidence_ids", sa.JSON(), nullable=True))
    op.add_column("hypotheses", sa.Column("reasoning_source", sa.String(length=50), nullable=True))
    op.add_column(
        "suggested_actions",
        sa.Column("requires_human_approval", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column(
        "suggested_actions", sa.Column("reasoning_source", sa.String(length=50), nullable=True)
    )
    op.add_column(
        "suggested_actions", sa.Column("supporting_evidence_ids", sa.JSON(), nullable=True)
    )
    op.add_column("slack_drafts", sa.Column("reasoning_source", sa.String(length=50), nullable=True))
    op.add_column(
        "incident_impacts",
        sa.Column("investigation_run_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        op.f("ix_incident_impacts_investigation_run_id"),
        "incident_impacts",
        ["investigation_run_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_incident_impacts_investigation_run_id",
        "incident_impacts",
        "investigation_runs",
        ["investigation_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_incident_impacts_investigation_run_id", "incident_impacts", type_="foreignkey"
    )
    op.drop_index(op.f("ix_incident_impacts_investigation_run_id"), table_name="incident_impacts")
    op.drop_column("incident_impacts", "investigation_run_id")
    op.drop_column("slack_drafts", "reasoning_source")
    op.drop_column("suggested_actions", "supporting_evidence_ids")
    op.drop_column("suggested_actions", "reasoning_source")
    op.drop_column("suggested_actions", "requires_human_approval")
    op.drop_column("hypotheses", "reasoning_source")
    op.drop_column("hypotheses", "contradicting_evidence_ids")
    op.drop_column("hypotheses", "supporting_evidence_ids")
    op.drop_column("investigation_runs", "reasoning_tracking")
    op.drop_index(op.f("ix_investigation_runs_reasoning_status"), table_name="investigation_runs")
    op.drop_column("investigation_runs", "reasoning_status")
    op.drop_column("investigation_runs", "executive_summary")
