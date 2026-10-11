"""Owner Setup & Strategy Qualification Review V1 tests."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.onboarding.approval_checkpoint import (
    DEFAULT_QUALIFICATION_ID,
    execute_approval_if_authorized,
    prepare_approval_checkpoint,
)
from app.onboarding.dry_run_readiness import assess_dry_run_readiness
from app.onboarding.errors import OnboardingBlockedError
from app.onboarding.owner_setup import (
    configure_owner_from_access_token,
    write_owner_allowlist_subject,
)
from app.onboarding.qualification_report import render_markdown
from app.onboarding.supabase_owner import (
    OwnerAuthError,
    sign_in_supabase_password,
    verify_supabase_access_token,
)
from app.qualification import resolve_authenticated_owner
from app.qualification.errors import UnauthorizedApprovalError


def _ready(db: Session) -> bool:
    try:
        db.execute(text("SELECT 1 FROM strategy_paper_qualifications LIMIT 1"))
        return True
    except Exception:
        db.rollback()
        return False


def _settings(**kwargs) -> Settings:
    base = dict(
        paper_qualification_owner_subjects="",
        paper_session_execute_enabled=False,
        supabase_url="https://example.supabase.co",
        supabase_anon_key="anon-test-key",
        alpaca_data_feed="iex",
        alpaca_paper_base_url="https://paper-api.alpaca.markets",
    )
    base.update(kwargs)
    return Settings(**base)


class _Transport(httpx.MockTransport):
    pass


def test_supabase_access_token_verification_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/auth/v1/user")
        assert request.headers.get("Authorization") == "Bearer user-access-token"
        return httpx.Response(
            200,
            json={
                "id": "11111111-1111-1111-1111-111111111111",
                "email": "owner@example.com",
                "email_confirmed_at": "2026-01-01T00:00:00Z",
                "app_metadata": {"providers": ["email"]},
            },
        )

    identity = verify_supabase_access_token(
        "user-access-token",
        settings=_settings(),
        transport=httpx.MockTransport(handler),
    )
    assert identity.subject == "owner@example.com"
    assert identity.email_confirmed is True


def test_supabase_rejects_unconfirmed_email() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "11111111-1111-1111-1111-111111111111",
                "email": "owner@example.com",
                "email_confirmed_at": None,
            },
        )

    with pytest.raises(OwnerAuthError) as exc:
        verify_supabase_access_token(
            "tok",
            settings=_settings(),
            transport=httpx.MockTransport(handler),
        )
    assert exc.value.code == "owner_email_unconfirmed"


def test_supabase_password_sign_in_and_allowlist_write(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("PAPER_SESSION_EXECUTE_ENABLED=false\nPAPER_QUALIFICATION_OWNER_SUBJECTS=\n")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(
                200,
                json={
                    "access_token": "session-token",
                    "user": {
                        "id": "11111111-1111-1111-1111-111111111111",
                        "email": "Owner@Example.com",
                        "email_confirmed_at": "2026-01-01T00:00:00Z",
                    },
                },
            )
        return httpx.Response(404)

    identity, token = sign_in_supabase_password(
        "owner@example.com",
        "secret",
        settings=_settings(),
        transport=httpx.MockTransport(handler),
    )
    assert identity.subject == "owner@example.com"
    assert token == "session-token"
    path = write_owner_allowlist_subject(identity.subject, env_path=env)
    text = path.read_text(encoding="utf-8")
    assert "PAPER_QUALIFICATION_OWNER_SUBJECTS=owner@example.com" in text
    owner = resolve_authenticated_owner(
        subject="owner@example.com",
        credential_verified=True,
        settings=_settings(paper_qualification_owner_subjects="owner@example.com"),
    )
    assert owner.subject == "owner@example.com"


def test_configure_owner_from_token_verifies(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("PAPER_QUALIFICATION_OWNER_SUBJECTS=\n")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "11111111-1111-1111-1111-111111111111",
                "email": "owner@example.com",
                "email_confirmed_at": "2026-01-01T00:00:00Z",
            },
        )

    result = configure_owner_from_access_token(
        "tok",
        env_path=env,
        write_env=False,
        settings=_settings(),
        transport=httpx.MockTransport(handler),
    )
    assert result.ok is True
    assert result.verification_passed is True
    assert result.subject == "owner@example.com"
    assert result.allowlist_written is False


def test_empty_allowlist_still_fail_closed() -> None:
    with pytest.raises((UnauthorizedApprovalError, OnboardingBlockedError)):
        resolve_authenticated_owner(
            subject="owner@example.com",
            credential_verified=True,
            settings=_settings(paper_qualification_owner_subjects=""),
        )


def test_qualification_report_render_contains_required_sections() -> None:
    metrics = {
        "qualification_id": str(DEFAULT_QUALIFICATION_ID),
        "strategy_id": "sma_crossover",
        "strategy_version": "1.0.0",
        "parameters": {"fast_period": 3, "slow_period": 5, "quantity": "1"},
        "parameter_hash": "abc",
        "dataset_fingerprint": "def",
        "evidence_fingerprint": "ghi",
        "evaluation_id": "harness",
        "evaluation_date_utc": "2026-10-11T16:39:10.259682Z",
        "qualification_created_at": "2026-10-11T16:39:10+00:00",
        "state": "review_required",
        "recommendation": "eligible_for_review",
        "approval_scope": "paper_only",
        "hard_blockers": [],
        "warning_codes": ["low_profit_factor"],
        "warnings": [{"code": "low_profit_factor", "message": "PF low"}],
        "informational": [],
        "cost_assumptions": {"slippage_bps": "5", "commission_per_share": "0.005"},
        "historical_period": {
            "symbol": "AAPL",
            "timeframe": "1Day",
            "start": "2024-04-24",
            "end": "2026-10-09",
            "bar_count": 618,
        },
        "split": {
            "mode": "rolling",
            "train_bars": 80,
            "validation_bars": 40,
            "oos_bars": 40,
            "step_bars": 40,
            "warmup_bars": 20,
        },
        "oos": {
            "windows": 12,
            "trades": 39,
            "net_pnl": "60.96",
            "net_return_pct": "0.06",
            "compounded_return_pct": "0.06",
            "trade_weighted_win_rate_pct": "51.28",
            "winning_trades": 20,
            "losing_trades": 19,
            "average_win": "5.15",
            "average_loss": "-6.18",
            "transaction_costs_total": "0.39",
            "max_drawdown_worst": "37.26",
            "profit_factor_stored": "0E+7",
            "profit_factor_note": "see windows",
        },
        "oos_windows": [
            {
                "window_index": 0,
                "trade_count": 2,
                "net_pnl": "1",
                "net_return_pct": "0.1",
                "win_rate_pct": "50",
                "profit_factor": "1.2",
                "max_drawdown": "2",
                "average_win": "1",
                "average_loss": "-1",
                "transaction_costs": "0.02",
            }
        ],
        "regime_notes": ["unreliable_regime:ranging"],
        "robustness_findings": ["unreliable_regime_buckets_present"],
        "hashes_match_recompute": {
            "parameter_hash": True,
            "dataset_fingerprint": True,
            "evaluation_id": True,
        },
        "approved": False,
    }
    md = render_markdown(metrics)
    assert "NOT APPROVED" in md
    assert "sma_crossover@1.0.0" in md
    assert "Out-of-sample summary" in md
    assert "Window-by-window" in md
    assert "Hard blockers" in md
    assert "future" in md.lower()


def test_approval_checkpoint_no_override(db_session: Session) -> None:
    if not _ready(db_session):
        pytest.skip("migrations not applied")
    row = db_session.get(
        __import__(
            "app.models.strategy_paper_qualification", fromlist=["StrategyPaperQualification"]
        ).StrategyPaperQualification,
        DEFAULT_QUALIFICATION_ID,
    )
    if row is None:
        pytest.skip("target qualification not present in this database")
    cp = prepare_approval_checkpoint(db_session, qualification_id=DEFAULT_QUALIFICATION_ID)
    assert cp.unsafe_override_offered is False
    assert cp.hard_blocker_count == 0
    assert cp.ready_for_owner_decision is True
    assert cp.parameter_hash
    assert cp.evidence_fingerprint


def test_approval_requires_explicit_phrase(db_session: Session) -> None:
    if not _ready(db_session):
        pytest.skip("migrations not applied")
    from app.qualification.auth import AuthenticatedOwner

    owner = AuthenticatedOwner(subject="owner@example.com")
    with pytest.raises(OnboardingBlockedError) as exc:
        execute_approval_if_authorized(
            db_session,
            qualification_id=DEFAULT_QUALIFICATION_ID,
            owner=owner,
            explicit_authorization_phrase="nope",
        )
    assert exc.value.code == "approval_not_authorized"


@pytest.mark.asyncio
async def test_dry_run_readiness_blocked_without_owner(db_session: Session) -> None:
    if not _ready(db_session):
        pytest.skip("migrations not applied")
    report = await assess_dry_run_readiness(
        db_session,
        settings=_settings(),
        check_live_market_data=False,
    )
    assert report.ready is False
    names = {c.name: c.ok for c in report.checks}
    assert names["owner_allowlist_configured"] is False
    assert names["qualification_approved"] is False
    assert names["execute_flag_disabled"] is True


def test_no_hardcoded_owner_email_in_setup_modules() -> None:
    root = Path("app/onboarding")
    for path in root.glob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert "lionlegacyapps@gmail.com" not in src
        if path.name in {"supabase_owner.py", "owner_setup.py", "owner_setup_cli.py"}:
            assert "PAPER_QUALIFICATION_OWNER_SUBJECTS" in src or "subject" in src


def test_execute_flag_remains_default_false() -> None:
    assert Settings().paper_session_execute_enabled is False
