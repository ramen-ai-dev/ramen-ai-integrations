import assert from "node:assert/strict";
import test from "node:test";

import { RamenClient } from "../dist/index.js";

const POLICY_ID = "1006492f-db62-4f46-8775-48b966c5c956";

function response() {
  return new Response(JSON.stringify({
    data: {
      allowed: true,
      policy_ids: [POLICY_ID],
      policies_evaluated: 1,
      policies_passed: 1,
      policies_failed: 0,
      policies_errored: 0,
      total_violations: [],
      results: [],
      execution_time_ms: 1,
      executed_at: "2026-08-12T00:00:00Z",
    },
  }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function client(expectedBody) {
  return new RamenClient({
    apiKey: "ramen_ak_test",
    baseUrl: "https://example.test",
    fetchImpl: async (url, init) => {
      assert.equal(url, "https://example.test/api/v1/paas/evaluate");
      assert.deepEqual(JSON.parse(init.body), expectedBody);
      return response();
    },
  });
}

test("evaluateCompliance omits attestation by default", async () => {
  const expectedBody = {
    input: "evaluate me",
    policy_ids: [POLICY_ID],
  };

  const result = await client(expectedBody).evaluateCompliance("evaluate me", {
    policyIds: [POLICY_ID],
  });

  assert.equal(result.allowed, true);
});

test("evaluateCompliance forwards attestation", async () => {
  const attestation = {
    vendor: "mock",
    evidence: "signed-evidence",
    challenge: "challenge-digest",
    metadata: { tee: "test" },
  };
  const expectedBody = {
    input: "evaluate me",
    policy_ids: [POLICY_ID],
    attestation,
  };

  const result = await client(expectedBody).evaluateCompliance("evaluate me", {
    policyIds: [POLICY_ID],
    attestation,
  });

  assert.equal(result.allowed, true);
});
