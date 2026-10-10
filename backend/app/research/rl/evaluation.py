"""Offline policy evaluation → normalized ResearchOutput.

Does not train DRL agents. Does not place broker orders.
"""

from __future__ import annotations

from decimal import Decimal

from app.market_data.models import Bar
from app.research.models import ResearchOutput, ResearchPrediction
from app.research.rl.environment import (
    Action,
    EpisodeResult,
    OfflineTradingEnv,
    OfflineTradingEnvConfig,
)
from app.research.rl.finrlx_intake import FINRLX_PINNED_COMMIT, FINRLX_REPOSITORY_URL
from app.research.rl.policies import Policy


def run_episode(
    env: OfflineTradingEnv,
    policy: Policy,
) -> EpisodeResult:
    obs = env.reset()
    rewards: list[Decimal] = []
    actions: list[Action] = []
    timestamps = []
    equities = []
    infos = []
    while True:
        action = policy.act(obs)
        result = env.step(action)
        actions.append(action)
        rewards.append(result.reward)
        timestamps.append(obs.timestamp)
        equities.append(obs.equity)
        infos.append(result.info)
        obs = result.observation
        if result.terminated or result.truncated:
            timestamps.append(obs.timestamp)
            equities.append(obs.equity)
            break
    return EpisodeResult(
        rewards=rewards,
        actions=actions,
        timestamps=timestamps,
        equities=equities,
        total_reward=sum(rewards, Decimal("0")),
        ending_equity=equities[-1] if equities else Decimal("0"),
        ending_cash=obs.cash,
        ending_position=obs.position_qty,
        total_costs=Decimal(str(infos[-1].get("costs_total", "0"))) if infos else Decimal("0"),
        infos=infos,
    )


def evaluate_policy(
    bars: list[Bar],
    policy: Policy,
    *,
    config: OfflineTradingEnvConfig | None = None,
    model_id: str = "finrlx_inspired_baseline_v1",
    model_version: str = "1.0.0",
    data_version: str = "v1-fixture",
) -> tuple[ResearchOutput, EpisodeResult]:
    env = OfflineTradingEnv(bars, config=config)
    episode = run_episode(env, policy)

    predictions: list[ResearchPrediction] = []
    # Map each decision timestamp to a signed score from the action taken
    for ts, action, reward in zip(
        episode.timestamps[: len(episode.actions)],
        episode.actions,
        episode.rewards,
        strict=True,
    ):
        if action == Action.BUY:
            score = Decimal("1")
        elif action == Action.SELL:
            score = Decimal("-1")
        else:
            score = Decimal("0")
        predictions.append(
            ResearchPrediction(
                symbol=env.symbol,
                prediction_timestamp=ts,
                prediction_horizon="1bar",
                score=score,
                factor_values={
                    "action": Decimal(action.value),
                    "step_reward": reward,
                },
            )
        )

    output = ResearchOutput(
        research_model_id=model_id,
        source_repository=FINRLX_REPOSITORY_URL,
        pinned_commit=FINRLX_PINNED_COMMIT,
        model_version=model_version,
        symbol=env.symbol,
        prediction_horizon="1bar",
        data_version=data_version,
        training_period_start=None,  # no training in V1
        training_period_end=None,
        evaluation_period_start=episode.timestamps[0] if episode.timestamps else None,
        evaluation_period_end=episode.timestamps[-1] if episode.timestamps else None,
        predictions=predictions,
        warnings=[
            "FinRL-X inspired offline evaluation — not the full FinRL-X framework.",
            "Baseline policy is deterministic and NOT a trained RL model.",
            "DRL training deferred; no training workers deployed.",
            "Research outputs do not automatically trigger trading.",
            "IN-SAMPLE / RESEARCH PERFORMANCE DOES NOT PROVE PROFITABILITY.",
            "EXTERNAL GITHUB CODE IS NEVER TRUSTED BY DEFAULT.",
        ],
        metadata={
            "total_reward": str(episode.total_reward),
            "ending_equity": str(episode.ending_equity),
            "total_costs": str(episode.total_costs),
            "full_finrlx_runtime": False,
            "auto_trade": False,
            "aka": "FinRL-X",
        },
    )
    return output, episode
