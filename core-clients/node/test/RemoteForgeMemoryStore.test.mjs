import assert from "node:assert/strict";
import test from "node:test";
import {
  RemoteForgeMemoryStore,
  ForgeWriteError,
  buildProvenance,
  verifyAllowReceiptSignature,
  sha256Hex,
  INDUSTRIAL_IOT_ACTUATION_INVARIANCE_POLICY_IDS,
  ROBOTICS_PHYSICAL_SAFETY_POLICY_ID,
} from "../dist/index.js";

const BASE = "https://forge.example.test";
const TOKEN = "forge-test-token";
const TASK = "Formulate an adverse action notice for credit application APP-99214.";
const TOOL = "issue_credit_adverse_action";

// A generated key stands in for ramen_pk_v1, whose private half is not available here.
const keyPair = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
const spki = Buffer.from(await crypto.subtle.exportKey("spki", keyPair.publicKey)).toString("base64");
const TEST_KEYS = { ramen_pk_v1: spki };

async function signedReceipt({ id = "8d1f2c4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f", verdict = 1, tamper = false } = {}) {
  const canonical = JSON.stringify({ id, schema_version: "5.0", kid: "ramen_pk_v1", verdict, payload_hash: "00" });
  const sig = await crypto.subtle.sign("Ed25519", keyPair.privateKey, new TextEncoder().encode(canonical));
  return {
    id,
    schema_version: "5.0",
    kid: "ramen_pk_v1",
    signature: Buffer.from(sig).toString("base64url"),
    canonical_payload: tamper ? canonical.replace('"verdict":1', '"verdict":0') : canonical,
    statutory_anchors: [],
    attestation: null,
  };
}

async function servedExemplar(overrides = {}) {
  return {
    exemplar_id: "11111111-1111-4111-8111-111111111111",
    domain: "fintech",
    task_description: TASK,
    task_fingerprint: await sha256Hex(TASK),
    tool_name: TOOL,
    failed_arguments: { reg_b_reason_codes: ["REGIONAL_ECONOMIC_VOLATILITY_ZIP_CODE"] },
    violation_reason: "Denial cites ZIP code as adverse factor.",
    primary_statutory_anchor: "ECOA Regulation B",
    steering_directive: "Use documented neutral creditworthiness factors.",
    repaired_arguments: { reg_b_reason_codes: ["INSUFFICIENT_LIQUIDITY"] },
    receipt_id: "8d1f2c4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f",
    created_at: "2026-10-02T12:00:00+00:00",
    tier: "community",
    signature: "c2ln",
    canonical_payload: "{}",
    ...overrides,
  };
}

async function payload(overrides = {}) {
  return {
    exemplar_id: "22222222-2222-4222-8222-222222222222",
    task_description: TASK,
    tool_name: TOOL,
    failed_arguments: { reg_b_reason_codes: ["REGIONAL_ECONOMIC_VOLATILITY_ZIP_CODE"] },
    violation_reason: "Denial cites ZIP code as adverse factor.",
    primary_statutory_anchor: "ECOA Regulation B",
    steering_directive: "Use documented neutral creditworthiness factors.",
    repaired_arguments: { reg_b_reason_codes: ["INSUFFICIENT_LIQUIDITY"] },
    created_at: "2026-10-03T00:00:00+00:00",
    receipt: await signedReceipt(),
    ...overrides,
  };
}

function json(status, body) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function quietLogger() {
  const warnings = [];
  return { warnings, warn: (m) => warnings.push(m), info: () => {} };
}

function store(fetchImpl, extra = {}) {
  const logger = quietLogger();
  return {
    logger,
    store: new RemoteForgeMemoryStore({
      baseUrl: BASE,
      domain: "fintech",
      writeToken: TOKEN,
      fetchImpl,
      logger,
      publicKeys: TEST_KEYS,
      ...extra,
    }),
  };
}

// ---------------------------------------------------------------------------
// Retrieval
// ---------------------------------------------------------------------------

test("retrieve: sends the query parameters and returns served exemplars", async () => {
  const record = await servedExemplar();
  let seen;
  const { store: s } = store(async (url, init) => {
    seen = { url: new URL(url), init };
    return json(200, { success: true, count: 1, exemplars: [record] });
  });
  const fingerprint = await sha256Hex(TASK);
  const result = await s.retrieveRelevantExemplars({ toolName: TOOL, query: " ZIP ", taskFingerprint: fingerprint, limit: 2 });

  assert.equal(`${seen.url.origin}${seen.url.pathname}`, `${BASE}/api/v1/exemplars`);
  assert.deepEqual(Object.fromEntries(seen.url.searchParams), {
    domain: "fintech", limit: "2", tool_name: TOOL, task_fingerprint: fingerprint, q: "ZIP",
  });
  assert.equal(seen.init.method, "GET");
  assert.equal(seen.init.headers.Authorization, undefined, "reads must not send the write token");
  assert.deepEqual(result, [record]);
});

test("retrieve: domain override and default limit", async () => {
  let seen;
  const { store: s } = store(async (url) => {
    seen = new URL(url);
    return json(200, { exemplars: [] });
  });
  await s.retrieveRelevantExemplars({ domain: "industrial_iot" });
  assert.equal(seen.searchParams.get("domain"), "industrial_iot");
  assert.equal(seen.searchParams.get("limit"), "3");
  assert.equal(seen.searchParams.has("tool_name"), false);
});

test("retrieve: empty response returns []", async () => {
  const { store: s, logger } = store(async () => json(200, { success: true, count: 0, exemplars: [] }));
  assert.deepEqual(await s.retrieveRelevantExemplars({ toolName: TOOL }), []);
  assert.equal(logger.warnings.length, 0);
});

test("retrieve: network timeout, connection failure, HTTP error, and bad body fail open", async () => {
  const failures = [
    async () => { throw new DOMException("The operation was aborted due to timeout", "TimeoutError"); },
    async () => { throw new TypeError("fetch failed"); },
    async () => json(503, { success: false }),
    async () => new Response("<html>not json</html>", { status: 200 }),
    async () => json(200, [{ unexpected: "array" }]),
  ];
  for (const impl of failures) {
    const { store: s, logger } = store(impl);
    assert.deepEqual(await s.retrieveRelevantExemplars({ toolName: TOOL }), []);
    assert.equal(logger.warnings.length, 1);
  }
});

test("retrieve: a real timeout aborts the request and fails open", async () => {
  const { store: s, logger } = store(
    (url, init) => new Promise((_, reject) => init.signal.addEventListener("abort", () => reject(init.signal.reason))),
    { timeoutMs: 20 },
  );
  // AbortSignal.timeout uses an unref'd timer; a real fetch holds a socket open,
  // but this fake does not, so keep the event loop alive until the abort fires.
  const keepAlive = setTimeout(() => {}, 5000);
  try {
    assert.deepEqual(await s.retrieveRelevantExemplars({ toolName: TOOL }), []);
    assert.match(logger.warnings[0], /retrieval failed/);
  } finally {
    clearTimeout(keepAlive);
  }
});

test("retrieve: invalid, wrong-domain, and wrong-tool records are skipped", async () => {
  const good = await servedExemplar();
  const records = [
    { exemplar_id: "x" },
    await servedExemplar({ domain: "devsecops" }),
    await servedExemplar({ tool_name: "dispatch_wire" }),
    await servedExemplar({ task_fingerprint: "f".repeat(64) }), // different phrasing is accepted
    good,
  ];
  const { store: s, logger } = store(async () => json(200, { exemplars: records }));
  const result = await s.retrieveRelevantExemplars({ toolName: TOOL, limit: 5 });
  assert.equal(result.length, 2);
  assert.equal(logger.warnings.length, 3);
});

test("retrieve: invalid options throw before any network call", async () => {
  let calls = 0;
  const { store: s } = store(async () => { calls++; return json(200, { exemplars: [] }); });
  for (const options of [{ limit: 0 }, { limit: 51 }, { limit: 1.5 }, { query: "  " }, { query: "x".repeat(101) },
    { toolName: "" }, { taskFingerprint: "abc" }, { domain: "FinTech" }]) {
    await assert.rejects(() => s.retrieveRelevantExemplars(options));
  }
  assert.equal(calls, 0);
});

// ---------------------------------------------------------------------------
// Ingestion
// ---------------------------------------------------------------------------

test("record: sends the bearer token and the normalised payload with the full receipt", async () => {
  const exemplar = await payload();
  let seen;
  const { store: s } = store(async (url, init) => {
    seen = { url, init, body: JSON.parse(init.body) };
    return json(201, { success: true, exemplar_id: exemplar.exemplar_id });
  });
  const result = await s.recordCorrection(exemplar);

  assert.deepEqual(result, { status: "created", exemplarId: exemplar.exemplar_id });
  assert.equal(seen.url, `${BASE}/api/v1/exemplars`);
  assert.equal(seen.init.method, "POST");
  assert.equal(seen.init.headers.Authorization, `Bearer ${TOKEN}`);
  assert.equal(seen.init.headers["Content-Type"], "application/json");
  assert.deepEqual(Object.keys(seen.body).sort(), [
    "created_at", "domain", "exemplar_id", "failed_arguments", "primary_statutory_anchor", "receipt",
    "receipt_id", "repaired_arguments", "steering_directive", "task_description", "task_fingerprint",
    "tool_name", "violation_reason",
  ]);
  assert.deepEqual(seen.body.receipt, exemplar.receipt);
  assert.equal(seen.body.receipt_id, exemplar.receipt.id);
  assert.equal(seen.body.domain, "fintech");
  assert.equal(seen.body.task_fingerprint, await sha256Hex(TASK));
});

test("record: missing receipt is skipped without a network call", async () => {
  let calls = 0;
  const { store: s, logger } = store(async () => { calls++; return json(201, {}); });
  const result = await s.recordCorrection(await payload({ receipt: undefined }));
  assert.equal(result.status, "skipped");
  assert.equal(calls, 0);
  assert.match(logger.warnings[0], /no Schema V5 receipt/);
});

test("record: unverifiable, blocked, or mismatched receipts are rejected without a network call", async () => {
  let calls = 0;
  const { store: s } = store(async () => { calls++; return json(201, {}); });
  const bad = [
    await payload({ receipt: await signedReceipt({ tamper: true }) }),
    await payload({ receipt: await signedReceipt({ verdict: 0 }) }),
    await payload({ receipt: { ...(await signedReceipt()), kid: "unknown_kid" } }),
    await payload({ receipt_id: "some-other-id" }),
    await payload({ task_fingerprint: "a".repeat(64) }),
  ];
  for (const exemplar of bad) {
    await assert.rejects(() => s.recordCorrection(exemplar), ForgeWriteError);
  }
  assert.equal(calls, 0);
});

test("record: read-only store refuses writes", async () => {
  const { store: s } = store(async () => json(201, {}), { writeToken: undefined });
  assert.equal(s.writable, false);
  const exemplar = await payload();
  await assert.rejects(() => s.recordCorrection(exemplar), /read-only/);
});

test("record: duplicate 409 and refreshed 200 are reported, other errors throw", async () => {
  const exemplar = await payload();
  let { store: s } = store(async () => json(409, { success: false }));
  assert.equal((await s.recordCorrection(exemplar)).status, "duplicate");

  ({ store: s } = store(async () => json(200, { success: true, exemplar_id: "stored-id", refreshed: true })));
  assert.deepEqual(await s.recordCorrection(exemplar), { status: "refreshed", exemplarId: "stored-id" });

  ({ store: s } = store(async () => json(422, {
    success: false,
    error: { code: "INVALID_CRYPTOGRAPHIC_RECEIPT", message: "Exemplar rejected" },
    details: ["signed verdict is not 1"],
  })));
  await assert.rejects(() => s.recordCorrection(exemplar), /HTTP 422.*INVALID_CRYPTOGRAPHIC_RECEIPT.*signed verdict/);

  ({ store: s } = store(async () => { throw new TypeError("fetch failed"); }));
  await assert.rejects(() => s.recordCorrection(exemplar), /write failed/);
});

// ---------------------------------------------------------------------------
// Construction, provenance, constants
// ---------------------------------------------------------------------------

test("constructor: defaults, https enforcement, and token privacy", () => {
  const s = new RemoteForgeMemoryStore({ writeToken: TOKEN });
  assert.equal(s.baseUrl, "https://forge.ramenai.dev");
  assert.equal(s.domain, "general");
  assert.equal(s.timeoutMs, 5000);
  assert.equal(JSON.stringify(s).includes(TOKEN), false);
  assert.equal(Object.values(s).some((v) => v === TOKEN), false);
  assert.throws(() => new RemoteForgeMemoryStore({ baseUrl: "http://forge.example.test" }), /https/);
  new RemoteForgeMemoryStore({ baseUrl: "http://localhost:8787" });
  assert.throws(() => new RemoteForgeMemoryStore({ domain: "Fin Tech" }));
  assert.throws(() => new RemoteForgeMemoryStore({ timeoutMs: 0 }));
});

test("verifyAllowReceiptSignature checks the signed bytes", async () => {
  assert.deepEqual(await verifyAllowReceiptSignature(await signedReceipt(), TEST_KEYS), { valid: true });
  assert.equal((await verifyAllowReceiptSignature(await signedReceipt({ tamper: true }), TEST_KEYS)).valid, false);
  assert.match((await verifyAllowReceiptSignature(await signedReceipt({ verdict: 0 }), TEST_KEYS)).reason, /verdict/);
  // Production key cannot verify a test-key signature.
  assert.equal((await verifyAllowReceiptSignature(await signedReceipt())).valid, false);
});

test("buildProvenance: forge and local envelopes", async () => {
  const exemplar = await servedExemplar();
  const forge = new RemoteForgeMemoryStore({ baseUrl: BASE, domain: "fintech" });
  const env = buildProvenance({ domain: "fintech", toolName: TOOL, receiptId: "r-1", exemplar, store: forge });
  assert.deepEqual(Object.keys(env).sort(), [
    "audit_uri", "domain", "exemplar_id", "prevention_summary", "receipt_id", "source", "statutory_anchor",
    "tool_name", "version",
  ]);
  assert.equal(env.source, "ramen-forge");
  assert.equal(env.version, "1.0");
  assert.equal(env.exemplar_id, exemplar.exemplar_id);
  const audit = new URL(env.audit_uri);
  assert.deepEqual(Object.fromEntries(audit.searchParams), {
    domain: "fintech", tool_name: TOOL, task_fingerprint: exemplar.task_fingerprint,
  });

  const local = buildProvenance({ domain: "general", toolName: "t" });
  assert.equal(local.source, "ramen-local");
  for (const key of ["exemplar_id", "statutory_anchor", "receipt_id", "prevention_summary", "audit_uri"]) {
    assert.equal(local[key], null);
  }
});

test("industrial IoT bundle reference list includes the robotics policy", () => {
  assert.ok(INDUSTRIAL_IOT_ACTUATION_INVARIANCE_POLICY_IDS.includes(ROBOTICS_PHYSICAL_SAFETY_POLICY_ID));
  assert.equal(ROBOTICS_PHYSICAL_SAFETY_POLICY_ID, "1fc71052-eb7e-43fe-9bfa-7ee06afe5b95");
  assert.ok(Object.isFrozen(INDUSTRIAL_IOT_ACTUATION_INVARIANCE_POLICY_IDS));
});
