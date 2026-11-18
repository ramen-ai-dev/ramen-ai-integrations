import assert from "node:assert/strict";
import test from "node:test";

import {
  COMPLIANCE_PROVENANCE_INVARIANCE_BUNDLE_ID,
  CONTRACTUAL_ELIGIBILITY_INVARIANCE_BUNDLE_ID,
  EU_AI_ACT_BASELINE_BUNDLE_ID,
  FINANCIAL_AUTHORIZATION_INVARIANCE_BUNDLE_ID,
  FINTECH_BANKING_INVARIANCE_BUNDLE_ID,
  INDUSTRIAL_IOT_ACTUATION_INVARIANCE_BUNDLE_ID,
  PRODUCTION_BUNDLE_IDS,
  SHIELD_CORE_IT_BUNDLE_ID,
} from "../dist/index.js";

const EXPECTED = [
  "ramen__shield_core_it",
  "ramen__eu_ai_act_baseline",
  "ramen__fintech_banking_invariance",
  "ramen__industrial_iot_actuation_invariance",
  "ramen__financial_authorization_invariance",
  "ramen__contractual_eligibility_invariance",
  "ramen__compliance_provenance_invariance",
];

test("production bundle ids match the production slugs", () => {
  assert.deepEqual([...PRODUCTION_BUNDLE_IDS], EXPECTED);
  assert.equal(new Set(PRODUCTION_BUNDLE_IDS).size, EXPECTED.length);
});

test("each constant carries its production slug", () => {
  assert.equal(SHIELD_CORE_IT_BUNDLE_ID, "ramen__shield_core_it");
  assert.equal(EU_AI_ACT_BASELINE_BUNDLE_ID, "ramen__eu_ai_act_baseline");
  assert.equal(FINTECH_BANKING_INVARIANCE_BUNDLE_ID, "ramen__fintech_banking_invariance");
  assert.equal(INDUSTRIAL_IOT_ACTUATION_INVARIANCE_BUNDLE_ID, "ramen__industrial_iot_actuation_invariance");
  assert.equal(FINANCIAL_AUTHORIZATION_INVARIANCE_BUNDLE_ID, "ramen__financial_authorization_invariance");
  assert.equal(CONTRACTUAL_ELIGIBILITY_INVARIANCE_BUNDLE_ID, "ramen__contractual_eligibility_invariance");
  assert.equal(COMPLIANCE_PROVENANCE_INVARIANCE_BUNDLE_ID, "ramen__compliance_provenance_invariance");
});

test("the production bundle list is frozen", () => {
  assert.throws(() => {
    "use strict";
    PRODUCTION_BUNDLE_IDS.push("ramen__other");
  }, TypeError);
});
