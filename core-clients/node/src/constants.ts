/**
 * Stable bundle and policy identifiers for ramen-ai integrations.
 *
 * Bundle membership is resolved by the ramen-ai server: pass `bundleIds` to
 * `RamenClient.evaluateCompliance` and read `policyIds` on the verdict for the
 * authoritative list. The member lists below are a reference snapshot so
 * integrations can document and assert expected coverage; they do not change
 * what the server evaluates.
 */

export const SHIELD_CORE_IT_BUNDLE_ID = "ramen__shield_core_it";
export const FINTECH_BANKING_INVARIANCE_BUNDLE_ID = "ramen__fintech_banking_invariance";
export const INDUSTRIAL_IOT_ACTUATION_INVARIANCE_BUNDLE_ID = "ramen__industrial_iot_actuation_invariance";

/** Credit adverse action (ECOA Regulation B / CFPB Circular 2023-03). */
export const CREDIT_ADVERSE_ACTION_POLICY_ID = "796b7a87-d1f5-4ecc-91f2-a506a9b0d91e";
/** Commercial wire and payment execution invariance (UCC Article 4A dual control). */
export const WIRE_DUAL_CONTROL_POLICY_ID = "b4c18ba1-26b7-4b7f-b44b-65e8de790572";
/** Robotics Physical Safety & Biomechanical Invariance (ISO 10218 / ISO/TS 15066). */
export const ROBOTICS_PHYSICAL_SAFETY_POLICY_ID = "1fc71052-eb7e-43fe-9bfa-7ee06afe5b95";

/**
 * Policies the server resolved for {@link INDUSTRIAL_IOT_ACTUATION_INVARIANCE_BUNDLE_ID}
 * on 2026-10-03, including {@link ROBOTICS_PHYSICAL_SAFETY_POLICY_ID}.
 */
export const INDUSTRIAL_IOT_ACTUATION_INVARIANCE_POLICY_IDS: readonly string[] = Object.freeze([
  "6f2fd94c-d2f0-4c91-b5bc-267b2dd067d1",
  "ca426a09-9484-487f-8e98-346218bfcefa",
  "5ae51a4f-46b8-4015-bee7-2c6cc9499561",
  ROBOTICS_PHYSICAL_SAFETY_POLICY_ID,
]);

export const FORGE_DEFAULT_BASE_URL = "https://forge.ramenai.dev";
