/**
 * @ramen-ai/node-core
 *
 * Agnostic Node.js core client for the ramen-ai PaaS evaluation API. Reusable
 * SDK shared across ramen-ai integrations (AGT middleware, GitHub Action, etc).
 *
 * Public surface:
 *   - RamenClient     — HTTP client for POST /api/v1/paas/evaluate
 *   - verifyReceipt   — V5 Ed25519 receipt verification (Web Crypto)
 *   - sha256Hex       — SHA-256 hex helper used by the verifier
 */

export { RamenClient } from "./client.js";
export type { RamenClientOptions, EvaluateOptions } from "./client.js";

export { verifyReceipt, sha256Hex, AUDIT_PUBLIC_KEYS } from "./verifier.js";

export type {
  RamenReceipt,
  Violation,
  PolicyResult,
  EvaluationResponse,
  VerificationResult,
  ComplianceVerdict,
} from "./types.js";
