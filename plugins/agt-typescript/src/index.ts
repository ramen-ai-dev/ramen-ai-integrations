/**
 * @ramen-ai/agt-middleware
 *
 * ramen-ai L2 Semantic Firewall middleware for the Microsoft Agent Governance
 * Toolkit (TypeScript SDK). Public surface:
 *
 *   - RamenClient            — re-exported from @ramen-ai/node-core
 *   - verifyReceipt          — re-exported from @ramen-ai/node-core (V5 Ed25519)
 *   - RamenFirewallBackend   — AGT ExternalPolicyBackend implementation
 *   - GovernanceDenied       — error thrown by governAction() on a block
 *   - ReceiptLedger          — binds receipts to AGT audit-chain hashes
 */
export {
  RamenClient,
  verifyReceipt,
  sha256Hex,
  AUDIT_PUBLIC_KEYS,
} from "@ramen-ai/node-core";
export type {
  RamenClientOptions,
  EvaluateOptions,
  RamenReceipt,
  Violation,
  PolicyResult,
  EvaluationResponse,
  VerificationResult,
  ComplianceVerdict,
} from "@ramen-ai/node-core";
export {
  RamenFirewallBackend,
  GovernanceDenied,
  ReceiptLedger,
  extractInputText,
} from "./firewall.js";
export type { RamenFirewallOptions, LedgerRecord } from "./firewall.js";
