"""Strategy orchestration package.

Strategies emit StrategyDecision / TradeProposal inputs only.
They never place broker orders and must never receive execution adapters.
"""

from app.strategies.context import (
    PortfolioContextView,
    StrategyContext,
    StrategyPositionView,
)
from app.strategies.decision import DecisionAction, StrategyDecision, no_action
from app.strategies.errors import (
    StrategyDecisionError,
    StrategyError,
    StrategyParameterError,
    StrategyRegistrationError,
)
from app.strategies.proposal_adapter import StrategyProposalAdapter
from app.strategies.protocol import Strategy, assert_strategy_metadata
from app.strategies.registry import StrategyRegistry
from app.strategies.reference import SMACrossoverStrategy

__all__ = [
    "DecisionAction",
    "PortfolioContextView",
    "SMACrossoverStrategy",
    "Strategy",
    "StrategyContext",
    "StrategyDecision",
    "StrategyDecisionError",
    "StrategyError",
    "StrategyParameterError",
    "StrategyPositionView",
    "StrategyProposalAdapter",
    "StrategyRegistrationError",
    "StrategyRegistry",
    "assert_strategy_metadata",
    "no_action",
]
