/**
 * Read-only resource clients: the global bundle catalogue and the signed
 * receipt ledger.
 */
import { requestJson, type Transport } from "./http.js";

/** A global bundle as listed by `GET /api/v1/safety/bundles`. */
export interface BundleSummary {
  /** The bundle slug to pass as `bundleIds`, for example `ramen__shield_core_it`. */
  id: string;
  name: string;
  description: string | null;
  policy_ids: string[];
  policy_count: number;
}

/**
 * One row of the receipt ledger (`GET /api/v1/paas/receipts`).
 *
 * The ledger does not store `canonical_payload`, so a row cannot be
 * re-verified. Verify the receipt returned by `evaluateCompliance` instead.
 */
export interface ReceiptLedgerEntry {
  id: string;
  timestamp: string;
  policy_ids: string[];
  /** 1 = ALLOW, 0 = BLOCK. */
  verdict: number;
  reasoning: string;
  steering: string;
  statutory_anchors: string[];
  signature: string;
  payload_hash: string;
}

export interface ReceiptLedgerPage {
  receipts: ReceiptLedgerEntry[];
  pagination: { limit: number; offset: number; count: number };
}

export interface ListReceiptsOptions {
  /** 1 to 200 (default 50). The server caps larger values silently, so they are rejected here. */
  limit?: number;
  /** 0 or greater (default 0). */
  offset?: number;
}

export const RECEIPTS_MAX_LIMIT = 200;

export class BundlesApi {
  readonly #transport: Transport;

  constructor(transport: Transport) {
    this.#transport = transport;
  }

  /** List the active global bundles available to the authenticated key. */
  async list(): Promise<BundleSummary[]> {
    return requestJson<BundleSummary[]>(this.#transport, "GET", "/api/v1/safety/bundles");
  }
}

export class ReceiptsApi {
  readonly #transport: Transport;

  constructor(transport: Transport) {
    this.#transport = transport;
  }

  /** List the caller's signed evaluation receipts, newest first. */
  async list(options: ListReceiptsOptions = {}): Promise<ReceiptLedgerPage> {
    const { limit, offset } = options;
    if (limit !== undefined && (!Number.isInteger(limit) || limit < 1 || limit > RECEIPTS_MAX_LIMIT)) {
      throw new RangeError(`limit must be an integer from 1 to ${RECEIPTS_MAX_LIMIT}`);
    }
    if (offset !== undefined && (!Number.isInteger(offset) || offset < 0)) {
      throw new RangeError("offset must be a non-negative integer");
    }
    return requestJson<ReceiptLedgerPage>(this.#transport, "GET", "/api/v1/paas/receipts", {
      query: { limit, offset },
    });
  }
}
