/**
 * RamenFirewall — Microsoft AGT integration for the ramen-ai L2 Semantic
 * Firewall, built on the TypeScript SDK (`@microsoft/agent-governance-sdk`).
 *
 * Integration surface
 * --------------------
 * The idiomatic AGT hook is {@link ExternalPolicyBackend}: a backend
 * registered on a `PolicyEngine` via `engine.registerBackend(...)` and
 * consulted by `engine.evaluateWithBackends(action, context)`. We implement
 * that interface so the firewall participates in AGT's native policy
 * pipeline. On a block, the agent-facing **steering instruction** is returned
 * in the outcome's `reason` field (AGT surfaces it via `deniedBy` + reason).
 *
 * Evidence binding
 * ----------------
 * AGT's `AuditEntry` (v4) has a fixed shape — `{ agentId, action, decision,
 * hash, previousHash, timestamp }` — with no free-form metadata field. So the
 * full Ed25519 receipt cannot be embedded *inside* an entry. Instead we log
 * the decision to the AGT `AuditLogger` (preserving its tamper-evident
 * hash-chain) and bind the receipt to that entry in a parallel
 * {@link ReceiptLedger} keyed by the entry's `hash`. The receipt already
 * carries its own independent Ed25519 proof.
 */

import type {
  AuditEntry,
  AuditLogger,
  BackendEvaluationOutcome,
  ExternalPolicyBackend,
  LegacyPolicyDecision,
} from "@microsoft/agent-governance-sdk";
import type { RamenClient } from "./client.js";
import type { ComplianceVerdict, RamenReceipt } from "./types.js";

/** Keys checked, in order, when extracting input text from an AGT context. */
const INPUT_KEYS = ["input", "input_text", "content", "message", "prompt"] as const;

/** Error thrown by the governed wrapper when the firewall blocks an action. */
export class GovernanceDenied extends Error {
  readonly steering: string;
  readonly verdict: ComplianceVerdict;
  /** True when the denial was caused by an infrastructure/evaluation failure
   *  (timeout, 5xx, malformed response) rather than an explicit policy block. */
  readonly failedClosed: boolean;

  constructor(steering: string, verdict: ComplianceVerdict, failedClosed = false) {
    super(steering || "Action denied by ramen-ai firewall");
    this.name = "GovernanceDenied";
    this.steering = steering || this.message;
    this.verdict = verdict;
    this.failedClosed = failedClosed;
  }

  /**
   * Build a fail-closed denial for an infrastructure/evaluation error. The
   * synthetic verdict records the failure so audit consumers can distinguish
   * "blocked by policy" from "blocked because we could not evaluate".
   */
  static failClosed(action: string, errorMessage: string): GovernanceDenied {
    const steering =
      "Action denied: the ramen-ai firewall could not be reached or returned an " +
      "error, so the action was blocked (fail-closed). Retry once the firewall is reachable.";
    const verdict: ComplianceVerdict = {
      allowed: false,
      steering,
      policyIds: [],
      statutoryAnchors: [],
      receiptVerified: false,
      receiptReason: `fail-closed on '${action}': ${errorMessage}`,
      data: {
        allowed: false,
        policy_ids: [],
        policies_evaluated: 0,
        policies_passed: 0,
        policies_failed: 0,
        policies_errored: 1,
        total_violations: [],
        results: [],
        execution_time_ms: 0,
        executed_at: new Date().toISOString(),
      },
    };
    return new GovernanceDenied(steering, verdict, true);
  }
}

/** A receipt bound to a specific AGT audit-chain entry. */
export interface LedgerRecord {
  auditHash: string;
  agentId: string;
  action: string;
  decision: LegacyPolicyDecision;
  steering: string | null;
  statutoryAnchors: string[];
  receiptVerified: boolean;
  receipt?: RamenReceipt;
}

/**
 * Parallel, append-only ledger binding each Ed25519 receipt to the AGT audit
 * entry hash that recorded the same decision.
 */
export class ReceiptLedger {
  private readonly records = new Map<string, LedgerRecord>();

  bind(record: LedgerRecord): void {
    this.records.set(record.auditHash, record);
  }

  /** Look up the receipt bound to an AGT audit entry hash. */
  get(auditHash: string): LedgerRecord | undefined {
    return this.records.get(auditHash);
  }

  get size(): number {
    return this.records.size;
  }
}

export interface RamenFirewallOptions {
  /** Bundle ids to evaluate (resolved server-side to policy ids). */
  bundleIds?: string[];
  /** Explicit policy ids to evaluate. */
  policyIds?: string[];
  /** Agent id recorded in audit entries (default "ramen-agent"). */
  agentId?: string;
  /**
   * If true (default), a missing or invalid receipt forces a denial even when
   * the verdict is `allowed` — no proof, no pass. Fail-closed on evidence.
   */
  requireVerifiedReceipt?: boolean;
  /** Optional AGT AuditLogger; when provided, every decision is logged. */
  auditLogger?: AuditLogger;
  /** Optional ledger binding receipts to audit hashes (auto-created if omitted). */
  ledger?: ReceiptLedger;
}

/** Extract the best-effort input text from an AGT action context. */
export function extractInputText(context: Record<string, unknown> | undefined): string {
  if (!context) return "";
  for (const key of INPUT_KEYS) {
    const value = context[key];
    if (typeof value === "string" && value.length > 0) return value;
  }
  return "";
}

/**
 * ramen-ai firewall as an AGT external policy backend.
 *
 * Register it with `policyEngine.registerBackend(new RamenFirewallBackend(...))`
 * and evaluate via `policyEngine.evaluateWithBackends(action, context)`.
 */
export class RamenFirewallBackend implements ExternalPolicyBackend {
  readonly name = "ramen-ai-firewall";

  private readonly client: RamenClient;
  private readonly opts: Required<Pick<RamenFirewallOptions, "agentId" | "requireVerifiedReceipt">> &
    RamenFirewallOptions;
  readonly ledger: ReceiptLedger;

  constructor(client: RamenClient, opts: RamenFirewallOptions = {}) {
    if (!opts.bundleIds?.length && !opts.policyIds?.length) {
      throw new Error("RamenFirewallBackend requires bundleIds or policyIds");
    }
    this.client = client;
    this.ledger = opts.ledger ?? new ReceiptLedger();
    // Spread caller opts FIRST, then apply defaults, so an explicitly-passed
    // `undefined` can never clobber a default value.
    this.opts = {
      ...opts,
      agentId: opts.agentId ?? "ramen-agent",
      requireVerifiedReceipt: opts.requireVerifiedReceipt ?? true,
    };
  }

  /**
   * Evaluate a proposed action. Implements {@link ExternalPolicyBackend}.
   * Fail-closed: any error returns a `deny` outcome.
   */
  async evaluateAction(
    action: string,
    context: Record<string, unknown>,
  ): Promise<BackendEvaluationOutcome> {
    try {
      const verdict = await this.runFirewall(action, context);
      const decision: LegacyPolicyDecision = verdict.allowed ? "allow" : "deny";
      const reason = verdict.allowed
        ? undefined
        : verdict.steering ?? "Blocked by ramen-ai firewall";
      return { backend: this.name, decision, reason };
    } catch (err) {
      return {
        backend: this.name,
        decision: "deny",
        reason: "ramen-ai firewall error (fail-closed)",
        error: (err as Error).message,
      };
    }
  }

  /**
   * Run the firewall and enforce the receipt-verification policy, logging the
   * decision to the AGT audit chain and binding the receipt in the ledger.
   *
   * Returns a {@link ComplianceVerdict} whose `allowed` reflects both the
   * server verdict AND the receipt-verification requirement.
   */
  async runFirewall(action: string, context: Record<string, unknown>): Promise<ComplianceVerdict> {
    const input = extractInputText(context);
    const verdict = await this.client.evaluateCompliance(input, {
      bundleIds: this.opts.bundleIds,
      policyIds: this.opts.policyIds,
    });

    // Fail-closed on evidence: allowed verdict with no valid proof is denied.
    let effectiveAllowed = verdict.allowed;
    let steering = verdict.steering;
    if (effectiveAllowed && this.opts.requireVerifiedReceipt && !verdict.receiptVerified) {
      effectiveAllowed = false;
      steering =
        steering ??
        `Receipt could not be verified (${verdict.receiptReason ?? verdict.receiptAlert ?? "no receipt"})`;
    }

    const effective: ComplianceVerdict = { ...verdict, allowed: effectiveAllowed, steering };
    this.audit(action, effective);
    return effective;
  }

  /**
   * Intercept the agent's proposed action: evaluate, and on a block throw
   * {@link GovernanceDenied} carrying the steering instruction. On allow,
   * invoke and return the wrapped action's result.
   *
   * Fail-safe by construction: the wrapped `run` callback is invoked **only**
   * after a verified `allow` verdict. Any failure — a policy block, an
   * unverifiable receipt, OR an infrastructure error (API timeout, 5xx,
   * malformed body) — results in a thrown {@link GovernanceDenied} and the
   * tool never executes. Callers therefore catch a single, uniform error type
   * regardless of whether the cause was policy or transport (fail-closed).
   */
  async governAction<T>(
    action: string,
    context: Record<string, unknown>,
    run: () => Promise<T> | T,
  ): Promise<T> {
    let verdict: ComplianceVerdict;
    try {
      verdict = await this.runFirewall(action, context);
    } catch (err) {
      // Infrastructure/evaluation failure — deny rather than risk executing an
      // unevaluated action. Surface it as the same GovernanceDenied type so the
      // host agent has one error contract to handle.
      throw GovernanceDenied.failClosed(action, (err as Error).message);
    }
    if (!verdict.allowed) {
      throw new GovernanceDenied(verdict.steering ?? "", verdict);
    }
    return run();
  }

  /** Log to the AGT AuditLogger (if provided) and bind the receipt by hash. */
  private audit(action: string, verdict: ComplianceVerdict): void {
    if (!this.opts.auditLogger) return;
    const decision: LegacyPolicyDecision = verdict.allowed ? "allow" : "deny";
    const entry: AuditEntry = this.opts.auditLogger.log({
      agentId: this.opts.agentId,
      action,
      decision,
    });
    this.ledger.bind({
      auditHash: entry.hash,
      agentId: entry.agentId,
      action: entry.action,
      decision,
      steering: verdict.steering,
      statutoryAnchors: verdict.statutoryAnchors,
      receiptVerified: verdict.receiptVerified,
      receipt: verdict.receipt,
    });
  }
}
