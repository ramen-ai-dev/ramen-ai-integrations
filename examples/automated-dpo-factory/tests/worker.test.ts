import { afterEach, describe, expect, it, vi } from "vitest";
import { handleRequest } from "../src/worker/index";
import type { Env } from "../src/worker/env";

function environment(overrides: Partial<Env> = {}): Env {
  return {
    ASSETS: { fetch: async () => new Response("asset") },
    RAMEN_API_KEY: "ramen-server-key",
    OPENAI_API_KEY: "openai-server-key",
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Foundry Worker stateless proxy", () => {
  it("streams a direct request and attaches secrets only to the governed upstream", async () => {
    const upstream = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => {
      const blocked = {
        success: false,
        error: {
          code: "GOVERNED_OUTPUT_BLOCKED",
          message: "No compliant output was produced within the retry limit",
          http_status: 422,
        },
        data: {
          attempts: 1,
          attempt_metadata: [{
            attempt: 1,
            provider: "openai",
            model: "model",
            generation_duration_ms: 10,
            evaluation_duration_ms: 5,
            policies_evaluated: 1,
            allowed: false,
          }],
          evaluation: {
            allowed: false,
            policy_ids: ["policy"],
            policies_evaluated: 1,
            policies_passed: 0,
            policies_failed: 1,
            policies_errored: 0,
            violation_count: 1,
            statutory_anchors: [],
          },
          accounting: { generation_attempts: 1, evaluation_batches: 1, policy_evaluations: 1 },
          total_duration_ms: 15,
        },
      };
      const frames = [
        'event: status\ndata: {"stage":"accepted","attempt":0}\n\n',
        'event: status\ndata: {"stage":"generating","attempt":0}\n\n',
        'event: status\ndata: {"stage":"evaluating","attempt":0}\n\n',
        'event: status\ndata: {"stage":"scrubbing","attempt":0,"violations":1}\n\n',
        `event: blocked\ndata: ${JSON.stringify(blocked)}\n\n`,
      ];
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          for (const frame of frames) controller.enqueue(new TextEncoder().encode(frame));
          controller.close();
        },
      });
      return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
    });
    vi.stubGlobal("fetch", upstream);

    const response = await handleRequest(new Request("https://demo.example.com/api/demo/generate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Origin: "https://demo.example.com",
      },
      body: JSON.stringify({ scenarioId: "geographic-redlining-proxy" }),
    }), environment());

    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toContain("text/event-stream");
    const downstream = await response.text();
    expect(downstream).toContain('data: {"stage":"scrubbing","attempt":0,"violations":1}');
    expect(downstream).toContain("event: blocked");
    expect(downstream.indexOf('"stage":"scrubbing"')).toBeLessThan(downstream.indexOf("event: blocked"));
    expect(downstream).not.toContain("event: error");
    expect(String(upstream.mock.calls[0]?.[0])).toBe("https://api.ramenai.dev/api/v1/generate/governed");
    const init = upstream.mock.calls[0]?.[1];
    const headers = new Headers(init?.headers);
    expect(headers.get("Authorization")).toBe("Bearer ramen-server-key");
    expect(headers.get("X-Provider-Key")).toBe("openai-server-key");
    expect(headers.get("X-Provider")).toBe("openai");
    const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
    expect(body).toMatchObject({ max_retries: 1, expose_healing_trail: true, generation: { max_tokens: 420, temperature: 0.2 } });
    expect(String(body.prompt)).toContain("Candidate A");
  });

  it("rejects cross-origin requests before upstream work", async () => {
    const outbound = vi.fn();
    vi.stubGlobal("fetch", outbound);

    const response = await handleRequest(new Request("https://demo.example.com/api/demo/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json", Origin: "https://attacker.example.com" },
      body: JSON.stringify({ scenarioId: "pure-merit-control" }),
    }), environment());

    expect(response.status).toBe(403);
    expect(outbound).not.toHaveBeenCalled();
  });

  it("rejects unknown scenarios before upstream work", async () => {
    const outbound = vi.fn();
    vi.stubGlobal("fetch", outbound);

    const response = await handleRequest(new Request("https://demo.example.com/api/demo/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json", Origin: "https://demo.example.com" },
      body: JSON.stringify({ scenarioId: "not-configured" }),
    }), environment());

    expect(response.status).toBe(404);
    expect(outbound).not.toHaveBeenCalled();
  });

  it("fails closed before upstream work when server credentials are absent", async () => {
    const outbound = vi.fn();
    vi.stubGlobal("fetch", outbound);

    const response = await handleRequest(new Request("https://demo.example.com/api/demo/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json", Origin: "https://demo.example.com" },
      body: JSON.stringify({ scenarioId: "pure-merit-control" }),
    }), environment({ RAMEN_API_KEY: "" }));

    expect(response.status).toBe(503);
    expect(outbound).not.toHaveBeenCalled();
  });
});
