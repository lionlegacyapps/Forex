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
from app.onboarding.market_data_check import (
    MarketDataAccessResult,
    verify_alpaca_market_data_access,
)
from app.onboarding.qualification_evidence import (
    DEFAULT_PILOT_COSTS,
    DEFAULT_PILOT_PARAMETERS,
    QualificationEvidenceBundle,
    prepare_sma_crossover_qualification,
    persist_qualification_evidence,
    run_sma_crossover_walk_forward,
)
from app.onboarding.workflow import (
    OnboardingStepResult,
    OnboardingWorkflowReport,
    PaperPilotOnboardingWorkflow,
)

__all__ = [
    "DEFAULT_PILOT_COSTS",
    "DEFAULT_PILOT_PARAMETERS",
    "OWNER_ALLOWLIST_SETUP_PROCEDURE",
    "MarketDataAccessResult",
    "OnboardingBlockedError",
    "OnboardingError",
    "OnboardingStepResult",
    "OnboardingWorkflowReport",
    "OwnerAllowlistStatus",
    "PaperAccountRegistrationResult",
    "PaperPilotOnboardingWorkflow",
    "QualificationEvidenceBundle",
    "owner_allowlist_status",
    "persist_qualification_evidence",
    "prepare_sma_crossover_qualification",
    "require_authenticated_owner",
    "run_sma_crossover_walk_forward",
    "verify_alpaca_market_data_access",
    "verify_and_register_alpaca_paper_account",
]
