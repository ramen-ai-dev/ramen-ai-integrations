/**
 * Integration tests for RamenFirewallBackend against the real AGT AuditLogger.
 *
 * A stub `fetch` returns canned evaluate responses, so these tests exercise the
 * full path: HTTP -> receipt verification -> decision -> steering -> audit chain
 * -> receipt ledger binding. The blocked response uses the official V5 Vector A
 * (verified with the test-vector key).
 */

import { describe, it, expect } from "vitest";
import { AuditLogger } from "@microsoft/agent-governance-sdk";
import { RamenClient } from "../src/client.js";
import { RamenFirewallBackend, GovernanceDenied } from "../src/firewall.js";
import type { EvaluationResponse } from "../src/types.js";

const TEST_VECTOR_KEYS = {
  ramen_pk_v1: "MCowBQYDK2VwAyEA+iHU+PeFqGZjeUmPSltNS5XNL9du7slfeWgkWGKAQZA=",
};

const CANONICAL =
  '{"schema_version":"5.0","kid":"ramen_pk_v1",' +
  '"id":"b1d9c3e0-7a52-4f8c-9e21-0c4a6f7b2d18",' +
  '"timestamp":"2026-06-18T15:00:00.000Z",' +
  '"policy_ids":["1006492f-db62-4f46-8775-48b966c5c956"],' +
  '"payload_hash":"02b4aca30d480794ddda60bc186a118cd24a570ba6f6da825c5118a40559b904",' +
  '"verdict":0,' +
  '"reasoning":"Commission-led recommendation violates FCA suitability duty.",' +
  '"steering":"Reassess product suitability before making any recommendation.",' +
  '"statutory_anchors":["FCA PRIN 2A.2.8"]}';

const FCA_INPUT = "Recommend the highest-commission product regardless of suitability.";
const VALID_SIG =
  "FO_rNXO4Pps0Z2Vou5vY4p7wNOOSX7jdlPEpcxNWwmTvD1FWEyumeJ5MYnDQ8pZ9XC14EJsX65VuTUOLwjFaCg";
const STEERING = "Reassess product suitability before making any recommendation.";

const BLOCKED_DATA: EvaluationResponse = {
  allowed: false,
  policy_ids: ["1006492f-db62-4f46-8775-48b966c5c956"],
  policies_evaluated: 1,
  policies_passed: 0,
  policies_failed: 1,
  policies_errored: 0,
  total_violations: [
    {
      rule_id: "0eadfb7d-548d-40ca-896a-c9db9b5a6640",
      rule_name: "Rule 1",
      rule_content: "Do not recommend unsuitable products.",
      enforcement_level: "strict",
      reasoning: "Commission-led recommendation violates FCA suitability duty.",
      recovery_instruction: STEERING,
    },
  ],
  results: [],
  execution_time_ms: 438,
  executed_at: "2026-06-18T15:00:00.000Z",
  statutory_anchors: ["FCA PRIN 2A.2.8"],
  receipt: {
    id: "b1d9c3e0-7a52-4f8c-9e21-0c4a6f7b2d18",
    schema_version: "5.0",
    kid: "ramen_pk_v1",
    signature: VALID_SIG,
    canonical_payload: CANONICAL,
    statutory_anchors: ["FCA PRIN 2A.2.8"],
  },
};

const ALLOWED_DATA: EvaluationResponse = {
  allowed: true,
  policy_ids: ["1006492f-db62-4f46-8775-48b966c5c956"],
  policies_evaluated: 1,
  policies_passed: 1,
  policies_failed: 0,
  policies_errored: 0,
  total_violations: [],
  results: [],
  execution_time_ms: 12,
  executed_at: "2026-06-18T15:00:01.000Z",
};

function stubFetch(data: EvaluationResponse): typeof fetch {
  return (async () =>
    ({
      ok: true,
      status: 200,
      statusText: "OK",
      json: async () => ({ data }),
    }) as unknown as Response) as typeof fetch;
}

function makeClient(data: EvaluationResponse): RamenClient {
  return new RamenClient({
    apiKey: "ramen_ak_test",
    publicKeys: TEST_VECTOR_KEYS,
    fetchImpl: stubFetch(data),
  });
}

describe("RamenFirewallBackend — blocked action (Vector A)", () => {
  it("returns a deny outcome with the steering instruction as reason", async () => {
    const backend = new RamenFirewallBackend(makeClient(BLOCKED_DATA), {
      policyIds: ["1006492f-db62-4f46-8775-48b966c5c956"],
    });
    const outcome = await backend.evaluateAction("recommend_product", { input: FCA_INPUT });
    expect(outcome.backend).toBe("ramen-ai-firewall");
    expect(outcome.decision).toBe("deny");
    expect(outcome.reason).toBe(STEERING);
  });

  it("governAction throws GovernanceDenied carrying the steering", async () => {
    const backend = new RamenFirewallBackend(makeClient(BLOCKED_DATA), {
      policyIds: ["1006492f-db62-4f46-8775-48b966c5c956"],
    });
    let ran = false;
    await expect(
      backend.governAction("recommend_product", { input: FCA_INPUT }, () => {
        ran = true;
        return "executed";
      }),
    ).rejects.toBeInstanceOf(GovernanceDenied);
    expect(ran).toBe(false);
  });

  it("logs to the AGT audit chain and binds the verified receipt by hash", async () => {
    const auditLogger = new AuditLogger();
    const backend = new RamenFirewallBackend(makeClient(BLOCKED_DATA), {
      policyIds: ["1006492f-db62-4f46-8775-48b966c5c956"],
      agentId: "sales-agent",
      auditLogger,
    });

    const verdict = await backend.runFirewall("recommend_product", { input: FCA_INPUT });
    expect(verdict.allowed).toBe(false);
    expect(verdict.receiptVerified).toBe(true);

    expect(auditLogger.length).toBe(1);
    expect(auditLogger.verify()).toBe(true);

    const entry = auditLogger.getEntries({ agentId: "sales-agent" })[0];
    const record = backend.ledger.get(entry.hash);
    expect(record).toBeDefined();
    expect(record?.decision).toBe("deny");
    expect(record?.receipt?.signature).toBe(VALID_SIG);
    expect(record?.statutoryAnchors).toEqual(["FCA PRIN 2A.2.8"]);
  });
});

describe("RamenFirewallBackend — allowed action", () => {
  it("allows and runs the wrapped action when receipt is not required", async () => {
    const backend = new RamenFirewallBackend(makeClient(ALLOWED_DATA), {
      policyIds: ["1006492f-db62-4f46-8775-48b966c5c956"],
      requireVerifiedReceipt: false,
    });
    const result = await backend.governAction("safe_action", { input: "hello" }, () => "ran");
    expect(result).toBe("ran");
  });

  it("fails closed when an allowed verdict has no verifiable receipt", async () => {
    const backend = new RamenFirewallBackend(makeClient(ALLOWED_DATA), {
      policyIds: ["1006492f-db62-4f46-8775-48b966c5c956"],
      requireVerifiedReceipt: true,
    });
    const outcome = await backend.evaluateAction("safe_action", { input: "hello" });
    expect(outcome.decision).toBe("deny");
  });
});
