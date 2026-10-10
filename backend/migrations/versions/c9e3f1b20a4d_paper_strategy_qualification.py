"""Add strategy_paper_qualifications for paper eligibility approvals.

Revision ID: c9e3f1b20a4d
Revises: b7c1e9a04d2f
Create Date: 2026-10-10 12:00:00.000000

Why this migration is required
------------------------------
Paper Strategy Qualification Gate V1 needs durable approval records with
optimistic concurrency, paper-only scope enforcement, and immutable evidence
bindings. Process-local memory is insufficient for approval state.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9e3f1b20a4d"
down_revision: str | None = "b7c1e9a04d2f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATES = (
    "draft",
    "evaluation_required",
    "evaluated",
    "review_required",
    "approved_for_paper",
    "rejected",
    "revoked",
    "expired",
)


def upgrade() -> None:
    op.create_table(
        "strategy_paper_qualifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=True),
        sa.Column("engine_strategy_id", sa.String(length=128), nullable=False),
        sa.Column("strategy_version", sa.String(length=32), nullable=False),
        sa.Column("parameter_hash", sa.String(length=64), nullable=False),
        sa.Column("evidence_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("evaluation_id", sa.String(length=64), nullable=False),
        sa.Column("dataset_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column(
            "qualification_state",
            sa.String(length=32),
            server_default="draft",
            nullable=False,
        ),
        sa.Column(
            "approval_scope",
            sa.String(length=32),
            server_default="paper_only",
            nullable=False,
        ),
        sa.Column("recommendation", sa.String(length=64), nullable=True),
        sa.Column(
            "report",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "hard_blockers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("approved_by_actor_type", sa.String(length=64), nullable=True),
        sa.Column("approved_by_actor_reference", sa.String(length=255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column(
            "state_version",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            name="fk_paper_qual_strategy_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "engine_strategy_id",
            "strategy_version",
            "parameter_hash",
            "evidence_fingerprint",
            name="uq_paper_qual_evidence_binding",
        ),
        sa.CheckConstraint(
            "approval_scope = 'paper_only'",
            name="ck_paper_qual_scope_paper_only",
        ),
        sa.CheckConstraint(
            "state_version >= 0",
            name="ck_paper_qual_state_version_nonneg",
        ),
        sa.CheckConstraint(
            "qualification_state IN ("
            + ", ".join(f"'{s}'" for s in _STATES)
            + ")",
            name="ck_paper_qual_state_values",
        ),
    )
    op.create_index(
        "ix_paper_qual_engine_state",
        "strategy_paper_qualifications",
        ["engine_strategy_id", "qualification_state"],
        unique=False,
    )
    op.create_index(
        "ix_paper_qual_expires",
        "strategy_paper_qualifications",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_strategy_paper_qualifications_strategy_id",
        "strategy_paper_qualifications",
        ["strategy_id"],
        unique=False,
    )
    op.create_index(
        "ix_strategy_paper_qualifications_qualification_state",
        "strategy_paper_qualifications",
        ["qualification_state"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_strategy_paper_qualifications_qualification_state",
        table_name="strategy_paper_qualifications",
    )
    op.drop_index(
        "ix_strategy_paper_qualifications_strategy_id",
        table_name="strategy_paper_qualifications",
    )
    op.drop_index("ix_paper_qual_expires", table_name="strategy_paper_qualifications")
    op.drop_index("ix_paper_qual_engine_state", table_name="strategy_paper_qualifications")
    op.drop_table("strategy_paper_qualifications")
