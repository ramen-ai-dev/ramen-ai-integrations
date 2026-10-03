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
 *   - RemoteForgeMemoryStore — ramen forge (community memory) HTTP client
 *   - RamenProvenanceEnvelope — shared `_ramen_provenance` envelope type
 */

export { RamenClient } from "./client.js";
export type {
  AttestationPayload,
  RamenClientOptions,
  EvaluateOptions,
} from "./client.js";

export {
  GovernanceDeniedException,
  GovernedGenerationException,
} from "./governed-errors.js";
export type {
  GenerateGovernedOptions,
  GovernedAccounting,
  GovernedAttemptMetadata,
  GovernedBlockedData,
  GovernedCompleteData,
  GovernedCompleteEvent,
  GovernedEvaluationSummary,
  GovernedGenerationOptions,
  GovernedHeartbeatEvent,
  GovernedProviderName,
  GovernedStatusEvent,
  GovernedStatusStage,
  GovernedStreamEvent,
  GovernedTokenUsage,
} from "./governed-types.js";

export {
  verifyReceipt,
  verifyAllowReceiptSignature,
  sha256Hex,
  AUDIT_PUBLIC_KEYS,
} from "./verifier.js";
export type { AllowReceiptCheck } from "./verifier.js";
export {
  RemoteForgeMemoryStore,
  ForgeWriteError,
  buildProvenance,
} from "./memory/RemoteForgeMemoryStore.js";
export type {
  CorrectionExemplar,
  CorrectionExemplarPayload,
  MemoryLogger,
  RecordCorrectionResult,
  RemoteForgeMemoryStoreOptions,
  RetrieveExemplarsOptions,
} from "./memory/RemoteForgeMemoryStore.js";
export { PROVENANCE_VERSION } from "./types/provenance.js";
export type { RamenProvenanceEnvelope } from "./types/provenance.js";
export {
  SHIELD_CORE_IT_BUNDLE_ID,
  FINTECH_BANKING_INVARIANCE_BUNDLE_ID,
  INDUSTRIAL_IOT_ACTUATION_INVARIANCE_BUNDLE_ID,
  INDUSTRIAL_IOT_ACTUATION_INVARIANCE_POLICY_IDS,
  CREDIT_ADVERSE_ACTION_POLICY_ID,
  WIRE_DUAL_CONTROL_POLICY_ID,
  ROBOTICS_PHYSICAL_SAFETY_POLICY_ID,
  FORGE_DEFAULT_BASE_URL,
} from "./constants.js";

export type {
  RamenReceipt,
  Violation,
  PolicyResult,
  EvaluationResponse,
  VerificationResult,
  ComplianceVerdict,
} from "./types.js";
