/**
 * Tests for firewall.ts — evaluate() and buildClient()
 *
 * Coverage:
 *   - ALLOWED verdict: evaluate() returns { allowed: true }
 *   - BLOCKED verdict: evaluate() returns { allowed: false, steering, anchors }
 *   - Fail-closed: transport error → { allowed: false, error }
 *   - buildClient: returns a RamenClient instance
 *   - Payload shape: tool name + arguments in evaluated input JSON
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import type { ProxyConfig } from "../src/types.js";

// ---------------------------------------------------------------------------
// Shared fixtures
// ---------------------------------------------------------------------------

const BASE_CONFIG: ProxyConfig = {
  apiKey: "ramen_ak_test",
  bundleIds: ["ramen__shield_core_it"],
  policyIds: [],
  targetCommand: "node",
  targetArgs: ["server.js"],
  logLevel: "silent",
};

const TOOL_PARAMS = {
  name: "drop_database_table",
  arguments: { table_name: "users_prod" },
};

function makeVerdict(allowed: boolean, steering: string | null = null) {
  return {
    allowed,
    steering,
    policyIds: ["abc123"],
    statutoryAnchors: allowed ? [] : ["OWASP ASI-06"],
    receipt: undefined,
    receiptVerified: false,
    receiptReason: undefined,
    receiptAlert: undefined,
    data: {
      allowed,
      policy_ids: ["abc123"],
      policies_evaluated: 1,
      policies_passed: allowed ? 1 : 0,
      policies_failed: allowed ? 0 : 1,
      policies_errored: 0,
      total_violations: allowed
        ? []
        : [
            {
              rule_id: "r1",
              rule_name: "Destructive Execution",
              rule_content: "block",
              enforcement_level: "strict" as const,
              recovery_instruction: steering ?? "Refuse the request.",
            },
          ],
      results: [],
      execution_time_ms: 5,
      executed_at: "2026-06-27T12:00:00.000Z",
      statutory_anchors: allowed ? [] : ["OWASP ASI-06"],
    },
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("evaluate()", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("returns allowed:true on ALLOWED verdict", async () => {
    const mockClient = {
      evaluateCompliance: vi.fn().mockResolvedValue(makeVerdict(true)),
    };

    const { evaluate } = await import("../src/firewall.js");
    const result = await evaluate(TOOL_PARAMS, BASE_CONFIG, mockClient as never);

    expect(result.allowed).toBe(true);
    expect(result.error).toBeUndefined();
  });

  it("returns allowed:false with steering on BLOCKED verdict", async () => {
    const mockClient = {
      evaluateCompliance: vi.fn().mockResolvedValue(
        makeVerdict(false, "Refuse destructive operations.")
      ),
    };

    const { evaluate } = await import("../src/firewall.js");
    const result = await evaluate(TOOL_PARAMS, BASE_CONFIG, mockClient as never);

    expect(result.allowed).toBe(false);
    expect(result.steering).toBe("Refuse destructive operations.");
    expect(result.statutoryAnchors).toContain("OWASP ASI-06");
  });

  it("is fail-closed on transport error", async () => {
    const mockClient = {
      evaluateCompliance: vi.fn().mockRejectedValue(new Error("Connection refused")),
    };

    const { evaluate } = await import("../src/firewall.js");
    const result = await evaluate(TOOL_PARAMS, BASE_CONFIG, mockClient as never);

    expect(result.allowed).toBe(false);
    expect(result.error).toContain("Connection refused");
    expect(result.steering).toContain("fail-closed");
  });

  it("is fail-closed on HTTP 500 error", async () => {
    const mockClient = {
      evaluateCompliance: vi.fn().mockRejectedValue(new Error("evaluate failed: HTTP 500")),
    };

    const { evaluate } = await import("../src/firewall.js");
    const result = await evaluate(TOOL_PARAMS, BASE_CONFIG, mockClient as never);

    expect(result.allowed).toBe(false);
    expect(result.error).toBeDefined();
  });

  it("sends tool name and arguments in evaluation payload", async () => {
    const mockClient = {
      evaluateCompliance: vi.fn().mockResolvedValue(makeVerdict(true)),
    };

    const { evaluate } = await import("../src/firewall.js");
    await evaluate(TOOL_PARAMS, BASE_CONFIG, mockClient as never);

    const [input] = mockClient.evaluateCompliance.mock.calls[0];
    const payload = JSON.parse(input as string);
    expect(payload.tool).toBe("drop_database_table");
    expect(payload.arguments).toEqual({ table_name: "users_prod" });
  });

  it("forwards bundle_ids to evaluateCompliance", async () => {
    const mockClient = {
      evaluateCompliance: vi.fn().mockResolvedValue(makeVerdict(true)),
    };

    const { evaluate } = await import("../src/firewall.js");
    await evaluate(TOOL_PARAMS, BASE_CONFIG, mockClient as never);

    const [, opts] = mockClient.evaluateCompliance.mock.calls[0];
    expect((opts as { bundleIds: string[] }).bundleIds).toEqual(["ramen__shield_core_it"]);
  });

  it("uses policy_ids when bundle_ids is empty", async () => {
    const config = {
      ...BASE_CONFIG,
      bundleIds: [],
      policyIds: ["6c787849-96db-4c92-8df9-10aa8d035527"],
    };
    const mockClient = {
      evaluateCompliance: vi.fn().mockResolvedValue(makeVerdict(true)),
    };

    const { evaluate } = await import("../src/firewall.js");
    await evaluate(TOOL_PARAMS, config, mockClient as never);

    const [, opts] = mockClient.evaluateCompliance.mock.calls[0];
    expect((opts as { policyIds: string[] }).policyIds).toEqual([
      "6c787849-96db-4c92-8df9-10aa8d035527",
    ]);
  });
});

describe("buildClient()", () => {
  it("returns an object with evaluateCompliance method", async () => {
    const { buildClient } = await import("../src/firewall.js");
    const client = buildClient(BASE_CONFIG);
    expect(typeof client.evaluateCompliance).toBe("function");
  });
});
