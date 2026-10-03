/**
 * RemoteForgeMemoryStore — HTTP client for ramen forge (Level 1 community memory).
 *
 * TypeScript counterpart of ramen-foundry's `RemoteForgeMemoryStore`. Field
 * names match the forge wire contract and foundry's `CorrectionExemplar`, so
 * Python and TypeScript agents share one record shape.
 *
 * Reads (`GET /api/v1/exemplars`) are public and fail open: network errors,
 * timeouts, HTTP errors, and malformed bodies are logged and return `[]`,
 * because memory is advisory and the ramen-ai policy boundary still evaluates
 * every call. Treat recalled exemplars as untrusted guidance.
 *
 * Writes (`POST /api/v1/exemplars`) require a `writeToken` and a complete
 * Schema V5 receipt whose signed verdict is ALLOW. ramen forge rejects records
 * without one, so they are skipped with a warning before any network call.
 * Contributed records are publicly readable.
 */
import type { RamenReceipt } from "../types.js";
import type { RamenProvenanceEnvelope } from "../types/provenance.js";
import { PROVENANCE_VERSION } from "../types/provenance.js";
import { AUDIT_PUBLIC_KEYS, sha256Hex, verifyAllowReceiptSignature } from "../verifier.js";
import { FORGE_DEFAULT_BASE_URL } from "../constants.js";

const EXEMPLARS_PATH = "/api/v1/exemplars";
const MAX_LIMIT = 50;
const MAX_QUERY_LENGTH = 100;
const DOMAIN_RE = /^[a-z0-9][a-z0-9_-]{1,63}$/;
const SHA256_HEX_RE = /^[0-9a-f]{64}$/;
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]", "::1"]);

type JsonObject = Record<string, unknown>;

/** An exemplar as contributed to ramen forge. */
export interface CorrectionExemplarPayload {
  exemplar_id: string;
  task_description: string;
  /** Optional; when present it must equal SHA-256(task_description). */
  task_fingerprint?: string;
  tool_name: string;
  failed_arguments?: JsonObject;
  violation_reason: string;
  primary_statutory_anchor: string;
  steering_directive: string;
  repaired_arguments: JsonObject;
  created_at: string;
  /** Complete Schema V5 receipt of the allowed (repaired) call. */
  receipt: RamenReceipt | null | undefined;
  /** Optional; when present it must equal receipt.id. */
  receipt_id?: string | null;
  /** Defaults to the store's domain. */
  domain?: string;
}

/** An exemplar as served by ramen forge. */
export interface CorrectionExemplar {
  exemplar_id: string;
  domain: string;
  task_description: string;
  task_fingerprint: string;
  tool_name: string;
  failed_arguments: JsonObject;
  violation_reason: string;
  primary_statutory_anchor: string;
  steering_directive: string;
  repaired_arguments: JsonObject;
  receipt_id: string | null;
  created_at: string;
  tier?: string;
  /** Ed25519 signature (base64url) over canonical_payload, for offline audit. */
  signature?: string | null;
  canonical_payload?: string | null;
}

export interface RetrieveExemplarsOptions {
  /** Defaults to the store's domain. */
  domain?: string;
  toolName?: string;
  /** Keyword search over task descriptions, violation rules, and steering directives. */
  query?: string;
  /** Exact-task match: SHA-256 hex of the task description. */
  taskFingerprint?: string;
  /** 1–50, default 3. */
  limit?: number;
}

export type RecordCorrectionResult =
  | { status: "created"; exemplarId: string }
  | { status: "refreshed"; exemplarId: string }
  | { status: "duplicate"; exemplarId: string }
  | { status: "skipped"; reason: string };

export interface MemoryLogger {
  warn(message: string): void;
  info?(message: string): void;
}

export interface RemoteForgeMemoryStoreOptions {
  /** Default https://forge.ramenai.dev. Must be https (http only for localhost). */
  baseUrl?: string;
  /** Bearer token for writes. Without it the store is read-only. */
  writeToken?: string;
  /** Default domain slug, e.g. "fintech". Default "general". */
  domain?: string;
  /** Per-request timeout. Default 5000 ms. */
  timeoutMs?: number;
  /** Injectable fetch, for tests and custom transports. */
  fetchImpl?: typeof fetch;
  /** Defaults to console (stderr). */
  logger?: MemoryLogger;
  /** Override receipt verification keys (e.g. test vectors). */
  publicKeys?: Record<string, string>;
}

export class ForgeWriteError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
    this.name = "ForgeWriteError";
  }
}

function isPlainObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isServedExemplar(value: unknown): value is CorrectionExemplar {
  if (!isPlainObject(value)) return false;
  const strings = [
    "exemplar_id",
    "domain",
    "task_description",
    "task_fingerprint",
    "tool_name",
    "violation_reason",
    "primary_statutory_anchor",
    "steering_directive",
    "created_at",
  ];
  return (
    strings.every((key) => typeof value[key] === "string" && (value[key] as string).length > 0) &&
    isPlainObject(value.failed_arguments) &&
    isPlainObject(value.repaired_arguments) &&
    (value.receipt_id === null || value.receipt_id === undefined || typeof value.receipt_id === "string")
  );
}

export class RemoteForgeMemoryStore {
  readonly baseUrl: string;
  readonly domain: string;
  readonly timeoutMs: number;
  readonly #writeToken: string | undefined;
  readonly #fetch: typeof fetch;
  readonly #logger: MemoryLogger;
  readonly #publicKeys: Record<string, string>;

  constructor(options: RemoteForgeMemoryStoreOptions = {}) {
    const baseUrl = (options.baseUrl ?? FORGE_DEFAULT_BASE_URL).replace(/\/+$/, "");
    let parsed: URL;
    try {
      parsed = new URL(baseUrl);
    } catch {
      throw new Error(`baseUrl is not a valid URL: ${baseUrl}`);
    }
    if (parsed.protocol !== "https:" && !(parsed.protocol === "http:" && LOCAL_HOSTS.has(parsed.hostname))) {
      throw new Error("baseUrl must use https (http is allowed only for localhost)");
    }
    const domain = options.domain ?? "general";
    if (!DOMAIN_RE.test(domain)) {
      throw new Error("domain must be a lowercase slug (a-z, 0-9, '_' or '-', 2-64 characters)");
    }
    const timeoutMs = options.timeoutMs ?? 5000;
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) throw new Error("timeoutMs must be a positive number");

    this.baseUrl = baseUrl;
    this.domain = domain;
    this.timeoutMs = timeoutMs;
    this.#writeToken = options.writeToken?.trim() ? options.writeToken.trim() : undefined;
    this.#fetch = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
    this.#logger = options.logger ?? console;
    this.#publicKeys = options.publicKeys ?? AUDIT_PUBLIC_KEYS;
  }

  /** True when a write token is configured. The token itself is never exposed. */
  get writable(): boolean {
    return this.#writeToken !== undefined;
  }

  /** Avoid leaking the write token through JSON serialisation or logging. */
  toJSON(): Record<string, unknown> {
    return { baseUrl: this.baseUrl, domain: this.domain, timeoutMs: this.timeoutMs, writable: this.writable };
  }

  /**
   * Query ramen forge for exemplars. Every filter except the domain is optional.
   *
   * Invalid options (bad limit, blank or overlong query, bad fingerprint or
   * domain) throw before any network call. Everything after that fails open.
   */
  async retrieveRelevantExemplars(options: RetrieveExemplarsOptions = {}): Promise<CorrectionExemplar[]> {
    const domain = options.domain ?? this.domain;
    if (!DOMAIN_RE.test(domain)) throw new Error("domain must be a lowercase slug");
    const limit = options.limit ?? 3;
    if (!Number.isInteger(limit) || limit < 1 || limit > MAX_LIMIT) {
      throw new Error(`limit must be an integer between 1 and ${MAX_LIMIT}`);
    }
    const params = new URLSearchParams({ domain, limit: String(limit) });
    if (options.toolName !== undefined) {
      if (!options.toolName.trim()) throw new Error("toolName must be a non-blank string");
      params.set("tool_name", options.toolName);
    }
    if (options.taskFingerprint !== undefined) {
      if (!SHA256_HEX_RE.test(options.taskFingerprint)) {
        throw new Error("taskFingerprint must be a lowercase SHA-256 hex digest");
      }
      params.set("task_fingerprint", options.taskFingerprint);
    }
    if (options.query !== undefined) {
      const query = options.query.trim();
      if (!query) throw new Error("query must be a non-blank string");
      if (query.length > MAX_QUERY_LENGTH) throw new Error(`query must be at most ${MAX_QUERY_LENGTH} characters`);
      params.set("q", query);
    }

    let body: unknown;
    try {
      const response = await this.#fetch(`${this.baseUrl}${EXEMPLARS_PATH}?${params.toString()}`, {
        method: "GET",
        headers: { Accept: "application/json" },
        signal: AbortSignal.timeout(this.timeoutMs),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      body = await response.json();
    } catch (err) {
      this.#logger.warn(
        `ramen forge retrieval failed; continuing without exemplars: ${(err as Error).message ?? String(err)}`,
      );
      return [];
    }

    const records = isPlainObject(body) ? body.exemplars : undefined;
    if (!Array.isArray(records)) {
      this.#logger.warn("ramen forge returned an unexpected response shape; ignoring it");
      return [];
    }
    const exemplars: CorrectionExemplar[] = [];
    for (const record of records) {
      if (!isServedExemplar(record)) {
        this.#logger.warn("skipping invalid ramen forge exemplar");
        continue;
      }
      // Fingerprints are deliberately not compared: a lesson for a differently
      // phrased task is still useful for the same tool and domain.
      if (record.domain !== domain || (options.toolName !== undefined && record.tool_name !== options.toolName)) {
        this.#logger.warn(`skipping ramen forge exemplar ${record.exemplar_id} that does not match the query`);
        continue;
      }
      exemplars.push(record);
    }
    return exemplars.slice(0, limit);
  }

  /**
   * Contribute one exemplar. Requires a write token and a complete Schema V5
   * receipt whose Ed25519 signature verifies and whose signed verdict is ALLOW.
   *
   * Returns `skipped` (without a network call) when the exemplar has no
   * receipt. Throws `ForgeWriteError` for an invalid receipt, a missing token,
   * a transport failure, or any forge rejection other than a duplicate id.
   */
  async recordCorrection(exemplar: CorrectionExemplarPayload): Promise<RecordCorrectionResult> {
    if (!isPlainObject(exemplar)) throw new ForgeWriteError("exemplar must be an object");
    if (exemplar.receipt === null || exemplar.receipt === undefined) {
      const reason = `exemplar ${exemplar.exemplar_id} has no Schema V5 receipt; skipping ramen forge upload`;
      this.#logger.warn(reason);
      return { status: "skipped", reason };
    }
    if (!this.#writeToken) throw new ForgeWriteError("RemoteForgeMemoryStore is read-only: no writeToken configured");

    const check = await verifyAllowReceiptSignature(exemplar.receipt, this.#publicKeys);
    if (!check.valid) throw new ForgeWriteError(`receipt is not a verified ALLOW receipt: ${check.reason}`);
    if (exemplar.receipt_id != null && exemplar.receipt_id !== exemplar.receipt.id) {
      throw new ForgeWriteError("receipt_id does not match receipt.id");
    }
    if (!exemplar.task_description?.trim()) throw new ForgeWriteError("task_description must be a non-blank string");
    const fingerprint = await sha256Hex(exemplar.task_description);
    if (exemplar.task_fingerprint !== undefined && exemplar.task_fingerprint !== fingerprint) {
      throw new ForgeWriteError("task_fingerprint does not match SHA-256(task_description)");
    }

    // Only the keys ramen forge accepts; unknown keys are rejected with 422.
    const payload = {
      exemplar_id: exemplar.exemplar_id,
      domain: exemplar.domain ?? this.domain,
      task_description: exemplar.task_description,
      task_fingerprint: fingerprint,
      tool_name: exemplar.tool_name,
      failed_arguments: exemplar.failed_arguments ?? {},
      violation_reason: exemplar.violation_reason,
      primary_statutory_anchor: exemplar.primary_statutory_anchor,
      steering_directive: exemplar.steering_directive,
      repaired_arguments: exemplar.repaired_arguments,
      receipt_id: exemplar.receipt.id,
      receipt: exemplar.receipt,
      created_at: exemplar.created_at,
    };

    let response: Response;
    try {
      response = await this.#fetch(`${this.baseUrl}${EXEMPLARS_PATH}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${this.#writeToken}`,
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch (err) {
      throw new ForgeWriteError(`ramen forge write failed: ${(err as Error).message ?? String(err)}`);
    }

    const body = (await response.json().catch(() => null)) as JsonObject | null;
    if (response.status === 409) {
      this.#logger.info?.(`ramen forge already holds exemplar ${exemplar.exemplar_id}`);
      return { status: "duplicate", exemplarId: exemplar.exemplar_id };
    }
    if (response.status !== 200 && response.status !== 201) {
      throw new ForgeWriteError(
        `ramen forge rejected exemplar ${exemplar.exemplar_id} (HTTP ${response.status}): ${forgeErrorDetail(body)}`,
        response.status,
      );
    }
    const storedId = typeof body?.exemplar_id === "string" ? body.exemplar_id : exemplar.exemplar_id;
    // 200 + refreshed: the same lesson was already stored; only its receipt was swapped.
    return body?.refreshed === true
      ? { status: "refreshed", exemplarId: storedId }
      : { status: "created", exemplarId: storedId };
  }

  /** Filtered listing URL that returns a lesson together with its signature. */
  auditUri(exemplar: Pick<CorrectionExemplar, "domain" | "tool_name" | "task_fingerprint">): string {
    const params = new URLSearchParams({
      domain: exemplar.domain,
      tool_name: exemplar.tool_name,
      task_fingerprint: exemplar.task_fingerprint,
    });
    return `${this.baseUrl}${EXEMPLARS_PATH}?${params.toString()}`;
  }
}

function forgeErrorDetail(body: JsonObject | null): string {
  if (!body) return "no response body";
  const error = body.error;
  let detail = isPlainObject(error)
    ? `${String(error.code ?? "error")}: ${String(error.message ?? "unknown error")}`
    : String(error ?? "unknown error");
  if (Array.isArray(body.details) && body.details.length) {
    detail += `: ${body.details.slice(0, 5).map(String).join("; ")}`;
  }
  return detail;
}

/**
 * Build the `_ramen_provenance` envelope for a governed tool outcome.
 *
 * Lesson fields are null when no exemplar is involved. `audit_uri` is set only
 * for exemplars that came from (or were stored in) ramen forge.
 */
export function buildProvenance(options: {
  domain: string;
  toolName: string;
  receiptId?: string | null;
  exemplar?: Pick<
    CorrectionExemplar,
    "exemplar_id" | "domain" | "tool_name" | "task_fingerprint" | "primary_statutory_anchor" | "steering_directive"
  > | null;
  store?: RemoteForgeMemoryStore | null;
}): RamenProvenanceEnvelope {
  const exemplar = options.exemplar ?? null;
  const fromForge = Boolean(options.store);
  return {
    source: fromForge ? "ramen-forge" : "ramen-local",
    version: PROVENANCE_VERSION,
    domain: options.domain,
    tool_name: options.toolName,
    exemplar_id: exemplar?.exemplar_id ?? null,
    statutory_anchor: exemplar?.primary_statutory_anchor ?? null,
    receipt_id: options.receiptId ?? null,
    prevention_summary: exemplar?.steering_directive ?? null,
    audit_uri: exemplar && options.store ? options.store.auditUri(exemplar) : null,
  };
}
