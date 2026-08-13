import { demoConfig, getScenario, buildScenarioPrompt } from "../shared/content";
import { generateRequestSchema } from "../shared/schemas";
import { SECURITY_LIMITS } from "../shared/security";
import { isEventStreamContentType } from "../shared/sse";
import type { Env } from "./env";
import { applySecurityHeaders, errorResponse, readJsonBody, RequestBodyError } from "./http";
import { readCookie, verifySessionToken } from "./session";

const GOVERNED_PATH = "/api/v1/generate/governed";

function governedEndpoint(baseUrl: string): string {
  const url = new URL(GOVERNED_PATH, baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`);
  const local = url.hostname === "localhost" || url.hostname === "127.0.0.1";
  if (url.protocol !== "https:" && !local) throw new Error("RAMEN_API_BASE_URL must use HTTPS");
  return url.toString();
}

export async function handleGenerate(request: Request, env: Env): Promise<Response> {
  const token = readCookie(request, env.SESSION_COOKIE_NAME);
  if (!token) return errorResponse(401, "SESSION_REQUIRED", "Complete verification before running the live demo");

  const session = await verifySessionToken(token, env.SESSION_SIGNING_SECRET);
  if (!session) return errorResponse(401, "SESSION_INVALID", "The demo session is invalid or expired");

  let input: unknown;
  try {
    input = await readJsonBody(request, SECURITY_LIMITS.maxRequestBytes);
  } catch (error) {
    if (error instanceof RequestBodyError) return errorResponse(error.status, error.code, error.message);
    throw error;
  }
  const parsed = generateRequestSchema.safeParse(input);
  if (!parsed.success) return errorResponse(400, "INVALID_REQUEST", "Choose a valid configured scenario");

  const scenario = getScenario(parsed.data.scenarioId);
  if (!scenario) return errorResponse(404, "SCENARIO_NOT_FOUND", "The requested scenario is not configured");
  if (!env.RAMEN_API_KEY || !env.PROVIDER_API_KEY) return errorResponse(503, "DEMO_NOT_CONFIGURED", "The live demo credentials are not configured");

  const rateLimit = await env.DEMO_RATE_LIMITER.limit({ key: session.session_id });
  if (!rateLimit.success) {
    return errorResponse(429, "BURST_LIMIT_EXCEEDED", "This session reached the five-request burst limit; retry after the 60-second window resets");
  }

  const upstreamBody = {
    prompt: buildScenarioPrompt(scenario),
    policy_ids: demoConfig.governance.policyIds,
    max_retries: demoConfig.governance.maxRetries,
    expose_healing_trail: demoConfig.governance.exposeHealingTrail,
    generation: {
      temperature: demoConfig.governance.generation.temperature,
      max_tokens: demoConfig.governance.generation.maxTokens,
    },
  };

  let upstream: Response;
  try {
    upstream = await fetch(governedEndpoint(env.RAMEN_API_BASE_URL), {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.RAMEN_API_KEY}`,
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        "X-Provider-Key": env.PROVIDER_API_KEY,
        "X-Provider": env.PROVIDER_NAME,
      },
      body: JSON.stringify(upstreamBody),
      signal: AbortSignal.timeout(SECURITY_LIMITS.upstreamTimeoutMs),
    });
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === "TimeoutError";
    return errorResponse(504, timedOut ? "UPSTREAM_TIMEOUT" : "UPSTREAM_UNAVAILABLE", timedOut ? "The governed generation timed out" : "The governed generation service is unavailable");
  }

  if (!upstream.ok) {
    return errorResponse(
      upstream.status >= 400 && upstream.status < 500 ? upstream.status : 502,
      "UPSTREAM_REJECTED",
      "The governed generation request was rejected",
    );
  }
  if (!isEventStreamContentType(upstream.headers.get("Content-Type")) || !upstream.body) {
    return errorResponse(502, "UPSTREAM_PROTOCOL_ERROR", "The governed generation service did not return an event stream");
  }

  return applySecurityHeaders(
    new Response(upstream.body, {
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-store, no-transform",
      },
    }),
    true,
  );
}
