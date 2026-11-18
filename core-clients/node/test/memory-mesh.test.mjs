import assert from "node:assert/strict";
import test from "node:test";

import { RamenApiError, RamenClient, assertSubTenantId } from "../dist/index.js";
import { jsonResponse, recordingFetch } from "./helpers.mjs";

const SUB = { subTenantId: "customer-42" };
const LESSON_ID = "5f0c1d2e-3a4b-4c5d-8e6f-7a8b9c0d1e2f";
const RECEIPT = { kid: "ramen_pk_v1", signature: "c2ln", canonical_payload: '{"schema_version":"5.0"}' };

function client(handler = () => jsonResponse({ success: true, data: {} })) {
  const { fetchImpl, calls } = recordingFetch(handler);
  return { calls, client: new RamenClient({ apiKey: "test-key", fetchImpl }) };
}

const TRAP = {
  domain: "fintech",
  tool: "dispatch_wire",
  task_description: "Dispatch a wire to a new payee account",
  arguments: { amount_usd: 40000 },
  evaluated_input: "dispatch_wire {...}",
  receipt: RECEIPT,
};

test("trap posts the body and names the partition in X-Sub-Tenant-ID", async () => {
  const result = { trap: { recorded: true, trap_id: "t1", opened_at: "a", expires_at: "b", joined: false }, steering_directive: "Use dual control" };
  const { client: c, calls } = client(() => jsonResponse({ success: true, data: result }, { status: 201 }));
  assert.deepEqual(await c.memory.trap(TRAP, SUB), result);
  assert.equal(calls[0].method, "POST");
  assert.equal(calls[0].url, "https://api.ramenai.dev/api/v1/memory/trap");
  assert.equal(calls[0].headers["X-Sub-Tenant-ID"], "customer-42");
  assert.equal(calls[0].headers.Authorization, "Bearer test-key");
  assert.deepEqual(calls[0].body, TRAP);
  assert.equal("sub_tenant_id" in calls[0].body, false);
  assert.equal("tenant_id" in calls[0].body, false);
});

test("fix and recall use their routes and the partition header", async () => {
  const { client: c, calls } = client();
  await c.memory.fix({ trap_id: "t1", arguments: {}, evaluated_input: "x", receipt: RECEIPT }, SUB);
  await c.memory.recall({ domain: "fintech", tool: "dispatch_wire", task_description: "Dispatch a wire to a new payee", arguments: {}, include_pending: true }, SUB);
  assert.deepEqual(calls.map((call) => call.url.replace("https://api.ramenai.dev", "")), ["/api/v1/memory/fix", "/api/v1/memory/recall"]);
  assert.ok(calls.every((call) => call.headers["X-Sub-Tenant-ID"] === "customer-42"));
  assert.equal(calls[1].body.include_pending, true);
});

test("every lesson call refuses a missing or malformed sub-tenant before any request", async () => {
  const { client: c, calls } = client();
  const bad = [undefined, {}, { subTenantId: "" }, { subTenantId: "__reserved" }, { subTenantId: "has space" }, { subTenantId: "a".repeat(129) }, { subTenantId: "ok\nX-Evil: 1" }];
  for (const options of bad) {
    await assert.rejects(c.memory.trap(TRAP, options), TypeError, JSON.stringify(options));
    await assert.rejects(c.memory.recall(TRAP, options), TypeError);
    await assert.rejects(c.memory.lessons(options), TypeError);
    await assert.rejects(c.memory.reviewLesson(LESSON_ID, "approve", options), TypeError);
  }
  assert.equal(calls.length, 0);
});

test("assertSubTenantId accepts the documented alphabet", () => {
  for (const id of ["a", "customer-42", "org:team@example.com", "A.b_c-d", "9".repeat(128)]) assert.doesNotThrow(() => assertSubTenantId(id), id);
});

test("lessons sends review_status, limit and before as a query string", async () => {
  const { client: c, calls } = client(() => jsonResponse({ success: true, data: { lessons: [], count: 0 } }));
  await c.memory.lessons(SUB, { reviewStatus: "pending_review", limit: 20, before: 1760000000000 });
  assert.equal(calls[0].method, "GET");
  assert.equal(calls[0].url, "https://api.ramenai.dev/api/v1/memory/lessons?review_status=pending_review&limit=20&before=1760000000000");
  assert.equal(calls[0].headers["X-Sub-Tenant-ID"], "customer-42");
});

test("lessons validates paging before any request", async () => {
  const { client: c, calls } = client();
  for (const query of [{ limit: 0 }, { limit: 101 }, { limit: 2.5 }, { before: 0 }, { before: -5 }]) {
    await assert.rejects(c.memory.lessons(SUB, query), RangeError, JSON.stringify(query));
  }
  assert.equal(calls.length, 0);
});

test("reviewLesson patches the lesson with the decision and optional reason", async () => {
  const { client: c, calls } = client(() => jsonResponse({ success: true, data: { lesson_id: LESSON_ID, review_status: "approved", vector_synced: true } }));
  await c.memory.reviewLesson(LESSON_ID, "approve", SUB);
  await c.memory.reviewLesson(LESSON_ID, "quarantine", SUB, "needs a second look");
  assert.equal(calls[0].method, "PATCH");
  assert.equal(calls[0].url, `https://api.ramenai.dev/api/v1/memory/lessons/${LESSON_ID}`);
  assert.deepEqual(calls[0].body, { decision: "approve" });
  assert.deepEqual(calls[1].body, { decision: "quarantine", reason: "needs a second look" });
});

test("reviewLesson rejects an id that could escape the path", async () => {
  const { client: c, calls } = client();
  for (const id of ["../sub-tenants", "not-a-uuid", `${LESSON_ID}/x`, LESSON_ID.toUpperCase()]) {
    await assert.rejects(c.memory.reviewLesson(id, "approve", SUB), TypeError, id);
  }
  assert.equal(calls.length, 0);
});

test("subTenants lists without a partition header", async () => {
  const data = { sub_tenants: [{ sub_tenant_id: "customer-42", created_at_ms: 1, lesson_count: 3 }], count: 1 };
  const { client: c, calls } = client(() => jsonResponse({ success: true, data }));
  assert.deepEqual(await c.memory.subTenants(), data);
  assert.equal(calls[0].url, "https://api.ramenai.dev/api/v1/memory/sub-tenants");
  assert.equal("X-Sub-Tenant-ID" in calls[0].headers, false);
});

test("eraseSubTenant deletes the encoded partition and validates the id", async () => {
  const { client: c, calls } = client(() => jsonResponse({ success: true, data: { erased: true, lessons_removed: 3 } }));
  assert.deepEqual(await c.memory.eraseSubTenant("org:team@example.com"), { erased: true, lessons_removed: 3 });
  assert.equal(calls[0].method, "DELETE");
  assert.equal(calls[0].url, "https://api.ramenai.dev/api/v1/memory/sub-tenants/org%3Ateam%40example.com");
  await assert.rejects(c.memory.eraseSubTenant("../lessons"), TypeError);
  assert.equal(calls.length, 1);
});

test("mesh errors surface the server code, status and details", async () => {
  const body = { success: false, error: { code: "TIER_REQUIRED", message: "Memory Mesh needs the enterprise tier", details: { required: "enterprise" } } };
  const { client: c } = client(() => jsonResponse(body, { status: 403 }));
  await assert.rejects(c.memory.recall(TRAP, SUB), (error) => {
    assert.ok(error instanceof RamenApiError);
    assert.equal(error.status, 403);
    assert.equal(error.code, "TIER_REQUIRED");
    assert.deepEqual(error.details, { required: "enterprise" });
    return true;
  });
});

test("a recall that finds nothing returns { match: false }", async () => {
  const { client: c } = client(() => jsonResponse({ success: true, data: { match: false } }));
  assert.deepEqual(await c.memory.recall(TRAP, SUB), { match: false });
});
