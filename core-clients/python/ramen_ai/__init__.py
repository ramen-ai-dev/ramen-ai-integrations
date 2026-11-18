"""ramen-ai-core — Python client and Ed25519 V5 verifier for the ramen-ai cloud API."""

from .client import RamenClient
from .constants import (
    COMPLIANCE_PROVENANCE_INVARIANCE_BUNDLE_ID,
    CONTRACTUAL_ELIGIBILITY_INVARIANCE_BUNDLE_ID,
    EU_AI_ACT_BASELINE_BUNDLE_ID,
    FINANCIAL_AUTHORIZATION_INVARIANCE_BUNDLE_ID,
    FINTECH_BANKING_INVARIANCE_BUNDLE_ID,
    INDUSTRIAL_IOT_ACTUATION_INVARIANCE_BUNDLE_ID,
    PRODUCTION_BUNDLE_IDS,
    SHIELD_CORE_IT_BUNDLE_ID,
)
from .governed_errors import GovernanceDeniedException, GovernedGenerationException
from .governed_types import (
    GovernedAccounting,
    GovernedAttemptMetadata,
    GovernedBlockedData,
    GovernedCompleteData,
    GovernedCompleteEnvelope,
    GovernedCompleteEvent,
    GovernedEvaluationSummary,
    GovernedGenerationOptions,
    GovernedHeartbeatData,
    GovernedHeartbeatEvent,
    GovernedProviderName,
    GovernedStatusData,
    GovernedStatusEvent,
    GovernedStatusStage,
    GovernedStreamEvent,
    GovernedTokenUsage,
)
from .types import AttestationPayload, RamenReceipt
from .verifier import verify_receipt

__all__ = [
    "AttestationPayload",
    "COMPLIANCE_PROVENANCE_INVARIANCE_BUNDLE_ID",
    "CONTRACTUAL_ELIGIBILITY_INVARIANCE_BUNDLE_ID",
    "EU_AI_ACT_BASELINE_BUNDLE_ID",
    "FINANCIAL_AUTHORIZATION_INVARIANCE_BUNDLE_ID",
    "FINTECH_BANKING_INVARIANCE_BUNDLE_ID",
    "INDUSTRIAL_IOT_ACTUATION_INVARIANCE_BUNDLE_ID",
    "PRODUCTION_BUNDLE_IDS",
    "SHIELD_CORE_IT_BUNDLE_ID",
    "GovernanceDeniedException",
    "GovernedAccounting",
    "GovernedAttemptMetadata",
    "GovernedBlockedData",
    "GovernedCompleteData",
    "GovernedCompleteEnvelope",
    "GovernedCompleteEvent",
    "GovernedEvaluationSummary",
    "GovernedGenerationException",
    "GovernedGenerationOptions",
    "GovernedHeartbeatData",
    "GovernedHeartbeatEvent",
    "GovernedProviderName",
    "GovernedStatusData",
    "GovernedStatusEvent",
    "GovernedStatusStage",
    "GovernedStreamEvent",
    "GovernedTokenUsage",
    "RamenClient",
    "RamenReceipt",
    "verify_receipt",
]
__version__ = "0.3.3"
