"""Paper pilot onboarding & blocker remediation — fail closed, no auto-approval.

Never enables PAPER_SESSION_EXECUTE_ENABLED.
Never submits broker orders.
Never auto-approves strategy qualification.
"""

from app.onboarding.account import (
    PaperAccountRegistrationResult,
    verify_and_register_alpaca_paper_account,
)
from app.onboarding.errors import OnboardingBlockedError, OnboardingError
from app.onboarding.owner import (
    OWNER_ALLOWLIST_SETUP_PROCEDURE,
    OwnerAllowlistStatus,
    owner_allowlist_status,
    require_authenticated_owner,
)
from app.onboarding.approval_checkpoint import (
    ApprovalCheckpoint,
    prepare_approval_checkpoint,
)
from app.onboarding.dry_run_readiness import (
    DryRunReadinessReport,
    assess_dry_run_readiness,
)
from app.onboarding.market_data_check import (
    MarketDataAccessResult,
    verify_alpaca_market_data_access,
)
from app.onboarding.owner_setup import (
    OWNER_SETUP_OPERATOR_STEPS,
    OwnerSetupResult,
    configure_owner_from_access_token,
    configure_owner_from_password,
)
from app.onboarding.qualification_evidence import (
    DEFAULT_PILOT_COSTS,
    DEFAULT_PILOT_PARAMETERS,
    QualificationEvidenceBundle,
    prepare_sma_crossover_qualification,
    persist_qualification_evidence,
    run_sma_crossover_walk_forward,
)
from app.onboarding.qualification_report import (
    generate_qualification_report,
)
from app.onboarding.supabase_owner import (
    VerifiedOwnerIdentity,
    sign_in_supabase_password,
    verify_supabase_access_token,
)
from app.onboarding.workflow import (
    OnboardingStepResult,
    OnboardingWorkflowReport,
    PaperPilotOnboardingWorkflow,
)

__all__ = [
    "ApprovalCheckpoint",
    "DEFAULT_PILOT_COSTS",
    "DEFAULT_PILOT_PARAMETERS",
    "DryRunReadinessReport",
    "OWNER_ALLOWLIST_SETUP_PROCEDURE",
    "OWNER_SETUP_OPERATOR_STEPS",
    "MarketDataAccessResult",
    "OnboardingBlockedError",
    "OnboardingError",
    "OnboardingStepResult",
    "OnboardingWorkflowReport",
    "OwnerAllowlistStatus",
    "OwnerSetupResult",
    "PaperAccountRegistrationResult",
    "PaperPilotOnboardingWorkflow",
    "QualificationEvidenceBundle",
    "VerifiedOwnerIdentity",
    "assess_dry_run_readiness",
    "configure_owner_from_access_token",
    "configure_owner_from_password",
    "generate_qualification_report",
    "owner_allowlist_status",
    "persist_qualification_evidence",
    "prepare_approval_checkpoint",
    "prepare_sma_crossover_qualification",
    "require_authenticated_owner",
    "run_sma_crossover_walk_forward",
    "sign_in_supabase_password",
    "verify_alpaca_market_data_access",
    "verify_and_register_alpaca_paper_account",
    "verify_supabase_access_token",
]
