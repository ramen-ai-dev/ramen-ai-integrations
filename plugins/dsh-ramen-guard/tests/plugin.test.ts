import type { Context } from "@deepseek-ai/cordis";
import type { PreToolDecision, ToolExecution } from "@deepseek-ai/dsh-tools";
import type { ComplianceVerdict } from "@ramen-ai/node-core";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  evaluateCompliance: vi.fn(),
  RamenClient: vi.fn(),
}));

vi.mock("@ramen-ai/node-core", () => ({
  RamenClient: mocks.RamenClient.mockImplementation(() => ({
    evaluateCompliance: mocks.evaluateCompliance,
  })),
}));

import {
  apply,
  BOUNDARY_UNAVAILABLE_REASON,
  Config as ConfigSchema,
  type Config,
} from "../src/index.js";

const CONFIG: Config = {
  apiKey: "ramen_ak_test",
  policyIds: ["policy-test"],
};

const EXECUTION = {
  name: "shell",
  arguments: { command: "rm -rf /" },
  signal: new AbortController().signal,
} as ToolExecution;

type PreExecuteListener = (
  exec: ToolExecution,
  next: () => Promise<PreToolDecision>,
) => Promise<PreToolDecision>;

function verdict(
  allowed: boolean,
  options: { steering?: string | null; receipt?: "verified" | "missing" | "invalid" } = {},
): ComplianceVerdict {
  const receiptState = options.receipt ?? "verified";
  const receipt = receiptState === "missing"
    ? undefined
    : {
        id: "receipt-test",
        schema_version: "5.0",
        kid: "test-key",
        signature: "signature",
        canonical_payload: "payload",
      };

  return {
    allowed,
    steering: options.steering ?? null,
    policyIds: ["policy-test"],
    statutoryAnchors: [],
    receipt,
    receiptVerified: receiptState === "verified",
    data: {
      allowed,
      policy_ids: ["policy-test"],
      policies_evaluated: 1,
      policies_passed: allowed ? 1 : 0,
      policies_failed: allowed ? 0 : 1,
      policies_errored: 0,
      total_violations: [],
      results: [],
      execution_time_ms: 1,
      executed_at: "2026-08-25T00:00:00.000Z",
      receipt,
    },
  };
}

function mount(config: Config = CONFIG) {
  let listener: PreExecuteListener | undefined;
  const logger = {
    info: vi.fn(),
    warn: vi.fn(),
  };
  const ctx = {
    logger,
    on: vi.fn((event: string, callback: PreExecuteListener) => {
      expect(event).toBe("tools/pre-execute");
      listener = callback;
      return vi.fn();
    }),
  } as unknown as Context;

  apply(ctx, config);
  if (!listener) throw new Error("pre-execute listener was not registered");
  return { listener, logger };
}

describe("configuration", () => {
  it.each([
    {
      label: "policy-only enforcement",
      input: { apiKey: "ramen_ak_test", policyIds: ["policy-test"] },
      expectedMode: "enforce",
    },
    {
      label: "bundle-only audit",
      input: { apiKey: "ramen_ak_test", bundleIds: ["bundle-test"], mode: "audit" },
      expectedMode: "audit",
    },
    {
      label: "combined policy and bundle enforcement",
      input: {
        apiKey: "ramen_ak_test",
        policyIds: ["policy-test"],
        bundleIds: ["bundle-test"],
        mode: "enforce",
      },
      expectedMode: "enforce",
    },
  ] as const)("accepts $label", ({ input, expectedMode }) => {
    expect(ConfigSchema(input).mode).toBe(expectedMode);
  });

  it("requires at least one policy or bundle identifier", () => {
    expect(() => ConfigSchema({ apiKey: "ramen_ak_test" } as never)).toThrow();
  });

  it("rejects fail-open mode", () => {
    expect(() => ConfigSchema({
      apiKey: "ramen_ak_test",
      policyIds: ["policy-test"],
      mode: "fail-open",
    } as never)).toThrow();
  });
});

describe("dsh-ramen-guard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("delegates an allowed execution with a verified receipt", async () => {
    mocks.evaluateCompliance.mockResolvedValue(verdict(true));
    const { listener } = mount();
    const next = vi.fn().mockResolvedValue({ kind: "allow" });

    await expect(listener(EXECUTION, next)).resolves.toEqual({ kind: "allow" });
    expect(next).toHaveBeenCalledOnce();
  });

  it("denies a blocked execution with the steering rationale", async () => {
    mocks.evaluateCompliance.mockResolvedValue(
      verdict(false, { steering: "Use a non-destructive command." }),
    );
    const { listener } = mount();
    const next = vi.fn().mockResolvedValue({ kind: "allow" });

    await expect(listener(EXECUTION, next)).resolves.toEqual({
      kind: "deny",
      reason: "Use a non-destructive command.",
    });
    expect(next).not.toHaveBeenCalled();
  });

  it("fails closed with the fixed reason when evaluation is unavailable", async () => {
    mocks.evaluateCompliance.mockRejectedValue(new Error("request timed out"));
    const { listener } = mount();
    const next = vi.fn().mockResolvedValue({ kind: "allow" });

    await expect(listener(EXECUTION, next)).resolves.toEqual({
      kind: "deny",
      reason: BOUNDARY_UNAVAILABLE_REASON,
    });
    expect(next).not.toHaveBeenCalled();
  });

  it("observes tool cancellation while evaluation is pending", async () => {
    mocks.evaluateCompliance.mockReturnValue(new Promise(() => {}));
    const { listener } = mount();
    const next = vi.fn().mockResolvedValue({ kind: "allow" });
    const controller = new AbortController();
    const pending = listener(
      { ...EXECUTION, signal: controller.signal } as ToolExecution,
      next,
    );

    controller.abort();

    await expect(pending).resolves.toEqual({
      kind: "deny",
      reason: BOUNDARY_UNAVAILABLE_REASON,
    });
    expect(next).not.toHaveBeenCalled();
  });

  it.each(["missing", "invalid"] as const)(
    "fails closed when the cryptographic receipt is %s",
    async (receipt) => {
      mocks.evaluateCompliance.mockResolvedValue(verdict(true, { receipt }));
      const { listener } = mount();
      const next = vi.fn().mockResolvedValue({ kind: "allow" });

      await expect(listener(EXECUTION, next)).resolves.toEqual({
        kind: "deny",
        reason: BOUNDARY_UNAVAILABLE_REASON,
      });
      expect(next).not.toHaveBeenCalled();
    },
  );

  it("sends the tool intent and configured policy scope to node-core", async () => {
    mocks.evaluateCompliance.mockResolvedValue(verdict(true));
    const { listener } = mount({
      apiKey: "ramen_ak_test",
      bundleIds: ["bundle-test"],
      policyIds: ["policy-test"],
    });

    await listener(EXECUTION, () => Promise.resolve({ kind: "allow" }));

    expect(mocks.evaluateCompliance).toHaveBeenCalledWith(
      JSON.stringify({ tool: "shell", arguments: { command: "rm -rf /" } }),
      {
        bundleIds: ["bundle-test"],
        policyIds: ["policy-test"],
        context: { tool_name: "shell" },
      },
    );
  });

  it("audit mode logs a denied verdict and delegates execution", async () => {
    mocks.evaluateCompliance.mockResolvedValue(
      verdict(false, { steering: "Would be blocked." }),
    );
    const { listener, logger } = mount({ ...CONFIG, mode: "audit" });
    const next = vi.fn().mockResolvedValue({ kind: "allow" });

    await expect(listener(EXECUTION, next)).resolves.toEqual({ kind: "allow" });
    expect(next).toHaveBeenCalledOnce();
    expect(logger.info).toHaveBeenCalledWith(expect.stringContaining("verdict=deny"));
  });

  it("audit mode logs infrastructure failures and delegates execution", async () => {
    mocks.evaluateCompliance.mockRejectedValue(new Error("HTTP 500"));
    const { listener, logger } = mount({ ...CONFIG, mode: "audit" });
    const next = vi.fn().mockResolvedValue({ kind: "allow" });

    await expect(listener(EXECUTION, next)).resolves.toEqual({ kind: "allow" });
    expect(next).toHaveBeenCalledOnce();
    expect(logger.warn).toHaveBeenCalledWith(expect.stringContaining("HTTP 500"));
  });
});
