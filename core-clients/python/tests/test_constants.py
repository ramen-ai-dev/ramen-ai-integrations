"""Bundle slug constants stay in sync with the production bundle names."""
from __future__ import annotations

import ramen_ai
from ramen_ai import constants

EXPECTED = (
    "ramen__shield_core_it",
    "ramen__eu_ai_act_baseline",
    "ramen__fintech_banking_invariance",
    "ramen__industrial_iot_actuation_invariance",
    "ramen__financial_authorization_invariance",
    "ramen__contractual_eligibility_invariance",
    "ramen__compliance_provenance_invariance",
)


def test_production_bundle_ids_match_the_production_slugs():
    assert constants.PRODUCTION_BUNDLE_IDS == EXPECTED
    assert len(set(constants.PRODUCTION_BUNDLE_IDS)) == len(EXPECTED)


def test_new_enterprise_bundles_are_exported_from_the_package():
    assert ramen_ai.FINANCIAL_AUTHORIZATION_INVARIANCE_BUNDLE_ID == "ramen__financial_authorization_invariance"
    assert ramen_ai.CONTRACTUAL_ELIGIBILITY_INVARIANCE_BUNDLE_ID == "ramen__contractual_eligibility_invariance"
    assert ramen_ai.COMPLIANCE_PROVENANCE_INVARIANCE_BUNDLE_ID == "ramen__compliance_provenance_invariance"
    assert ramen_ai.PRODUCTION_BUNDLE_IDS == EXPECTED
