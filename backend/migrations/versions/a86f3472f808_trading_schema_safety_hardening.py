"""trading_schema_safety_hardening

Revision ID: a86f3472f808
Revises: 111d98cf92b8
Create Date: 2026-10-06 17:53:37.576267

Hardens the Version 1 trading schema with fail-closed defaults, proposal
stop-loss semantics, order TIF, composite order/proposal account integrity,
RESTRICT historical FKs, and critical CHECK/UNIQUE invariants.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "a86f3472f808"
down_revision: str | None = "111d98cf92b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- broker_accounts ---
    op.alter_column(
        "broker_accounts",
        "account_type",
        existing_type=sa.VARCHAR(length=64),
        type_=sa.Enum(
            "cash",
            "margin",
            "futures",
            "other",
            name="broker_account_type",
            native_enum=False,
        ),
        nullable=False,
    )
    op.alter_column(
        "broker_accounts",
        "is_enabled",
        existing_type=sa.Boolean(),
        server_default=sa.text("false"),
        existing_nullable=False,
    )
    op.create_unique_constraint("uq_broker_accounts_name", "broker_accounts", ["name"])
    op.create_unique_constraint(
        "uq_broker_accounts_broker_external_account_id",
        "broker_accounts",
        ["broker", "external_account_id"],
    )
    op.create_check_constraint(
        "ck_broker_accounts_name_not_blank",
        "broker_accounts",
        "btrim(name) <> ''",
    )
    op.create_check_constraint(
        "ck_broker_accounts_broker_slug",
        "broker_accounts",
        "broker = lower(btrim(broker)) AND broker <> ''",
    )
    op.create_check_constraint(
        "ck_broker_accounts_account_type",
        "broker_accounts",
        "account_type IN ('cash', 'margin', 'futures', 'other')",
    )
    op.create_check_constraint(
        "ck_broker_accounts_trading_mode",
        "broker_accounts",
        "trading_mode IN ('paper', 'live')",
    )

    # --- strategies ---
    op.drop_constraint("strategies_name_key", "strategies", type_="unique")
    op.create_unique_constraint(
        "uq_strategies_name_version",
        "strategies",
        ["name", "version"],
    )
    op.create_check_constraint(
        "ck_strategies_name_not_blank",
        "strategies",
        "btrim(name) <> ''",
    )
    op.create_check_constraint(
        "ck_strategies_status",
        "strategies",
        "status IN ("
        "'development', 'backtesting', 'paper', 'live_eligible', 'paused', 'retired'"
        ")",
    )

    # --- strategy_account_assignments ---
    op.alter_column(
        "strategy_account_assignments",
        "is_enabled",
        existing_type=sa.Boolean(),
        server_default=sa.text("false"),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_strategy_account_assignments_limits_valid",
        "strategy_account_assignments",
        "(capital_allocation IS NULL OR capital_allocation >= 0)"
        " AND (max_position_size IS NULL OR max_position_size > 0)"
        " AND (daily_loss_limit IS NULL OR daily_loss_limit >= 0)"
        " AND (max_concurrent_positions IS NULL OR max_concurrent_positions > 0)",
    )
    op.create_check_constraint(
        "ck_strategy_account_assignments_trading_mode",
        "strategy_account_assignments",
        "trading_mode IN ('paper', 'live')",
    )

    # --- trade_proposals ---
    op.add_column(
        "trade_proposals",
        sa.Column("stop_loss_price", sa.Numeric(precision=24, scale=8), nullable=True),
    )
    op.alter_column(
        "trade_proposals",
        "source",
        existing_type=sa.VARCHAR(length=64),
        type_=sa.Enum(
            "strategy",
            "ai",
            "telegram",
            "discord",
            "manual",
            "external",
            name="trade_proposal_source",
            native_enum=False,
        ),
        existing_nullable=False,
    )
    op.create_unique_constraint(
        "uq_trade_proposals_id_broker_account_id",
        "trade_proposals",
        ["id", "broker_account_id"],
    )
    op.drop_constraint("trade_proposals_strategy_id_fkey", "trade_proposals", type_="foreignkey")
    op.create_foreign_key(
        "fk_trade_proposals_strategy_id",
        "trade_proposals",
        "strategies",
        ["strategy_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_trade_proposals_quantity_positive",
        "trade_proposals",
        "quantity > 0",
    )
    op.create_check_constraint(
        "ck_trade_proposals_prices_non_negative",
        "trade_proposals",
        "(limit_price IS NULL OR limit_price >= 0)"
        " AND (stop_price IS NULL OR stop_price >= 0)"
        " AND (take_profit_price IS NULL OR take_profit_price >= 0)"
        " AND (stop_loss_price IS NULL OR stop_loss_price >= 0)",
    )
    op.create_check_constraint(
        "ck_trade_proposals_strategy_source",
        "trade_proposals",
        "(source <> 'strategy') OR (strategy_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_trade_proposals_source",
        "trade_proposals",
        "source IN ('strategy', 'ai', 'telegram', 'discord', 'manual', 'external')",
    )
    op.create_check_constraint(
        "ck_trade_proposals_side",
        "trade_proposals",
        "side IN ('buy', 'sell')",
    )
    op.create_check_constraint(
        "ck_trade_proposals_order_type",
        "trade_proposals",
        "order_type IN ('market', 'limit', 'stop', 'stop_limit')",
    )
    op.create_check_constraint(
        "ck_trade_proposals_tif",
        "trade_proposals",
        "time_in_force IN ('day', 'gtc', 'ioc', 'fok')",
    )
    op.create_check_constraint(
        "ck_trade_proposals_status",
        "trade_proposals",
        "status IN ("
        "'pending', 'risk_rejected', 'risk_approved', 'validation_rejected',"
        " 'validated', 'routed', 'submitted', 'cancelled', 'expired'"
        ")",
    )
    op.create_check_constraint(
        "ck_trade_proposals_asset_class",
        "trade_proposals",
        "asset_class IN ('forex', 'equity', 'futures', 'crypto', 'option', 'other')",
    )

    # --- orders ---
    op.add_column(
        "orders",
        sa.Column(
            "time_in_force",
            sa.Enum("day", "gtc", "ioc", "fok", name="order_tif", native_enum=False),
            server_default="day",
            nullable=False,
        ),
    )
    op.drop_index("ix_orders_broker_order_id", table_name="orders")
    op.create_unique_constraint(
        "uq_orders_broker_account_id_broker_order_id",
        "orders",
        ["broker_account_id", "broker_order_id"],
    )
    op.drop_constraint("orders_trade_proposal_id_fkey", "orders", type_="foreignkey")
    op.create_foreign_key(
        "fk_orders_trade_proposal_account",
        "orders",
        "trade_proposals",
        ["trade_proposal_id", "broker_account_id"],
        ["id", "broker_account_id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_orders_quantity_positive",
        "orders",
        "quantity > 0",
    )
    op.create_check_constraint(
        "ck_orders_prices_non_negative",
        "orders",
        "(limit_price IS NULL OR limit_price >= 0)"
        " AND (stop_price IS NULL OR stop_price >= 0)",
    )
    op.create_check_constraint(
        "ck_orders_side",
        "orders",
        "side IN ('buy', 'sell')",
    )
    op.create_check_constraint(
        "ck_orders_order_type",
        "orders",
        "order_type IN ('market', 'limit', 'stop', 'stop_limit')",
    )
    op.create_check_constraint(
        "ck_orders_tif",
        "orders",
        "time_in_force IN ('day', 'gtc', 'ioc', 'fok')",
    )
    op.create_check_constraint(
        "ck_orders_status",
        "orders",
        "status IN ("
        "'new', 'submitted', 'partially_filled', 'filled',"
        " 'cancelled', 'rejected', 'expired'"
        ")",
    )
    op.create_check_constraint(
        "ck_orders_asset_class",
        "orders",
        "asset_class IN ('forex', 'equity', 'futures', 'crypto', 'option', 'other')",
    )

    # --- executions ---
    op.drop_index("ix_executions_broker_execution_id", table_name="executions")
    op.create_unique_constraint(
        "uq_executions_order_id_broker_execution_id",
        "executions",
        ["order_id", "broker_execution_id"],
    )
    op.create_check_constraint(
        "ck_executions_quantity_positive",
        "executions",
        "quantity > 0",
    )
    op.create_check_constraint(
        "ck_executions_price_non_negative",
        "executions",
        "price >= 0",
    )
    op.create_check_constraint(
        "ck_executions_commission_non_negative",
        "executions",
        "commission IS NULL OR commission >= 0",
    )

    # --- positions ---
    op.create_index(
        "uq_positions_open_account_strategy_symbol_asset",
        "positions",
        ["broker_account_id", "strategy_id", "symbol", "asset_class"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.drop_constraint("positions_strategy_id_fkey", "positions", type_="foreignkey")
    op.create_foreign_key(
        "fk_positions_strategy_id",
        "positions",
        "strategies",
        ["strategy_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_positions_prices_non_negative",
        "positions",
        "average_entry_price >= 0 AND (current_price IS NULL OR current_price >= 0)",
    )
    op.create_check_constraint(
        "ck_positions_open_closed_consistent",
        "positions",
        "("
        "  (status = 'open' AND closed_at IS NULL AND quantity <> 0)"
        "  OR (status = 'closed' AND closed_at IS NOT NULL)"
        "  OR (status = 'flattening')"
        ")",
    )
    op.create_check_constraint(
        "ck_positions_status",
        "positions",
        "status IN ('open', 'closed', 'flattening')",
    )
    op.create_check_constraint(
        "ck_positions_asset_class",
        "positions",
        "asset_class IN ('forex', 'equity', 'futures', 'crypto', 'option', 'other')",
    )

    # --- risk_policies ---
    op.alter_column(
        "risk_policies",
        "require_stop_loss",
        existing_type=sa.Boolean(),
        server_default=sa.text("true"),
        existing_nullable=False,
    )
    op.create_index(
        "uq_risk_policies_global",
        "risk_policies",
        ["scope_type"],
        unique=True,
        postgresql_where=sa.text("scope_type = 'global'"),
    )
    op.create_index(
        "uq_risk_policies_scope",
        "risk_policies",
        ["scope_type", "scope_id"],
        unique=True,
        postgresql_where=sa.text("scope_id IS NOT NULL"),
    )
    op.create_check_constraint(
        "ck_risk_policies_scope_id_matches_type",
        "risk_policies",
        "(scope_type = 'global') = (scope_id IS NULL)",
    )
    op.create_check_constraint(
        "ck_risk_policies_limits_valid",
        "risk_policies",
        "(max_position_value IS NULL OR max_position_value > 0)"
        " AND (max_position_percent IS NULL OR (max_position_percent > 0 AND max_position_percent <= 100))"
        " AND (max_daily_loss IS NULL OR max_daily_loss >= 0)"
        " AND (max_order_value IS NULL OR max_order_value > 0)"
        " AND (max_total_exposure IS NULL OR max_total_exposure > 0)"
        " AND (max_open_positions IS NULL OR max_open_positions > 0)",
    )
    op.create_check_constraint(
        "ck_risk_policies_scope_type",
        "risk_policies",
        "scope_type IN ('global', 'broker_account', 'strategy', 'strategy_account')",
    )

    # --- market_memory_events ---
    op.drop_constraint(
        "market_memory_events_strategy_id_fkey",
        "market_memory_events",
        type_="foreignkey",
    )
    op.drop_constraint(
        "market_memory_events_trade_proposal_id_fkey",
        "market_memory_events",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_market_memory_events_strategy_id",
        "market_memory_events",
        "strategies",
        ["strategy_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_market_memory_events_trade_proposal_id",
        "market_memory_events",
        "trade_proposals",
        ["trade_proposal_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_market_memory_events_asset_class",
        "market_memory_events",
        "asset_class IN ('forex', 'equity', 'futures', 'crypto', 'option', 'other')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_market_memory_events_asset_class",
        "market_memory_events",
        type_="check",
    )
    op.drop_constraint(
        "fk_market_memory_events_trade_proposal_id",
        "market_memory_events",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_market_memory_events_strategy_id",
        "market_memory_events",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "market_memory_events_trade_proposal_id_fkey",
        "market_memory_events",
        "trade_proposals",
        ["trade_proposal_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "market_memory_events_strategy_id_fkey",
        "market_memory_events",
        "strategies",
        ["strategy_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint("ck_risk_policies_scope_type", "risk_policies", type_="check")
    op.drop_constraint("ck_risk_policies_limits_valid", "risk_policies", type_="check")
    op.drop_constraint("ck_risk_policies_scope_id_matches_type", "risk_policies", type_="check")
    op.drop_index(
        "uq_risk_policies_scope",
        table_name="risk_policies",
        postgresql_where=sa.text("scope_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_risk_policies_global",
        table_name="risk_policies",
        postgresql_where=sa.text("scope_type = 'global'"),
    )
    op.alter_column(
        "risk_policies",
        "require_stop_loss",
        existing_type=sa.Boolean(),
        server_default=sa.text("false"),
        existing_nullable=False,
    )

    op.drop_constraint("ck_positions_asset_class", "positions", type_="check")
    op.drop_constraint("ck_positions_status", "positions", type_="check")
    op.drop_constraint("ck_positions_open_closed_consistent", "positions", type_="check")
    op.drop_constraint("ck_positions_prices_non_negative", "positions", type_="check")
    op.drop_constraint("fk_positions_strategy_id", "positions", type_="foreignkey")
    op.create_foreign_key(
        "positions_strategy_id_fkey",
        "positions",
        "strategies",
        ["strategy_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_index(
        "uq_positions_open_account_strategy_symbol_asset",
        table_name="positions",
        postgresql_where=sa.text("status = 'open'"),
    )

    op.drop_constraint("ck_executions_commission_non_negative", "executions", type_="check")
    op.drop_constraint("ck_executions_price_non_negative", "executions", type_="check")
    op.drop_constraint("ck_executions_quantity_positive", "executions", type_="check")
    op.drop_constraint(
        "uq_executions_order_id_broker_execution_id",
        "executions",
        type_="unique",
    )
    op.create_index(
        "ix_executions_broker_execution_id",
        "executions",
        ["broker_execution_id"],
        unique=False,
    )

    op.drop_constraint("ck_orders_asset_class", "orders", type_="check")
    op.drop_constraint("ck_orders_status", "orders", type_="check")
    op.drop_constraint("ck_orders_tif", "orders", type_="check")
    op.drop_constraint("ck_orders_order_type", "orders", type_="check")
    op.drop_constraint("ck_orders_side", "orders", type_="check")
    op.drop_constraint("ck_orders_prices_non_negative", "orders", type_="check")
    op.drop_constraint("ck_orders_quantity_positive", "orders", type_="check")
    op.drop_constraint("fk_orders_trade_proposal_account", "orders", type_="foreignkey")
    op.create_foreign_key(
        "orders_trade_proposal_id_fkey",
        "orders",
        "trade_proposals",
        ["trade_proposal_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "uq_orders_broker_account_id_broker_order_id",
        "orders",
        type_="unique",
    )
    op.create_index("ix_orders_broker_order_id", "orders", ["broker_order_id"], unique=False)
    op.drop_column("orders", "time_in_force")

    op.drop_constraint("ck_trade_proposals_asset_class", "trade_proposals", type_="check")
    op.drop_constraint("ck_trade_proposals_status", "trade_proposals", type_="check")
    op.drop_constraint("ck_trade_proposals_tif", "trade_proposals", type_="check")
    op.drop_constraint("ck_trade_proposals_order_type", "trade_proposals", type_="check")
    op.drop_constraint("ck_trade_proposals_side", "trade_proposals", type_="check")
    op.drop_constraint("ck_trade_proposals_source", "trade_proposals", type_="check")
    op.drop_constraint("ck_trade_proposals_strategy_source", "trade_proposals", type_="check")
    op.drop_constraint("ck_trade_proposals_prices_non_negative", "trade_proposals", type_="check")
    op.drop_constraint("ck_trade_proposals_quantity_positive", "trade_proposals", type_="check")
    op.drop_constraint("fk_trade_proposals_strategy_id", "trade_proposals", type_="foreignkey")
    op.create_foreign_key(
        "trade_proposals_strategy_id_fkey",
        "trade_proposals",
        "strategies",
        ["strategy_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint(
        "uq_trade_proposals_id_broker_account_id",
        "trade_proposals",
        type_="unique",
    )
    op.alter_column(
        "trade_proposals",
        "source",
        existing_type=sa.Enum(
            "strategy",
            "ai",
            "telegram",
            "discord",
            "manual",
            "external",
            name="trade_proposal_source",
            native_enum=False,
        ),
        type_=sa.VARCHAR(length=64),
        existing_nullable=False,
    )
    op.drop_column("trade_proposals", "stop_loss_price")

    op.drop_constraint(
        "ck_strategy_account_assignments_trading_mode",
        "strategy_account_assignments",
        type_="check",
    )
    op.drop_constraint(
        "ck_strategy_account_assignments_limits_valid",
        "strategy_account_assignments",
        type_="check",
    )
    op.alter_column(
        "strategy_account_assignments",
        "is_enabled",
        existing_type=sa.Boolean(),
        server_default=sa.text("true"),
        existing_nullable=False,
    )

    op.drop_constraint("ck_strategies_status", "strategies", type_="check")
    op.drop_constraint("ck_strategies_name_not_blank", "strategies", type_="check")
    op.drop_constraint("uq_strategies_name_version", "strategies", type_="unique")
    op.create_unique_constraint("strategies_name_key", "strategies", ["name"])

    op.drop_constraint("ck_broker_accounts_trading_mode", "broker_accounts", type_="check")
    op.drop_constraint("ck_broker_accounts_account_type", "broker_accounts", type_="check")
    op.drop_constraint("ck_broker_accounts_broker_slug", "broker_accounts", type_="check")
    op.drop_constraint("ck_broker_accounts_name_not_blank", "broker_accounts", type_="check")
    op.drop_constraint(
        "uq_broker_accounts_broker_external_account_id",
        "broker_accounts",
        type_="unique",
    )
    op.drop_constraint("uq_broker_accounts_name", "broker_accounts", type_="unique")
    op.alter_column(
        "broker_accounts",
        "is_enabled",
        existing_type=sa.Boolean(),
        server_default=sa.text("true"),
        existing_nullable=False,
    )
    op.alter_column(
        "broker_accounts",
        "account_type",
        existing_type=sa.Enum(
            "cash",
            "margin",
            "futures",
            "other",
            name="broker_account_type",
            native_enum=False,
        ),
        type_=sa.VARCHAR(length=64),
        nullable=True,
    )
