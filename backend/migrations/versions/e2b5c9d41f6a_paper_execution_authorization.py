"""Add paper execution authorization (session-scoped consent).

Revision ID: e2b5c9d41f6a
Revises: d1a4b8c30e5f
Create Date: 2026-10-10 14:00:00.000000

Why this migration is required
------------------------------
Authorized Paper Execute Activation V1 needs durable, revocable,
session-scoped PAPER_EXECUTE consent with expiration and audit fields.
Also adds session submission-block flags for uncertain broker ACKs.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e2b5c9d41f6a"
down_revision: str | None = "d1a4b8c30e5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "paper_trading_sessions",
        sa.Column(
            "submissions_blocked",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "paper_trading_sessions",
        sa.Column("submissions_block_reason", sa.Text(), nullable=True),
    )

    op.create_table(
        "paper_execution_authorizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("broker_account_id", sa.Uuid(), nullable=False),
        sa.Column("owner_subject", sa.String(length=255), nullable=False),
        sa.Column(
            "scope",
            sa.String(length=32),
            server_default="paper_execute",
            nullable=False,
        ),
        sa.Column(
            "consent_state",
            sa.String(length=32),
            server_default="granted",
            nullable=False,
        ),
        sa.Column("authorization_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "paper_endpoint_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("paper_base_url_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "one_time",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.Column(
            "state_version",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "details",
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
        sa.CheckConstraint(
            "consent_state IN ('granted', 'revoked', 'expired', 'consumed')",
            name="ck_paper_exec_auth_state",
        ),
        sa.CheckConstraint(
            "state_version >= 0", name="ck_paper_exec_auth_state_version"
        ),
        sa.CheckConstraint(
            "scope = 'paper_execute'", name="ck_paper_exec_auth_scope_paper_only"
        ),
        sa.ForeignKeyConstraint(
            ["broker_account_id"],
            ["broker_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["paper_trading_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_paper_exec_auth_session_state",
        "paper_execution_authorizations",
        ["session_id", "consent_state"],
    )
    op.create_index(
        "ix_paper_exec_auth_account",
        "paper_execution_authorizations",
        ["broker_account_id"],
    )
    op.create_index(
        "ix_paper_exec_auth_expires",
        "paper_execution_authorizations",
        ["expires_at"],
    )
    op.create_index(
        "ix_paper_execution_authorizations_session_id",
        "paper_execution_authorizations",
        ["session_id"],
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_paper_exec_auth_one_granted_per_session
        ON paper_execution_authorizations (session_id)
        WHERE consent_state = 'granted'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_paper_exec_auth_one_granted_per_session")
    op.drop_index(
        "ix_paper_execution_authorizations_session_id",
        table_name="paper_execution_authorizations",
    )
    op.drop_index("ix_paper_exec_auth_expires", table_name="paper_execution_authorizations")
    op.drop_index("ix_paper_exec_auth_account", table_name="paper_execution_authorizations")
    op.drop_index(
        "ix_paper_exec_auth_session_state", table_name="paper_execution_authorizations"
    )
    op.drop_table("paper_execution_authorizations")
    op.drop_column("paper_trading_sessions", "submissions_block_reason")
    op.drop_column("paper_trading_sessions", "submissions_blocked")
