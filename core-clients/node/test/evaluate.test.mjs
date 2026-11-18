import assert from "node:assert/strict";
import test from "node:test";

import {
  RamenApiError,
  RamenClient,
  ReceiptVerificationError,
  signedVerdictProblem,
} from "../dist/index.js";
import { evaluationData, jsonResponse, makeSigner, POLICY_ID, recordingFetch } from "./helpers.mjs";

const INPUT = "Wire 40,000 USD to account 12-34-56";
const signer = makeSigner();

function client(handler, options = {}) {
  const { fetchImpl, calls } = recordingFetch(handler);
  return {
    calls,
    client: new RamenClient({ apiKey: "test-key", fetchImpl, publicKeys: signer.keys, ...options }),
  };
}

const ok = (data) => () => jsonResponse({ success: true, data });
const policy = { policyIds: [POLICY_ID] };

// --- strict signed-verdict binding -------------------------------------------

test("an authentic BLOCK receipt verifies when the response says blocked", async () => {
  const receipt = signer.receipt(INPUT, { verdict: 0 });
  const { client: c } = client(ok(evaluationData(false, receipt)));
  const verdict = await c.evaluateCompliance(INPUT, policy);
  assert.equal(verdict.allowed, false);
  assert.equal(verdict.receiptVerified, true);
  assert.equal(verdict.receiptReason, undefined);
});

test("an authentic ALLOW receipt verifies when the response says allowed", async () => {
  const receipt = signer.receipt(INPUT, { verdict: 1 });
  const { client: c } = client(ok(evaluationData(true, receipt)));
  assert.equal((await c.evaluateCompliance(INPUT, policy)).receiptVerified, true);
});

test("a genuine BLOCK receipt wrapped in allowed:true is not verified", async () => {
  const receipt = signer.receipt(INPUT, { verdict: 0 });
  const { client: c } = client(ok(evaluationData(true, receipt)));
  const verdict = await c.evaluateCompliance(INPUT, policy);
  assert.equal(verdict.receiptVerified, false);
  assert.match(verdict.receiptReason, /signed verdict is 0, not 1/);
});

test("a genuine ALLOW receipt wrapped in allowed:false is not verified", async () => {
  const receipt = signer.receipt(INPUT, { verdict: 1 });
  const { client: c } = client(ok(evaluationData(false, receipt)));
  const verdict = await c.evaluateCompliance(INPUT, policy);
  assert.equal(verdict.receiptVerified, false);
  assert.match(verdict.receiptReason, /signed verdict is 1, not 0/);
});

test("a swapped receipt id is rejected", async () => {
  const receipt = signer.receipt(INPUT, { verdict: 0, receipt: { id: "99999999-9999-4999-8999-999999999999" } });
  const { client: c } = client(ok(evaluationData(false, receipt)));
  const verdict = await c.evaluateCompliance(INPUT, policy);
  assert.equal(verdict.receiptVerified, false);
  assert.match(verdict.receiptReason, /signed id does not match/);
});

test("a receipt kid that differs from the signed kid is rejected", async () => {
  const two = { ...signer.keys, ramen_pk_other: signer.keys.ramen_pk_v1 };
  const receipt = signer.receipt(INPUT, { verdict: 0, receipt: { kid: "ramen_pk_other" } });
  const problem = await signedVerdictProblem(receipt, INPUT, 0, two);
  assert.match(problem, /signed kid does not match/);
});

test("signed timestamp, policy ids and anchors must match the response", async () => {
  const receipt = signer.receipt(INPUT, { verdict: 0 });
  const cases = [
    [{ executed_at: "2030-01-01T00:00:00.000Z" }, /timestamp/],
    [{ policy_ids: ["2d2f2c8e-1111-4222-8333-444455556666"] }, /policy_ids/],
    [{ statutory_anchors: ["MiFID II Art. 25"] }, /statutory_anchors/],
    [{ statutory_anchors: undefined }, /statutory_anchors/],
  ];
  for (const [override, pattern] of cases) {
    const { client: c } = client(ok(evaluationData(false, receipt, override)));
    const verdict = await c.evaluateCompliance(INPUT, policy);
    assert.equal(verdict.receiptVerified, false, JSON.stringify(override));
    assert.match(verdict.receiptReason, pattern);
  }
});

test("the evaluated input must be the one that was signed", async () => {
  const receipt = signer.receipt(INPUT, { verdict: 0 });
  const { client: c } = client(ok(evaluationData(false, receipt)));
  const verdict = await c.evaluateCompliance(`${INPUT} `, policy);
  assert.equal(verdict.receiptVerified, false);
  assert.match(verdict.receiptReason, /payload_hash/);
});

test("unknown and prototype-named kids are rejected", async () => {
  const receipt = signer.receipt(INPUT, { verdict: 0 });
  for (const kid of ["ramen_pk_v999", "__proto__", "constructor"]) {
    const problem = await signedVerdictProblem({ ...receipt, kid }, INPUT, 0, signer.keys);
    assert.match(problem, /Unknown kid/, kid);
  }
});

test("a tampered signature, a missing field and a non-object payload are rejected", async () => {
  const receipt = signer.receipt(INPUT, { verdict: 0 });
  const flipped = { ...receipt, signature: receipt.signature.slice(0, -2) + "AA" };
  assert.match(await signedVerdictProblem(flipped, INPUT, 0, signer.keys), /Signature does not verify/);
  assert.match(await signedVerdictProblem({ ...receipt, id: "" }, INPUT, 0, signer.keys), /missing id/);
  assert.match(await signedVerdictProblem(undefined, INPUT, 0, signer.keys), /no Schema V5 receipt/);
  assert.equal(await signedVerdictProblem(receipt, INPUT, 0, signer.keys), null);
});

// --- requireVerifiedReceipt ---------------------------------------------------

test("requireVerifiedReceipt passes an authentic response through", async () => {
  const receipt = signer.receipt(INPUT, { verdict: 1 });
  const { client: c } = client(ok(evaluationData(true, receipt)), { requireVerifiedReceipt: true });
  assert.equal((await c.evaluateCompliance(INPUT, policy)).allowed, true);
});

test("requireVerifiedReceipt throws on a tampered response and carries the verdict", async () => {
  const receipt = signer.receipt(INPUT, { verdict: 0 });
  const { client: c } = client(ok(evaluationData(true, receipt)), { requireVerifiedReceipt: true });
  await assert.rejects(c.evaluateCompliance(INPUT, policy), (error) => {
    assert.ok(error instanceof ReceiptVerificationError);
    assert.match(error.reason, /signed verdict is 0/);
    assert.equal(error.verdict.receiptVerified, false);
    return true;
  });
});

test("requireVerifiedReceipt throws when no receipt is returned and reports the alert", async () => {
  const data = evaluationData(true, undefined, { receipt_alert: "RECEIPT_SIGNING_FAILED" });
  const { client: c } = client(ok(data), { requireVerifiedReceipt: true });
  await assert.rejects(c.evaluateCompliance(INPUT, policy), (error) => {
    assert.ok(error instanceof ReceiptVerificationError);
    assert.equal(error.reason, "RECEIPT_SIGNING_FAILED");
    return true;
  });
});

test("without requireVerifiedReceipt a missing receipt is reported, not thrown", async () => {
  const { client: c } = client(ok(evaluationData(true, undefined)));
  const verdict = await c.evaluateCompliance(INPUT, policy);
  assert.equal(verdict.receiptVerified, false);
});

// --- BYOK headers -------------------------------------------------------------

test("provider key and name are forwarded together", async () => {
  const { client: c, calls } = client(ok(evaluationData(true, undefined)), {
    providerKey: "sk-provider-test",
    providerName: "anthropic",
  });
  await c.evaluateCompliance(INPUT, policy);
  assert.equal(calls[0].headers["X-Provider-Key"], "sk-provider-test");
  assert.equal(calls[0].headers["X-Provider"], "anthropic");
});

test("managed mode omits both provider headers", async () => {
  const { client: c, calls } = client(ok(evaluationData(true, undefined)));
  await c.evaluateCompliance(INPUT, policy);
  assert.equal("X-Provider-Key" in calls[0].headers, false);
  assert.equal("X-Provider" in calls[0].headers, false);
});

test("a provider name without a key is never sent", async () => {
  const { client: c, calls } = client(ok(evaluationData(true, undefined)), { providerName: "anthropic" });
  await c.evaluateCompliance(INPUT, policy);
  assert.equal("X-Provider" in calls[0].headers, false);
});

// --- error mapping -------------------------------------------------------------

test("an HTTP error becomes a RamenApiError with the server code and details", async () => {
  const body = { success: false, error: { code: "AUTHORIZATION_REQUIRED", message: "Authorization required", details: { hint: "x" } } };
  const { client: c } = client(() => jsonResponse(body, { status: 401, statusText: "Unauthorized" }));
  await assert.rejects(c.evaluateCompliance(INPUT, policy), (error) => {
    assert.ok(error instanceof RamenApiError);
    assert.equal(error.status, 401);
    assert.equal(error.code, "AUTHORIZATION_REQUIRED");
    assert.deepEqual(error.details, { hint: "x" });
    assert.match(error.message, /evaluate failed: HTTP 401/);
    return true;
  });
});

test("a non-JSON error body keeps an HTTP-derived code", async () => {
  const { client: c } = client(() => new Response("<html>bad gateway</html>", { status: 502, statusText: "Bad Gateway" }));
  await assert.rejects(c.evaluateCompliance(INPUT, policy), (error) => {
    assert.ok(error instanceof RamenApiError);
    assert.equal(error.status, 502);
    assert.equal(error.code, "HTTP_502");
    return true;
  });
});

test("a transport failure becomes TRANSPORT_ERROR and keeps its cause", async () => {
  const { client: c } = client(() => {
    throw new TypeError("fetch failed");
  });
  await assert.rejects(c.evaluateCompliance(INPUT, policy), (error) => {
    assert.ok(error instanceof RamenApiError);
    assert.equal(error.status, null);
    assert.equal(error.code, "TRANSPORT_ERROR");
    assert.match(error.message, /Request failed before a response was received: fetch failed/);
    assert.match(String(error.cause), /fetch failed/);
    return true;
  });
});

test("a request that outlives timeoutMs becomes TRANSPORT_TIMEOUT", async () => {
  const fetchImpl = (_url, init) =>
    new Promise((_resolve, reject) => {
      init.signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })));
    });
  const c = new RamenClient({ apiKey: "k", fetchImpl, timeoutMs: 20, publicKeys: signer.keys });
  await assert.rejects(c.evaluateCompliance(INPUT, policy), (error) => {
    assert.ok(error instanceof RamenApiError);
    assert.equal(error.code, "TRANSPORT_TIMEOUT");
    return true;
  });
});

test("a 200 with a non-JSON body or no data envelope is INVALID_RESPONSE", async () => {
  const bad = client(() => new Response("not json", { status: 200 })).client;
  await assert.rejects(bad.evaluateCompliance(INPUT, policy), (e) => e instanceof RamenApiError && e.code === "INVALID_RESPONSE");
  const empty = client(() => jsonResponse({ success: true })).client;
  await assert.rejects(empty.evaluateCompliance(INPUT, policy), (e) => e instanceof RamenApiError && e.code === "INVALID_RESPONSE");
});

test("evaluateCompliance still requires a bundle or policy id", async () => {
  const { client: c, calls } = client(ok(evaluationData(true, undefined)));
  await assert.rejects(c.evaluateCompliance(INPUT, {}), /at least one of bundleIds or policyIds/);
  assert.equal(calls.length, 0);
});
