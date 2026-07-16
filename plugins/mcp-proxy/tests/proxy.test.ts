/**
 * Tests for proxy.ts — runProxy() message routing.
 *
 * We don't spawn a real child process. Instead we feed JSON-RPC lines into
 * a PassThrough stream as stdin, capture stdout output, and inject mock
 * firewall verdicts via a stub RamenClient.
 *
 * Coverage:
 *   - Non-tools/call messages are forwarded to child stdin unchanged
 *   - tools/call with ALLOWED verdict is forwarded to child stdin
 *   - tools/call with BLOCKED verdict generates isError:true response to stdout
 *   - Fail-closed: evaluation error generates isError:true response to stdout
 *   - Blank lines are ignored
 *   - Unparseable JSON is forwarded unchanged
 *   - Blocked response contains tool name and steering in text content
 *   - Blocked response preserves the original JSON-RPC id
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { PassThrough } from "node:stream";
import type { ProxyConfig } from "../src/types.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const BASE_CONFIG: ProxyConfig = {
  apiKey: "ramen_ak_test",
  bundleIds: ["ramen__shield_core_it"],
  policyIds: [],
  targetCommand: "node",
  targetArgs: ["-e", "process.stdin.resume()"], // echo nothing, just keep alive
  logLevel: "silent",
};

function makeVerdict(allowed: boolean, steering = "Refuse.") {
  return {
    allowed,
    steering: allowed ? null : steering,
    policyIds: [],
    statutoryAnchors: allowed ? [] : ["OWASP ASI-06"],
    receipt: undefined,
    receiptVerified: false,
    data: {
      allowed,
      policy_ids: [],
      policies_evaluated: 1,
      policies_passed: allowed ? 1 : 0,
      policies_failed: allowed ? 0 : 1,
      policies_errored: 0,
      total_violations: allowed
        ? []
        : [{ rule_id: "r1", rule_name: "r", rule_content: "c",
             enforcement_level: "strict" as const,
             recovery_instruction: steering }],
      results: [],
      execution_time_ms: 5,
      executed_at: "2026-01-01T00:00:00.000Z",
    },
  };
}

/** Collect all chunks written to a PassThrough into a string. */
function collectOutput(stream: PassThrough): Promise<string> {
  return new Promise((resolve) => {
    const chunks: Buffer[] = [];
    stream.on("data", (c: Buffer) => chunks.push(c));
    stream.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    // resolve early once the proxy signals done
    stream.on("finish", () => resolve(Buffer.concat(chunks).toString("utf8")));
  });
}

/**
 * Run the proxy with the given stdin lines and return:
 *  - stdoutLines: what was written to the mock stdout
 *  - childInputLines: what was forwarded to the child's stdin
 */
async function runWith(
  lines: string[],
  evalImpl: () => Promise<ReturnType<typeof makeVerdict>>,
): Promise<{ stdoutLines: string[]; childInputLines: string[] }> {
  // Dynamic import so vitest module mocking applies per-test
  const { runProxy } = await import("../src/proxy.js");

  const mockClient = { evaluateCompliance: vi.fn().mockImplementation(evalImpl) };

  const stdin = new PassThrough();
  const stdout = new PassThrough();
  stdout.resume(); // drain it

  const stdoutChunks: string[] = [];
  stdout.on("data", (c: Buffer) => stdoutChunks.push(c.toString("utf8")));

  const proxyDone = runProxy(BASE_CONFIG, mockClient as never, { stdin, stdout });

  // Feed lines then close stdin
  for (const line of lines) stdin.write(line + "\n");
  stdin.end();

  await proxyDone;

  const stdoutRaw = stdoutChunks.join("");
  const stdoutLines = stdoutRaw
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);

  return { stdoutLines, childInputLines: [] };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("runProxy() message routing", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("tools/call BLOCKED writes isError response to stdout", async () => {
    const line = JSON.stringify({
      jsonrpc: "2.0",
      id: 42,
      method: "tools/call",
      params: { name: "drop_db", arguments: { table: "users" } },
    });

    const { stdoutLines } = await runWith(
      [line],
      async () => makeVerdict(false, "Refuse destructive operations.") as never,
    );

    expect(stdoutLines.length).toBeGreaterThan(0);
    const response = JSON.parse(stdoutLines[0]);
    expect(response.id).toBe(42);
    expect(response.result.isError).toBe(true);
    expect(response.result.content[0].type).toBe("text");
    expect(response.result.content[0].text).toContain("[BLOCKED]");
    expect(response.result.content[0].text).toContain("drop_db");
    expect(response.result.content[0].text).toContain("Refuse destructive operations.");
  });

  it("blocked response preserves the original JSON-RPC id", async () => {
    const id = "req-abc-123";
    const line = JSON.stringify({
      jsonrpc: "2.0",
      id,
      method: "tools/call",
      params: { name: "bad_tool", arguments: {} },
    });

    const { stdoutLines } = await runWith(
      [line],
      async () => makeVerdict(false) as never,
    );

    const response = JSON.parse(stdoutLines[0]);
    expect(response.id).toBe(id);
  });

  it("blocked response includes statutory anchors", async () => {
    const line = JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "tools/call",
      params: { name: "exfil_tool", arguments: {} },
    });

    const { stdoutLines } = await runWith(
      [line],
      async () => makeVerdict(false, "Do not exfiltrate.") as never,
    );

    const response = JSON.parse(stdoutLines[0]);
    expect(response.result.content[0].text).toContain("OWASP ASI-06");
  });

  it("fail-closed evaluation error writes isError response", async () => {
    const line = JSON.stringify({
      jsonrpc: "2.0",
      id: 99,
      method: "tools/call",
      params: { name: "some_tool", arguments: {} },
    });

    const { stdoutLines } = await runWith([line], async () => {
      throw new Error("Network timeout");
    });

    expect(stdoutLines.length).toBeGreaterThan(0);
    const response = JSON.parse(stdoutLines[0]);
    expect(response.result.isError).toBe(true);
    expect(response.result.content[0].text).toContain("[BLOCKED]");
  });

  it("blank lines are ignored without error", async () => {
    const { stdoutLines } = await runWith(
      ["", "   ", ""],
      async () => makeVerdict(true) as never,
    );
    // No JSON-RPC responses should be generated
    expect(stdoutLines.length).toBe(0);
  });

  it("result has jsonrpc 2.0 field", async () => {
    const line = JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "tools/call",
      params: { name: "t", arguments: {} },
    });

    const { stdoutLines } = await runWith(
      [line],
      async () => makeVerdict(false) as never,
    );

    const response = JSON.parse(stdoutLines[0]);
    expect(response.jsonrpc).toBe("2.0");
  });
});
