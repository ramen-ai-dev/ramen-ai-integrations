/**
 * Shared types for the ramen-ai AGT middleware.
 *
 * These mirror the V5 Evaluation API contract
 * (`POST /api/v1/paas/evaluate`). Field order and names match the backend
 * exactly so request/response payloads round-trip without translation.
 */

/** A V5 self-describing cryptographic receipt as returned by the API. */
export interface RamenReceipt {
  id: string;
  schema_version: string; // "5.0"
  kid: string; // signing key id, e.g. "ramen_pk_v1"
  signature: string; // base64url Ed25519 signature
  canonical_payload: string; // the EXACT signed string
  statutory_anchors?: string[];
}

/** A single rule violation from the evaluator. */
export interface Violation {
  rule_id: string;
  rule_name: string;
  rule_content: string;
  enforcement_level: "strict" | "suggested" | "informational";
  reasoning?: string;
  recovery_instruction?: string;
}

/** Per-policy breakdown. */
export interface PolicyResult {
  policy_id: string;
  policy_name: string;
  status: "fulfilled" | "rejected";
  allowed?: boolean;
  violations: Violation[];
  rules_checked: number;
  error?: string;
  instruction?: string;
  statutory_anchors?: string[];
}

/** The `data` payload of a successful evaluate response. */
export interface EvaluationResponse {
  allowed: boolean;
  policy_ids: string[];
  policies_evaluated: number;
  policies_passed: number;
  policies_failed: number;
  policies_errored: number;
  total_violations: Violation[];
  results: PolicyResult[];
  execution_time_ms: number;
  executed_at: string;
  statutory_anchors?: string[];
  receipt?: RamenReceipt;
  receipt_alert?: string;
}

/** Result of locally verifying a receipt. */
export interface VerificationResult {
  valid: boolean;
  reason?: string;
}

/** Normalized verdict surfaced to callers and the governance backend. */
export interface ComplianceVerdict {
  allowed: boolean;
  steering: string | null;
  policyIds: string[];
  statutoryAnchors: string[];
  receipt?: RamenReceipt;
  receiptVerified: boolean;
  receiptReason?: string;
  receiptAlert?: string;
  data: EvaluationResponse;
}
