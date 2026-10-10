"""Quantitative research package (isolated from broker execution).

Microsoft Qlib is reviewed as a research reference. Full ``pyqlib`` is NOT
installed into the trading runtime. This package provides a narrowly scoped,
deterministic research demonstration inspired by Qlib factor workflows,
wired through our StrategyDecision → Trade Proposal path.

EXTERNAL GITHUB CODE IS NEVER TRUSTED BY DEFAULT.
Research outputs never automatically trigger trading.
"""

from app.research.data import ResearchBarFrame, bars_to_research_frame
from app.research.factors import compute_momentum_factor, compute_return_factor
from app.research.models import ResearchOutput, ResearchPrediction
from app.research.pipeline import QlibInspiredResearchPipeline
from app.research.qlib_intake import (
    QLIB_PINNED_COMMIT,
    QLIB_REPOSITORY_URL,
    build_qlib_intake_result,
    qlib_approved_adaptation_manifest,
)
from app.research.strategy_adapter import QlibFactorSignalAdapter

__all__ = [
    "QLIB_PINNED_COMMIT",
    "QLIB_REPOSITORY_URL",
    "QlibFactorSignalAdapter",
    "QlibInspiredResearchPipeline",
    "ResearchBarFrame",
    "ResearchOutput",
    "ResearchPrediction",
    "bars_to_research_frame",
    "build_qlib_intake_result",
    "compute_momentum_factor",
    "compute_return_factor",
    "qlib_approved_adaptation_manifest",
]
