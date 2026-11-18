"""Stable bundle slugs for ramen-ai integrations.

Bundle membership is resolved by the ramen-ai server: pass ``bundle_ids`` to
``RamenClient.evaluate_compliance`` and read ``policy_ids`` on the response for
the authoritative list. These constants only name the production bundles.
"""
from __future__ import annotations

SHIELD_CORE_IT_BUNDLE_ID = "ramen__shield_core_it"
EU_AI_ACT_BASELINE_BUNDLE_ID = "ramen__eu_ai_act_baseline"
FINTECH_BANKING_INVARIANCE_BUNDLE_ID = "ramen__fintech_banking_invariance"
INDUSTRIAL_IOT_ACTUATION_INVARIANCE_BUNDLE_ID = "ramen__industrial_iot_actuation_invariance"
# Corporate spend authorization: platform limits, ERP clearance, dual control.
FINANCIAL_AUTHORIZATION_INVARIANCE_BUNDLE_ID = "ramen__financial_authorization_invariance"
# Contractual eligibility and exclusion: coverage dates, exclusions, verified evidence.
CONTRACTUAL_ELIGIBILITY_INVARIANCE_BUNDLE_ID = "ramen__contractual_eligibility_invariance"
# Compliance provenance: verified evidence tokens before regulated records move.
COMPLIANCE_PROVENANCE_INVARIANCE_BUNDLE_ID = "ramen__compliance_provenance_invariance"

PRODUCTION_BUNDLE_IDS: tuple[str, ...] = (
    SHIELD_CORE_IT_BUNDLE_ID,
    EU_AI_ACT_BASELINE_BUNDLE_ID,
    FINTECH_BANKING_INVARIANCE_BUNDLE_ID,
    INDUSTRIAL_IOT_ACTUATION_INVARIANCE_BUNDLE_ID,
    FINANCIAL_AUTHORIZATION_INVARIANCE_BUNDLE_ID,
    CONTRACTUAL_ELIGIBILITY_INVARIANCE_BUNDLE_ID,
    COMPLIANCE_PROVENANCE_INVARIANCE_BUNDLE_ID,
)
