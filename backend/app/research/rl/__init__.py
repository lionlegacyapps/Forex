"""FinRL-X inspired offline RL research (isolated from broker execution).

Official FinRL-X repository: https://github.com/AI4Finance-Foundation/FinRL-Trading
Pinned commit: see finrlx_intake.FINRLX_PINNED_COMMIT

Full FinRL-X / alpaca-py / torch / stable-baselines3 are NOT installed.
Training workers are NOT deployed. Research only — no auto-trading.
"""

from app.research.rl.environment import (
    Action,
    EpisodeResult,
    OfflineTradingEnv,
    OfflineTradingEnvConfig,
)
from app.research.rl.evaluation import evaluate_policy
from app.research.rl.finrlx_intake import (
    FINRLX_PINNED_COMMIT,
    FINRLX_REPOSITORY_URL,
    build_finrlx_intake_result,
    finrlx_approved_adaptation_manifest,
)
from app.research.rl.policies import DeterministicMomentumBaselinePolicy, Policy
from app.research.rl.strategy_adapter import FinRLXBaselineSignalAdapter

__all__ = [
    "Action",
    "DeterministicMomentumBaselinePolicy",
    "EpisodeResult",
    "FINRLX_PINNED_COMMIT",
    "FINRLX_REPOSITORY_URL",
    "FinRLXBaselineSignalAdapter",
    "OfflineTradingEnv",
    "OfflineTradingEnvConfig",
    "Policy",
    "build_finrlx_intake_result",
    "evaluate_policy",
    "finrlx_approved_adaptation_manifest",
]
