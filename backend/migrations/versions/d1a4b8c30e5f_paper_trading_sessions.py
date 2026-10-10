"""Add paper_trading_sessions and processed-bar idempotency ledger.

Revision ID: d1a4b8c30e5f
Revises: c9e3f1b20a4d
Create Date: 2026-10-10 13:00:00.000000

Why this migration is required
------------------------------
Controlled Paper Session Runner V1 needs durable session lifecycle state,
worker leases, and per-bar idempotency keys. Process-local memory is unsafe
for crash recovery and concurrent worker protection.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d1a4b8c30e5f"
down_revision: str | None = "c9e3f1b20a4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATES = (
    "created",
    "ready",
    "running",
    "pausing",
    "paused",
    "stopping",
    "stopped",
    "failed",
)


def upgrade() -> None:
    op.create_table(
        "paper_trading_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_db_id", sa.Uuid(), nullable=True),
        sa.Column("engine_strategy_id", sa.String(length=128), nullable=False),
        sa.Column("strategy_version", sa.String(length=32), nullable=False),
        sa.Column("parameter_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("qualification_approval_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("broker_account_id", sa.Uuid(), nullable=False),
        sa.Column("instrument", sa.String(length=64), nullable=False),
        sa.Column("timeframe", sa.String(length=32), nullable=False),
        sa.Column(
            "session_state",
            sa.String(length=32),
            server_default="created",
            nullable=False,
        ),
        sa.Column(
            "execution_mode",
            sa.String(length=32),
            server_default="dry_run",
            nullable=False,
        ),
        sa.Column("start_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_processed_bar_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("stop_reason", sa.Text(), nullable=True),
        sa.Column(
            "risk_limits",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "orders_submitted_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "max_orders_per_session",
            sa.Integer(),
            server_default=sa.text("50"),
            nullable=False,
        ),
        sa.Column("worker_lease_owner", sa.String(length=128), nullable=True),
        sa.Column("worker_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "state_version",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("failure_detail", sa.Text(), nullable=True),
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
            ["broker_account_id"],
            ["broker_accounts.id"],
            name="fk_paper_sessions_broker_account",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["qualification_approval_id"],
            ["strategy_paper_qualifications.id"],
            name="fk_paper_sessions_qualification",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_db_id"],
            ["strategies.id"],
            name="fk_paper_sessions_strategy",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "execution_mode IN ('dry_run', 'paper_execute')",
            name="ck_paper_sessions_execution_mode",
        ),
        sa.CheckConstraint(
            "orders_submitted_count >= 0 AND max_orders_per_session > 0",
            name="ck_paper_sessions_order_counts",
        ),
        sa.CheckConstraint("state_version >= 0", name="ck_paper_sessions_state_version"),
        sa.CheckConstraint(
            "session_state IN (" + ", ".join(f"'{s}'" for s in _STATES) + ")",
            name="ck_paper_sessions_state_values",
        ),
    )
    op.create_index(
        "ix_paper_sessions_account_state",
        "paper_trading_sessions",
        ["broker_account_id", "session_state"],
        unique=False,
    )
    op.create_index(
        "ix_paper_sessions_strategy_state",
        "paper_trading_sessions",
        ["engine_strategy_id", "session_state"],
        unique=False,
    )
    op.create_index(
        "ix_paper_sessions_lease",
        "paper_trading_sessions",
        ["worker_lease_expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_paper_trading_sessions_session_state",
        "paper_trading_sessions",
        ["session_state"],
        unique=False,
    )
    op.create_index(
        "ix_paper_trading_sessions_broker_account_id",
        "paper_trading_sessions",
        ["broker_account_id"],
        unique=False,
    )
    op.create_index(
        "ix_paper_trading_sessions_qualification_approval_id",
        "paper_trading_sessions",
        ["qualification_approval_id"],
        unique=False,
    )
    op.create_index(
        "ix_paper_trading_sessions_strategy_db_id",
        "paper_trading_sessions",
        ["strategy_db_id"],
        unique=False,
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_paper_sessions_one_active_per_account
        ON paper_trading_sessions (broker_account_id)
        WHERE session_state IN (
            'created','ready','running','pausing','paused','stopping'
        )
        """
    )

    op.create_table(
        "paper_session_processed_bars",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("bar_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision_identity", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=True),
        sa.Column(
            "outcome",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
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
            ["session_id"],
            ["paper_trading_sessions.id"],
            name="fk_paper_session_processed_session",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "idempotency_key",
            name="uq_paper_session_idempotency_key",
        ),
        sa.UniqueConstraint(
            "session_id",
            "bar_timestamp",
            "decision_identity",
            name="uq_paper_session_bar_decision",
        ),
    )
    op.create_index(
        "ix_paper_session_processed_session",
        "paper_session_processed_bars",
        ["session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_paper_session_processed_session",
        table_name="paper_session_processed_bars",
    )
    op.drop_table("paper_session_processed_bars")
    op.execute("DROP INDEX IF EXISTS uq_paper_sessions_one_active_per_account")
    op.drop_index(
        "ix_paper_trading_sessions_strategy_db_id",
        table_name="paper_trading_sessions",
    )
    op.drop_index(
        "ix_paper_trading_sessions_qualification_approval_id",
        table_name="paper_trading_sessions",
    )
    op.drop_index(
        "ix_paper_trading_sessions_broker_account_id",
        table_name="paper_trading_sessions",
    )
    op.drop_index(
        "ix_paper_trading_sessions_session_state",
        table_name="paper_trading_sessions",
    )
    op.drop_index("ix_paper_sessions_lease", table_name="paper_trading_sessions")
    op.drop_index("ix_paper_sessions_strategy_state", table_name="paper_trading_sessions")
    op.drop_index("ix_paper_sessions_account_state", table_name="paper_trading_sessions")
    op.drop_table("paper_trading_sessions")
