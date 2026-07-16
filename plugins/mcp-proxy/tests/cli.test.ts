/**
 * Tests for cli.ts — parseArgs()
 *
 * Coverage:
 *   - --target flag parses command and args
 *   - -- separator parses command and args
 *   - --bundle-ids parses comma-separated slugs
 *   - --policy-ids parses comma-separated UUIDs
 *   - --log-level accepted values
 *   - RAMEN_API_KEY read from environment
 *   - OPENAI_API_KEY / ANTHROPIC_API_KEY read for providerKey
 *   - Missing RAMEN_API_KEY exits with error
 *   - Missing target exits with error
 *   - Missing bundle/policy exits with error
 *   - Unknown flag exits with error
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { parseArgs } from "../src/cli.js";

// parseArgs calls process.exit — mock so tests don't actually exit
const mockExit = vi.spyOn(process, "exit").mockImplementation((_code?: number) => {
  throw new Error(`process.exit(${_code})`);
}) as unknown as ReturnType<typeof vi.spyOn>;

// silence stderr output from usage printer
vi.spyOn(process.stderr, "write").mockImplementation(() => true);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const BASE_ENV = { RAMEN_API_KEY: "ramen_ak_test" };

function parse(
  args: string[],
  env: Record<string, string | undefined> = BASE_ENV,
) {
  return parseArgs(["node", "mcp-shield-proxy", ...args], env);
}

describe("parseArgs()", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockExit.mockImplementation((_code?: number) => {
      throw new Error(`process.exit(${_code})`);
    });
  });

  // ── Successful parses ────────────────────────────────────────────────────

  it("parses --target flag with quoted command", () => {
    const config = parse(["--target", "node server.js", "--bundle-ids", "ramen__shield_core_it"]);
    expect(config.targetCommand).toBe("node");
    expect(config.targetArgs).toEqual(["server.js"]);
  });

  it("parses -- separator for target command", () => {
    const config = parse(["--bundle-ids", "ramen__shield_core_it", "--", "npx", "mcp-server-fetch"]);
    expect(config.targetCommand).toBe("npx");
    expect(config.targetArgs).toEqual(["mcp-server-fetch"]);
  });

  it("parses -- separator with multiple target args", () => {
    const config = parse(["--bundle-ids", "b1", "--", "node", "dist/server.js", "--port", "3000"]);
    expect(config.targetCommand).toBe("node");
    expect(config.targetArgs).toEqual(["dist/server.js", "--port", "3000"]);
  });

  it("parses comma-separated --bundle-ids", () => {
    const config = parse([
      "--target", "node s.js",
      "--bundle-ids", "ramen__shield_core_it,ramen__eu_ai_act_baseline",
    ]);
    expect(config.bundleIds).toEqual(["ramen__shield_core_it", "ramen__eu_ai_act_baseline"]);
  });

  it("parses --policy-ids", () => {
    const config = parse([
      "--target", "node s.js",
      "--policy-ids", "6c787849-96db-4c92-8df9-10aa8d035527",
    ]);
    expect(config.policyIds).toEqual(["6c787849-96db-4c92-8df9-10aa8d035527"]);
    expect(config.bundleIds).toEqual([]);
  });

  it("defaults log level to info", () => {
    const config = parse(["--target", "node s.js", "--bundle-ids", "b1"]);
    expect(config.logLevel).toBe("info");
  });

  it("accepts --log-level debug", () => {
    const config = parse(["--target", "node s.js", "--bundle-ids", "b1", "--log-level", "debug"]);
    expect(config.logLevel).toBe("debug");
  });

  it("accepts --log-level silent", () => {
    const config = parse(["--target", "node s.js", "--bundle-ids", "b1", "--log-level", "silent"]);
    expect(config.logLevel).toBe("silent");
  });

  it("reads RAMEN_API_KEY from env", () => {
    const config = parse(["--target", "node s.js", "--bundle-ids", "b1"]);
    expect(config.apiKey).toBe("ramen_ak_test");
  });

  it("reads OPENAI_API_KEY as providerKey", () => {
    const config = parse(
      ["--target", "node s.js", "--bundle-ids", "b1"],
      { RAMEN_API_KEY: "ramen_ak_test", OPENAI_API_KEY: "sk-test" },
    );
    expect(config.providerKey).toBe("sk-test");
  });

  it("falls back to ANTHROPIC_API_KEY when OPENAI_API_KEY absent", () => {
    const config = parse(
      ["--target", "node s.js", "--bundle-ids", "b1"],
      { RAMEN_API_KEY: "ramen_ak_test", ANTHROPIC_API_KEY: "sk-ant-test" },
    );
    expect(config.providerKey).toBe("sk-ant-test");
  });

  it("reads RAMEN_BASE_URL as baseUrl", () => {
    const config = parse(
      ["--target", "node s.js", "--bundle-ids", "b1"],
      { RAMEN_API_KEY: "ramen_ak_test", RAMEN_BASE_URL: "https://staging.ramenai.dev" },
    );
    expect(config.baseUrl).toBe("https://staging.ramenai.dev");
  });

  // ── Exit conditions ──────────────────────────────────────────────────────

  it("exits when RAMEN_API_KEY is missing", () => {
    expect(() => parse(["--target", "node s.js", "--bundle-ids", "b1"], {})).toThrow("process.exit");
  });

  it("exits when no target is provided", () => {
    expect(() => parse(["--bundle-ids", "b1"])).toThrow("process.exit");
  });

  it("exits when neither --bundle-ids nor --policy-ids provided", () => {
    expect(() => parse(["--target", "node s.js"])).toThrow("process.exit");
  });

  it("exits on unknown flag", () => {
    expect(() =>
      parse(["--target", "node s.js", "--bundle-ids", "b1", "--unknown-flag"])
    ).toThrow("process.exit");
  });

  it("exits on --help", () => {
    expect(() => parse(["--help"])).toThrow("process.exit");
  });

  it("exits on --log-level with invalid value", () => {
    expect(() =>
      parse(["--target", "node s.js", "--bundle-ids", "b1", "--log-level", "verbose"])
    ).toThrow("process.exit");
  });
});
