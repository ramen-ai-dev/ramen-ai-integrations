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
    const upstream = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(
      'event: error\ndata: {"success":false,"error":{"code":"TEST","message":"stop","http_status":400}}\n\n',
      { headers: { "Content-Type": "text/event-stream" } },
    ));
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
    expect(await response.text()).toContain("event: error");
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
