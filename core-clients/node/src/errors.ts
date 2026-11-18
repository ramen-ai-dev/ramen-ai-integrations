/**
 * Typed errors for the evaluation, ledger, bundle and Memory Mesh clients.
 *
 * Governed generation keeps its own exception types
 * (`GovernedGenerationException`, `GovernanceDeniedException`).
 */
import type { ComplianceVerdict } from "./types.js";

/**
 * An API, transport, or response-shape failure.
 *
 * `status` is the HTTP status, or `null` when no response was received.
 * `code` is the server's error code (for example `AUTHORIZATION_REQUIRED`),
 * or one of `TRANSPORT_TIMEOUT`, `TRANSPORT_ERROR`, `INVALID_RESPONSE`, or
 * `HTTP_<status>` when the body carried no code.
 */
export class RamenApiError extends Error {
  readonly status: number | null;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number | null, code: string, message: string, details?: unknown, cause?: unknown) {
    super(message, cause === undefined ? undefined : { cause });
    this.name = "RamenApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

/**
 * Thrown when `requireVerifiedReceipt` is enabled and the evaluation response
 * carries no receipt, or a receipt that does not verify against the signed
 * verdict. Treat it as a denial.
 */
export class ReceiptVerificationError extends Error {
  readonly reason: string;
  /** The unverified verdict. Never act on `verdict.allowed`. */
  readonly verdict: ComplianceVerdict;

  constructor(reason: string, verdict: ComplianceVerdict) {
    super(`Receipt verification failed: ${reason}`);
    this.name = "ReceiptVerificationError";
    this.reason = reason;
    this.verdict = verdict;
  }
}
