"""Add execution realized_pnl and accounting_applied for paper accounting.

Revision ID: b7c1e9a04d2f
Revises: a86f3472f808
Create Date: 2026-10-06 18:10:00.000000

Why this migration is required
------------------------------
1. ``realized_pnl`` on each fill enables reliable same-day realized P&L
   aggregation for Risk Engine daily-loss checks without fragile audit parsing.
2. ``accounting_applied`` provides durable execution-level idempotency so the
   same sim fill cannot mutate positions/P&L twice.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "b7c1e9a04d2f"
down_revision: str | None = "a86f3472f808"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "executions",
        sa.Column(
            "realized_pnl",
            sa.Numeric(precision=24, scale=8),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "executions",
        sa.Column(
            "accounting_applied",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_executions_broker_execution_id",
        "executions",
        ["broker_execution_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_executions_broker_execution_id", table_name="executions")
    op.drop_column("executions", "accounting_applied")
    op.drop_column("executions", "realized_pnl")
