/**
 * @ramen-ai/agt-middleware
 *
 * ramen-ai L2 Semantic Firewall middleware for the Microsoft Agent Governance
 * Toolkit (TypeScript SDK). Public surface:
 *
 *   - RamenClient            — HTTP client for POST /api/v1/paas/evaluate
 *   - verifyReceipt          — V5 Ed25519 receipt verification (Web Crypto)
 *   - RamenFirewallBackend   — AGT ExternalPolicyBackend implementation
 *   - GovernanceDenied       — error thrown by governAction() on a block
 *   - ReceiptLedger          — binds receipts to AGT audit-chain hashes
 */

export { RamenClient } from "./client.js";
export type { RamenClientOptions, EvaluateOptions } from "./client.js";

export { verifyReceipt, sha256Hex, AUDIT_PUBLIC_KEYS } from "./verifier.js";

export {
  RamenFirewallBackend,
  GovernanceDenied,
  ReceiptLedger,
  extractInputText,
} from "./firewall.js";
export type { RamenFirewallOptions, LedgerRecord } from "./firewall.js";

export type {
  RamenReceipt,
  Violation,
  PolicyResult,
  EvaluationResponse,
  VerificationResult,
  ComplianceVerdict,
} from "./types.js";
