/**
 * RamenClient — Promise-based HTTP client for the ramen-ai PaaS evaluation
 * API, built on the global `fetch`.
 *
 * It calls `POST /api/v1/paas/evaluate`, verifies the V5 receipt locally,
 * and returns a normalized {@link ComplianceVerdict}.
 */

import type {
  ComplianceVerdict,
  EvaluationResponse,
  RamenReceipt,
} from "./types.js";
import {
  generateGoverned as executeGoverned,
  generateGovernedStream as streamGoverned,
} from "./governed.js";
import type {
  GenerateGovernedOptions,
  GovernedCompleteData,
  GovernedStreamEvent,
} from "./governed-types.js";
import { verifyReceipt, AUDIT_PUBLIC_KEYS } from "./verifier.js";

const DEFAULT_BASE_URL = "https://api.ramenai.dev";
const EVALUATE_PATH = "/api/v1/paas/evaluate";

export interface RamenClientOptions {
  apiKey: string;
  baseUrl?: string;
  /**
   * BYOK (Bring Your Own Key) — LLM provider API key.
   *
   * Required on the Starter and Professional tiers, where the ramen-ai backend
   * performs LLM inference using the caller's own provider key rather than a
   * platform-managed key. When present, the value is forwarded as the
   * `X-Provider-Key` HTTP header on every evaluation request. Omit on
   * Enterprise tiers where managed keys are provisioned server-side.
   *
   * Store this value in an environment variable or secret store — never
   * hard-code it. Example: `providerKey: process.env.OPENAI_API_KEY`
   */
  providerKey?: string;
  /**
   * BYOK — LLM provider name. Selects which provider the backend routes
   * the inference request to when `providerKey` is present.
   *
   * Accepted values: `"openai"` (default) | `"anthropic"` | `"google"` |
   * `"synthetic"` | `"hyperbolic"`.
   *
   * When omitted the backend defaults to `openai`. Has no effect when
   * `providerKey` is absent (managed-inference tiers ignore this header).
   *
   * Example: `providerName: "anthropic"` paired with an Anthropic `sk-ant-…`
   * key in `providerKey`.
   */
  providerName?: string;
  /** Override the public-key map (e.g. for test-vector verification). */
  publicKeys?: Record<string, string>;
  /** Injectable fetch for testing; defaults to global fetch. */
  fetchImpl?: typeof fetch;
  /** Request timeout in ms (default 30000). */
  timeoutMs?: number;
}

export interface EvaluateOptions {
  bundleIds?: string[];
  policyIds?: string[];
  context?: Record<string, string>;
}

export class RamenClient {
  private readonly apiKey: string;
  private readonly baseUrl: string;
  private readonly providerKey: string | undefined;
  private readonly providerName: string | undefined;
  private readonly publicKeys: Record<string, string>;
  private readonly fetchImpl: typeof fetch;
  private readonly timeoutMs: number;

  constructor(opts: RamenClientOptions) {
    if (!opts.apiKey) throw new Error("RamenClient requires a non-empty apiKey");
    this.apiKey = opts.apiKey;
    this.baseUrl = opts.baseUrl ?? DEFAULT_BASE_URL;
    this.providerKey = opts.providerKey;
    this.providerName = opts.providerName;
    this.publicKeys = opts.publicKeys ?? AUDIT_PUBLIC_KEYS;
    this.fetchImpl = opts.fetchImpl ?? globalThis.fetch;
    this.timeoutMs = opts.timeoutMs ?? 30_000;
    if (typeof this.fetchImpl !== "function") {
      throw new Error("No fetch implementation available; pass opts.fetchImpl");
    }
  }

  /**
   * Evaluate `input` against the given policies/bundles, verify the receipt,
   * and return a normalized verdict.
   *
   * Fail-closed: any transport or parse error throws; callers must treat a
   * thrown error as a denial.
   */
  async evaluateCompliance(input: string, opts: EvaluateOptions = {}): Promise<ComplianceVerdict> {
    if (!opts.bundleIds?.length && !opts.policyIds?.length) {
      throw new Error("Provide at least one of bundleIds or policyIds");
    }

    const body: Record<string, unknown> = { input };
    if (opts.bundleIds?.length) body.bundle_ids = opts.bundleIds;
    if (opts.policyIds?.length) body.policy_ids = opts.policyIds;
    if (opts.context) body.context = opts.context;

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    let envelope: { data?: EvaluationResponse };
    try {
      const headers: Record<string, string> = {
        Authorization: `Bearer ${this.apiKey}`,
        "Content-Type": "application/json",
      };
      // BYOK: forward the caller's LLM provider key when present.
      // Required on Starter/Professional tiers; omit on Enterprise.
      if (this.providerKey) {
        headers["X-Provider-Key"] = this.providerKey;
        // Optionally select the target provider (default: openai).
        // Only meaningful alongside a providerKey; ignored on managed tiers.
        if (this.providerName) headers["X-Provider"] = this.providerName;
      }

      const res = await this.fetchImpl(`${this.baseUrl}${EVALUATE_PATH}`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!res.ok) {
        throw new Error(`evaluate failed: HTTP ${res.status} ${res.statusText}`);
      }
      envelope = (await res.json()) as { data?: EvaluationResponse };
    } finally {
      clearTimeout(timer);
    }

    const data = envelope.data;
    if (!data) throw new Error("evaluate response missing data envelope");

    return this.normalize(data, input);
  }

  /** Generate content and return it only after strict governance approval. */
  async generateGoverned(
    prompt: string,
    options: GenerateGovernedOptions,
  ): Promise<GovernedCompleteData> {
    return executeGoverned(
      {
        apiKey: this.apiKey,
        baseUrl: this.baseUrl,
        providerKey: this.providerKey,
        providerName: this.providerName,
        fetchImpl: this.fetchImpl,
      },
      prompt,
      options,
    );
  }

  /** Stream governed progress and the successful terminal event. */
  generateGovernedStream(
    prompt: string,
    options: GenerateGovernedOptions,
  ): AsyncGenerator<GovernedStreamEvent> {
    return streamGoverned(
      {
        apiKey: this.apiKey,
        baseUrl: this.baseUrl,
        providerKey: this.providerKey,
        providerName: this.providerName,
        fetchImpl: this.fetchImpl,
      },
      prompt,
      options,
    );
  }

  /** Verify the receipt (if present) and shape the normalized verdict. */
  private async normalize(data: EvaluationResponse, input: string): Promise<ComplianceVerdict> {
    const receipt: RamenReceipt | undefined = data.receipt;

    let receiptVerified = false;
    let receiptReason: string | undefined;
    if (receipt?.canonical_payload) {
      const result = await verifyReceipt(receipt, input, this.publicKeys);
      receiptVerified = result.valid;
      receiptReason = result.reason;
    }

    const steeringParts: string[] = [];
    // Guard against a malformed 200 body: these are typed as required arrays,
    // but the response is untrusted JSON, so default to [] before iterating.
    for (const v of data.total_violations ?? []) {
      if (v.recovery_instruction) steeringParts.push(v.recovery_instruction);
    }
    for (const r of data.results ?? []) {
      if (r.instruction) steeringParts.push(r.instruction);
    }

    return {
      allowed: data.allowed,
      steering: steeringParts.length ? steeringParts.join(" | ") : null,
      policyIds: data.policy_ids ?? [],
      statutoryAnchors: data.statutory_anchors ?? [],
      receipt,
      receiptVerified,
      receiptReason,
      receiptAlert: data.receipt_alert,
      data,
    };
  }
}
