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

# Credit adverse action (ECOA Regulation B / CFPB Circular 2023-03).
CREDIT_ADVERSE_ACTION_POLICY_ID = "796b7a87-d1f5-4ecc-91f2-a506a9b0d91e"
# Commercial wire and payment execution invariance (UCC Article 4A dual control).
WIRE_DUAL_CONTROL_POLICY_ID = "b4c18ba1-26b7-4b7f-b44b-65e8de790572"
# Robotics Physical Safety & Biomechanical Invariance (ISO 10218 / ISO/TS 15066).
ROBOTICS_PHYSICAL_SAFETY_POLICY_ID = "1fc71052-eb7e-43fe-9bfa-7ee06afe5b95"
# Policies the server resolved for INDUSTRIAL_IOT_ACTUATION_INVARIANCE_BUNDLE_ID on
# 2026-10-03. A reference snapshot: the server resolves membership on every call.
INDUSTRIAL_IOT_ACTUATION_INVARIANCE_POLICY_IDS: tuple[str, ...] = (
    "6f2fd94c-d2f0-4c91-b5bc-267b2dd067d1",
    "ca426a09-9484-487f-8e98-346218bfcefa",
    "5ae51a4f-46b8-4015-bee7-2c6cc9499561",
    ROBOTICS_PHYSICAL_SAFETY_POLICY_ID,
)

FORGE_DEFAULT_BASE_URL = "https://forge.ramenai.dev"
