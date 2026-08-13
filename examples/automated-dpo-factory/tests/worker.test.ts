import { afterEach, describe, expect, it, vi } from "vitest";
import { handleRequest } from "../src/worker/index";
import { createSessionToken } from "../src/worker/session";
import type { Env } from "../src/worker/env";

const signingSecret = "worker-test-signing-secret-with-at-least-32-chars";

function environment(rateLimitSuccess = true): Env {
  return {
    ASSETS: { fetch: async () => new Response("asset") },
    DEMO_RATE_LIMITER: { limit: vi.fn(async () => ({ success: rateLimitSuccess })) },
    RAMEN_API_KEY: "ramen-server-key",
    OPENAI_API_KEY: "openai-server-key",
    TURNSTILE_SECRET_KEY: "turnstile-server-key",
    SESSION_SIGNING_SECRET: signingSecret,
    TURNSTILE_SITE_KEY: "public-site-key",
    TURNSTILE_EXPECTED_ACTION: "foundry-demo",
    SESSION_COOKIE_NAME: "ramen_foundry_session",
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Foundry Worker security boundary", () => {
  it("verifies Turnstile before issuing a strict one-hour cookie", async () => {
    const outbound = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => Response.json({
      success: true,
      hostname: "demo.example.com",
      action: "foundry-demo",
    }));
    vi.stubGlobal("fetch", outbound);

    const response = await handleRequest(new Request("https://demo.example.com/api/demo/session", {
      method: "POST",
      headers: { "Content-Type": "application/json", Origin: "https://demo.example.com" },
      body: JSON.stringify({ turnstileToken: "verified-token" }),
    }), environment());

    expect(response.status).toBe(201);
    expect(response.headers.get("Set-Cookie")).toMatch(/HttpOnly; Secure; SameSite=Strict/u);
    expect(await response.json()).toMatchObject({ expiresAt: expect.any(String) });
    const form = outbound.mock.calls[0]?.[1]?.body;
    expect(form).toBeInstanceOf(FormData);
    expect((form as FormData).get("secret")).toBe("turnstile-server-key");
  });

  it("rejects a mismatched Turnstile hostname", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({
      success: true,
      hostname: "attacker.example.com",
      action: "foundry-demo",
    })));

    const response = await handleRequest(new Request("https://demo.example.com/api/demo/session", {
      method: "POST",
      headers: { "Content-Type": "application/json", Origin: "https://demo.example.com" },
      body: JSON.stringify({ turnstileToken: "token" }),
    }), environment());

    expect(response.status).toBe(403);
    expect(response.headers.get("Set-Cookie")).toBeNull();
  });

  it("keys rate limiting by session ID and attaches secrets only upstream", async () => {
    const env = environment();
    const { token, payload } = await createSessionToken(signingSecret, 3_600);
    const upstream = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => new Response(
      'event: error\ndata: {"success":false,"error":{"code":"TEST","message":"stop","http_status":400}}\n\n',
      { headers: { "Content-Type": "text/event-stream" } },
    ));
    vi.stubGlobal("fetch", upstream);

    const response = await handleRequest(new Request("https://demo.example.com/api/demo/generate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Origin: "https://demo.example.com",
        Cookie: `ramen_foundry_session=${token}`,
      },
      body: JSON.stringify({ scenarioId: "geographic-redlining-proxy" }),
    }), env);

    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toContain("text/event-stream");
    expect(await response.text()).toContain("event: error");
    expect(env.DEMO_RATE_LIMITER.limit).toHaveBeenCalledWith({ key: payload.session_id });
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

  it("stops exhausted sessions before contacting the governed endpoint", async () => {
    const env = environment(false);
    const { token } = await createSessionToken(signingSecret, 3_600);
    const outbound = vi.fn();
    vi.stubGlobal("fetch", outbound);

    const response = await handleRequest(new Request("https://demo.example.com/api/demo/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json", Origin: "https://demo.example.com", Cookie: `ramen_foundry_session=${token}` },
      body: JSON.stringify({ scenarioId: "pure-merit-control" }),
    }), env);

    expect(response.status).toBe(429);
    expect(outbound).not.toHaveBeenCalled();
  });

  it("rejects cross-origin requests before session or upstream work", async () => {
    const response = await handleRequest(new Request("https://demo.example.com/api/demo/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json", Origin: "https://attacker.example.com" },
      body: JSON.stringify({ scenarioId: "pure-merit-control" }),
    }), environment());
    expect(response.status).toBe(403);
  });
});

describe("session recovery", () => {
  it("restores an unexpired HttpOnly-cookie session after a browser reload", async () => {
    const { token, payload } = await createSessionToken(signingSecret, 3_600);
    const response = await handleRequest(new Request("https://demo.example.com/api/demo/session", {
      headers: { Origin: "https://demo.example.com", Cookie: `ramen_foundry_session=${token}` },
    }), environment());

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ expiresAt: new Date(payload.exp * 1_000).toISOString() });
  });
});

describe("burst accounting", () => {
  it("does not consume burst capacity for an unknown scenario", async () => {
    const env = environment();
    const { token } = await createSessionToken(signingSecret, 3_600);
    const response = await handleRequest(new Request("https://demo.example.com/api/demo/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json", Origin: "https://demo.example.com", Cookie: `ramen_foundry_session=${token}` },
      body: JSON.stringify({ scenarioId: "not-configured" }),
    }), env);

    expect(response.status).toBe(404);
    expect(env.DEMO_RATE_LIMITER.limit).not.toHaveBeenCalled();
  });
});
