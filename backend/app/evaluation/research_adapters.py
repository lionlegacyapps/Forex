"""Adapters that attach research provenance without forcing identical metrics."""

from __future__ import annotations

from typing import Any

from app.evaluation.models import ResearchProvenance
from app.research.models import ResearchOutput
from app.research.qlib_intake import QLIB_PINNED_COMMIT, QLIB_REPOSITORY_URL
from app.research.rl.finrlx_intake import FINRLX_PINNED_COMMIT, FINRLX_REPOSITORY_URL


def provenance_from_research_output(output: ResearchOutput) -> ResearchProvenance:
    trained = bool(output.metadata.get("is_trained_ai_policy", False))
    notes = list(output.warnings)
    if "finrl" in output.research_model_id.lower() or "finrl" in (
        output.source_repository or ""
    ).lower():
        notes.append(
            "FinRL-X baseline/offline policy evaluation is not a trained AI trading agent."
        )
        trained = False
    return ResearchProvenance(
        research_model_id=output.research_model_id,
        source_repository=output.source_repository,
        pinned_commit=output.pinned_commit,
        model_version=output.model_version,
        data_version=output.data_version,
        is_trained_ai_policy=trained,
        notes=notes,
        metadata=dict(output.metadata),
    )


def qlib_momentum_provenance(
    *,
    model_version: str = "1.0.0",
    data_version: str = "v1-fixture",
    metadata: dict[str, Any] | None = None,
) -> ResearchProvenance:
    return ResearchProvenance(
        research_model_id="qlib_inspired_momentum_v1",
        source_repository=QLIB_REPOSITORY_URL,
        pinned_commit=QLIB_PINNED_COMMIT,
        model_version=model_version,
        data_version=data_version,
        is_trained_ai_policy=False,
        notes=[
            "Qlib-inspired momentum research adapter; not microsoft/qlib runtime.",
        ],
        metadata=metadata or {},
    )


def finrlx_baseline_provenance(
    *,
    model_version: str = "1.0.0",
    data_version: str = "v1-fixture",
    policy_id: str = "buy_hold_baseline",
    metadata: dict[str, Any] | None = None,
) -> ResearchProvenance:
    meta = {"policy_id": policy_id, **(metadata or {})}
    return ResearchProvenance(
        research_model_id="finrlx_offline_baseline_v1",
        source_repository=FINRLX_REPOSITORY_URL,
        pinned_commit=FINRLX_PINNED_COMMIT,
        model_version=model_version,
        data_version=data_version,
        is_trained_ai_policy=False,
        notes=[
            "FinRL-X intake is offline research only.",
            "Baseline deterministic policy — NOT a trained AI policy.",
        ],
        metadata=meta,
    )


def reference_strategy_provenance(
    *,
    strategy_id: str,
    strategy_version: str,
) -> ResearchProvenance:
    return ResearchProvenance(
        research_model_id=f"reference:{strategy_id}",
        source_repository="local://app.strategies.reference",
        pinned_commit=None,
        model_version=strategy_version,
        data_version=None,
        is_trained_ai_policy=False,
        notes=["Internal reference strategy; not an external research model."],
        metadata={"strategy_id": strategy_id},
    )
