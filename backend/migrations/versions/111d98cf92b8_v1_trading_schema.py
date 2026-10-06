"""v1 trading schema

Revision ID: 111d98cf92b8
Revises:
Create Date: 2026-10-06 17:09:25.735649

Creates the Version 1 application tables supporting the future pipeline:

    Signal/Strategy → Trade Proposal → Risk → Validation → Router → Broker Adapter

Historical trading rows use ON DELETE RESTRICT (or SET NULL) so deleting a
strategy/account cannot cascade-wipe orders, executions, or proposals.
Assignment junction rows may CASCADE. No broker API secrets are stored.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "111d98cf92b8"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("actor_type", sa.String(length=64), nullable=False),
        sa.Column("actor_reference", sa.String(length=255), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_events_actor_created",
        "audit_events",
        ["actor_type", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_entity",
        "audit_events",
        ["entity_type", "entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_type_created",
        "audit_events",
        ["event_type", "created_at"],
        unique=False,
    )

    op.create_table(
        "broker_accounts",
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("broker", sa.String(length=64), nullable=False),
        sa.Column("external_account_id", sa.String(length=128), nullable=True),
        sa.Column("account_type", sa.String(length=64), nullable=True),
        sa.Column(
            "trading_mode",
            sa.Enum("paper", "live", name="broker_account_trading_mode", native_enum=False),
            server_default="paper",
            nullable=False,
        ),
        sa.Column("is_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_broker_accounts_broker"), "broker_accounts", ["broker"], unique=False)

    op.create_table(
        "risk_policies",
        sa.Column(
            "scope_type",
            sa.Enum(
                "global",
                "broker_account",
                "strategy",
                "strategy_account",
                name="risk_scope_type",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("scope_id", sa.Uuid(), nullable=True),
        sa.Column("max_position_value", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("max_position_percent", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("max_daily_loss", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("max_open_positions", sa.Integer(), nullable=True),
        sa.Column("max_order_value", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("max_total_exposure", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("require_stop_loss", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_risk_policies_scope",
        "risk_policies",
        ["scope_type", "scope_id"],
        unique=False,
    )

    op.create_table(
        "strategies",
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("strategy_type", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), server_default="0.1.0", nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "development",
                "backtesting",
                "paper",
                "live_eligible",
                "paused",
                "retired",
                name="strategy_status",
                native_enum=False,
            ),
            server_default="development",
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_strategies_status"), "strategies", ["status"], unique=False)
    op.create_index(
        op.f("ix_strategies_strategy_type"),
        "strategies",
        ["strategy_type"],
        unique=False,
    )

    op.create_table(
        "positions",
        sa.Column("broker_account_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column(
            "asset_class",
            sa.Enum(
                "forex",
                "equity",
                "futures",
                "crypto",
                "option",
                "other",
                name="position_asset_class",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("average_entry_price", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("current_price", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column(
            "realized_pnl",
            sa.Numeric(precision=24, scale=8),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "unrealized_pnl",
            sa.Numeric(precision=24, scale=8),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("open", "closed", "flattening", name="position_status", native_enum=False),
            server_default="open",
            nullable=False,
        ),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["broker_account_id"], ["broker_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_positions_account_status",
        "positions",
        ["broker_account_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_positions_account_strategy_symbol",
        "positions",
        ["broker_account_id", "strategy_id", "symbol"],
        unique=False,
    )
    op.create_index(
        "ix_positions_symbol_status",
        "positions",
        ["symbol", "status"],
        unique=False,
    )

    op.create_table(
        "strategy_account_assignments",
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("broker_account_id", sa.Uuid(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "trading_mode",
            sa.Enum("paper", "live", name="assignment_trading_mode", native_enum=False),
            server_default="paper",
            nullable=False,
        ),
        sa.Column("capital_allocation", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("max_position_size", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("daily_loss_limit", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("max_concurrent_positions", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["broker_account_id"], ["broker_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "strategy_id",
            "broker_account_id",
            name="uq_strategy_account_assignment",
        ),
    )
    op.create_index(
        op.f("ix_strategy_account_assignments_broker_account_id"),
        "strategy_account_assignments",
        ["broker_account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_strategy_account_assignments_strategy_id"),
        "strategy_account_assignments",
        ["strategy_id"],
        unique=False,
    )

    op.create_table(
        "trade_proposals",
        sa.Column("strategy_id", sa.Uuid(), nullable=True),
        sa.Column("broker_account_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column(
            "asset_class",
            sa.Enum(
                "forex",
                "equity",
                "futures",
                "crypto",
                "option",
                "other",
                name="trade_proposal_asset_class",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "side",
            sa.Enum("buy", "sell", name="trade_proposal_side", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "order_type",
            sa.Enum(
                "market",
                "limit",
                "stop",
                "stop_limit",
                name="trade_proposal_order_type",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("limit_price", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("stop_price", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("take_profit_price", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column(
            "time_in_force",
            sa.Enum("day", "gtc", "ioc", "fok", name="trade_proposal_tif", native_enum=False),
            server_default="day",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "risk_rejected",
                "risk_approved",
                "validation_rejected",
                "validated",
                "routed",
                "submitted",
                "cancelled",
                "expired",
                name="trade_proposal_status",
                native_enum=False,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("signal_reference", sa.String(length=255), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["broker_account_id"], ["broker_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_trade_proposals_broker_account_status",
        "trade_proposals",
        ["broker_account_id", "status"],
        unique=False,
    )
    op.create_index(op.f("ix_trade_proposals_source"), "trade_proposals", ["source"], unique=False)
    op.create_index(op.f("ix_trade_proposals_status"), "trade_proposals", ["status"], unique=False)
    op.create_index(
        "ix_trade_proposals_strategy_created",
        "trade_proposals",
        ["strategy_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_trade_proposals_symbol_created",
        "trade_proposals",
        ["symbol", "created_at"],
        unique=False,
    )

    op.create_table(
        "market_memory_events",
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column(
            "asset_class",
            sa.Enum(
                "forex",
                "equity",
                "futures",
                "crypto",
                "option",
                "other",
                name="market_memory_asset_class",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column(
            "event_time",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "market_context",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=True),
        sa.Column("trade_proposal_id", sa.Uuid(), nullable=True),
        sa.Column("outcome", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["trade_proposal_id"], ["trade_proposals.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_market_memory_events_event_time"),
        "market_memory_events",
        ["event_time"],
        unique=False,
    )
    op.create_index(
        op.f("ix_market_memory_events_event_type"),
        "market_memory_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_market_memory_proposal",
        "market_memory_events",
        ["trade_proposal_id"],
        unique=False,
    )
    op.create_index(
        "ix_market_memory_strategy_event_time",
        "market_memory_events",
        ["strategy_id", "event_time"],
        unique=False,
    )
    op.create_index(
        "ix_market_memory_symbol_event_time",
        "market_memory_events",
        ["symbol", "event_time"],
        unique=False,
    )

    op.create_table(
        "orders",
        sa.Column("trade_proposal_id", sa.Uuid(), nullable=False),
        sa.Column("broker_account_id", sa.Uuid(), nullable=False),
        sa.Column("broker_order_id", sa.String(length=128), nullable=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column(
            "asset_class",
            sa.Enum(
                "forex",
                "equity",
                "futures",
                "crypto",
                "option",
                "other",
                name="order_asset_class",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "side",
            sa.Enum("buy", "sell", name="order_side", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "order_type",
            sa.Enum(
                "market",
                "limit",
                "stop",
                "stop_limit",
                name="order_order_type",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("limit_price", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("stop_price", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "new",
                "submitted",
                "partially_filled",
                "filled",
                "cancelled",
                "rejected",
                "expired",
                name="order_status",
                native_enum=False,
            ),
            server_default="new",
            nullable=False,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["broker_account_id"], ["broker_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["trade_proposal_id"], ["trade_proposals.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_orders_broker_account_status",
        "orders",
        ["broker_account_id", "status"],
        unique=False,
    )
    op.create_index(op.f("ix_orders_broker_order_id"), "orders", ["broker_order_id"], unique=False)
    op.create_index(
        "ix_orders_proposal_created",
        "orders",
        ["trade_proposal_id", "created_at"],
        unique=False,
    )
    op.create_index(op.f("ix_orders_status"), "orders", ["status"], unique=False)
    op.create_index(
        "ix_orders_symbol_created",
        "orders",
        ["symbol", "created_at"],
        unique=False,
    )

    op.create_table(
        "executions",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("broker_execution_id", sa.String(length=128), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("price", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("commission", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_executions_broker_execution_id"),
        "executions",
        ["broker_execution_id"],
        unique=False,
    )
    op.create_index(
        "ix_executions_order_executed",
        "executions",
        ["order_id", "executed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_executions_order_executed", table_name="executions")
    op.drop_index(op.f("ix_executions_broker_execution_id"), table_name="executions")
    op.drop_table("executions")
    op.drop_index("ix_orders_symbol_created", table_name="orders")
    op.drop_index(op.f("ix_orders_status"), table_name="orders")
    op.drop_index("ix_orders_proposal_created", table_name="orders")
    op.drop_index(op.f("ix_orders_broker_order_id"), table_name="orders")
    op.drop_index("ix_orders_broker_account_status", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_market_memory_symbol_event_time", table_name="market_memory_events")
    op.drop_index("ix_market_memory_strategy_event_time", table_name="market_memory_events")
    op.drop_index("ix_market_memory_proposal", table_name="market_memory_events")
    op.drop_index(op.f("ix_market_memory_events_event_type"), table_name="market_memory_events")
    op.drop_index(op.f("ix_market_memory_events_event_time"), table_name="market_memory_events")
    op.drop_table("market_memory_events")
    op.drop_index("ix_trade_proposals_symbol_created", table_name="trade_proposals")
    op.drop_index("ix_trade_proposals_strategy_created", table_name="trade_proposals")
    op.drop_index(op.f("ix_trade_proposals_status"), table_name="trade_proposals")
    op.drop_index(op.f("ix_trade_proposals_source"), table_name="trade_proposals")
    op.drop_index("ix_trade_proposals_broker_account_status", table_name="trade_proposals")
    op.drop_table("trade_proposals")
    op.drop_index(
        op.f("ix_strategy_account_assignments_strategy_id"),
        table_name="strategy_account_assignments",
    )
    op.drop_index(
        op.f("ix_strategy_account_assignments_broker_account_id"),
        table_name="strategy_account_assignments",
    )
    op.drop_table("strategy_account_assignments")
    op.drop_index("ix_positions_symbol_status", table_name="positions")
    op.drop_index("ix_positions_account_strategy_symbol", table_name="positions")
    op.drop_index("ix_positions_account_status", table_name="positions")
    op.drop_table("positions")
    op.drop_index(op.f("ix_strategies_strategy_type"), table_name="strategies")
    op.drop_index(op.f("ix_strategies_status"), table_name="strategies")
    op.drop_table("strategies")
    op.drop_index("ix_risk_policies_scope", table_name="risk_policies")
    op.drop_table("risk_policies")
    op.drop_index(op.f("ix_broker_accounts_broker"), table_name="broker_accounts")
    op.drop_table("broker_accounts")
    op.drop_index("ix_audit_events_type_created", table_name="audit_events")
    op.drop_index("ix_audit_events_entity", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_created", table_name="audit_events")
    op.drop_table("audit_events")
