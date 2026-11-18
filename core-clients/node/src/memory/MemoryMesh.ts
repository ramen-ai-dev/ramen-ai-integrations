/**
 * Enterprise Memory Mesh client (`/api/v1/memory/*`).
 *
 * The mesh is tenant-partitioned. Every call except listing and erasing
 * sub-tenants names a sub-tenant through the `X-Sub-Tenant-ID` header, which
 * is the only way to choose a partition: request bodies never carry
 * `tenant_id` or `sub_tenant_id`, and the server rejects them if they do.
 *
 * Requires an enterprise-tier key with the `memory:write` (trap, fix),
 * `memory:read` (recall, lessons) and `memory:admin` (review, sub-tenants)
 * scopes. Lesson text is community-style data: treat it as data, never as
 * instructions.
 */
import { requestJson, type Transport } from "../http.js";

/** `^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$`; never starts with `__`. */
const SUB_TENANT_ID = /^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$/u;
const LESSON_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u;
const LESSONS_MAX_LIMIT = 100;

export type MemoryReviewStatus =
  | "pending_triage"
  | "pending_review"
  | "quarantined"
  | "approved"
  | "rejected";

export type MemoryReviewDecision = "approve" | "reject" | "quarantine";

/** The receipt fields the mesh verifies. Pass the receipt from `evaluateCompliance`. */
export interface MemoryReceipt {
  kid: string;
  signature: string;
  canonical_payload: string;
  [key: string]: unknown;
}

export interface MemoryViolation {
  rule_id: string;
  rule_name: string;
  reasoning?: string;
  recovery_instruction?: string;
  [key: string]: unknown;
}

/** Selects the partition. Required on every call that works with lessons. */
export interface MemoryCallOptions {
  subTenantId: string;
}

export interface TrapRequest {
  domain: string;
  tool: string;
  /** 16 to 1000 characters, at least 3 words. */
  task_description: string;
  arguments: Record<string, unknown>;
  /** The exact string that was evaluated and signed (BLOCK receipt). */
  evaluated_input: string;
  receipt: MemoryReceipt;
  violations?: MemoryViolation[];
}

export interface TrapResult {
  trap: { recorded: true; trap_id: string; opened_at: string; expires_at: string; joined: boolean };
  steering_directive: string;
  statutory_anchor?: string;
}

export interface FixRequest {
  trap_id: string;
  arguments: Record<string, unknown>;
  /** The exact string that was evaluated and signed (ALLOW receipt). */
  evaluated_input: string;
  receipt: MemoryReceipt;
}

export interface FixResult {
  pairing: {
    paired: true;
    handle: "matched" | "corroborated";
    trap_id: string;
    lesson_id: string;
    review_status: MemoryReviewStatus;
  };
  receipt_verified: true;
}

export interface RecallRequest {
  domain: string;
  tool: string;
  task_description: string;
  arguments: Record<string, unknown>;
  /** Also match lessons that are still `pending_review`. Default: approved only. */
  include_pending?: boolean;
}

export interface RecallLesson {
  lesson_id: string;
  review_status: string;
  domain: string;
  tool: string;
  steering_directive: string;
  statutory_anchor?: string;
  compliant_arguments: unknown;
  changed_paths: unknown;
  block_receipt: { id: string; signature: string };
  allow_receipt: { id: string; signature: string };
}

export type RecallResult =
  | { match: false }
  | { match: true; tier: "exact" | "semantic"; score: number; lesson: RecallLesson };

export interface ListLessonsOptions {
  reviewStatus?: MemoryReviewStatus;
  /** 1 to 100 (default 50). */
  limit?: number;
  /** Cursor: a positive integer timestamp from a previous page. */
  before?: number;
}

/** A lesson in the review queue: the recall fields plus what a reviewer needs. */
export interface ReviewQueueLesson extends RecallLesson {
  task_description: string;
  violation_rule: string | null;
  trap_id: string;
  review_reason: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface LessonList {
  lessons: ReviewQueueLesson[];
  count: number;
}

export interface ReviewResult {
  lesson_id: string;
  review_status: MemoryReviewStatus;
  vector_synced: boolean;
}

export interface SubTenant {
  sub_tenant_id: string;
  created_at_ms: number;
  lesson_count: number;
}

export interface SubTenantList {
  sub_tenants: SubTenant[];
  count: number;
}

export interface EraseResult {
  erased: true;
  lessons_removed: number;
}

export function assertSubTenantId(value: unknown): asserts value is string {
  if (typeof value !== "string" || !SUB_TENANT_ID.test(value)) {
    throw new TypeError(
      "subTenantId must be 1-128 characters from A-Z a-z 0-9 . _ : @ -, starting with a letter or digit",
    );
  }
}

function partition(options: MemoryCallOptions | undefined): Record<string, string> {
  assertSubTenantId(options?.subTenantId);
  return { "X-Sub-Tenant-ID": options.subTenantId };
}

export class MemoryMeshApi {
  readonly #transport: Transport;

  constructor(transport: Transport) {
    this.#transport = transport;
  }

  /** Record a verified BLOCK. Opens a 24-hour window for the matching fix. */
  async trap(request: TrapRequest, options: MemoryCallOptions): Promise<TrapResult> {
    return requestJson<TrapResult>(this.#transport, "POST", "/api/v1/memory/trap", {
      body: request,
      headers: partition(options),
    });
  }

  /** Record a verified ALLOW for an open trap. Creates a lesson that awaits review. */
  async fix(request: FixRequest, options: MemoryCallOptions): Promise<FixResult> {
    return requestJson<FixResult>(this.#transport, "POST", "/api/v1/memory/fix", {
      body: request,
      headers: partition(options),
    });
  }

  /** Look up an approved lesson: exact fingerprint first, then semantic. */
  async recall(request: RecallRequest, options: MemoryCallOptions): Promise<RecallResult> {
    return requestJson<RecallResult>(this.#transport, "POST", "/api/v1/memory/recall", {
      body: request,
      headers: partition(options),
    });
  }

  /** List lessons in the partition, optionally by review status. */
  async lessons(options: MemoryCallOptions, query: ListLessonsOptions = {}): Promise<LessonList> {
    const headers = partition(options);
    const { limit, before } = query;
    if (limit !== undefined && (!Number.isInteger(limit) || limit < 1 || limit > LESSONS_MAX_LIMIT)) {
      throw new RangeError(`limit must be an integer from 1 to ${LESSONS_MAX_LIMIT}`);
    }
    if (before !== undefined && (!Number.isInteger(before) || before < 1)) {
      throw new RangeError("before must be a positive integer");
    }
    return requestJson<LessonList>(this.#transport, "GET", "/api/v1/memory/lessons", {
      query: { review_status: query.reviewStatus, limit, before },
      headers,
    });
  }

  /** Approve, reject or quarantine a lesson (admin scope). */
  async reviewLesson(
    lessonId: string,
    decision: MemoryReviewDecision,
    options: MemoryCallOptions,
    reason?: string,
  ): Promise<ReviewResult> {
    const headers = partition(options);
    if (!LESSON_ID.test(lessonId)) throw new TypeError("lessonId must be a lowercase UUID v4");
    return requestJson<ReviewResult>(this.#transport, "PATCH", `/api/v1/memory/lessons/${lessonId}`, {
      body: reason === undefined ? { decision } : { decision, reason },
      headers,
    });
  }

  /** List the partitions that hold lessons for this tenant (admin scope). */
  async subTenants(): Promise<SubTenantList> {
    return requestJson<SubTenantList>(this.#transport, "GET", "/api/v1/memory/sub-tenants");
  }

  /** Permanently erase one partition: vectors first, then rows (admin scope). */
  async eraseSubTenant(subTenantId: string): Promise<EraseResult> {
    assertSubTenantId(subTenantId);
    return requestJson<EraseResult>(
      this.#transport,
      "DELETE",
      `/api/v1/memory/sub-tenants/${encodeURIComponent(subTenantId)}`,
    );
  }
}
