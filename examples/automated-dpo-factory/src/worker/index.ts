import { sessionRequestSchema } from "../shared/schemas";
import { SECURITY_LIMITS } from "../shared/security";
import type { Env } from "./env";
import { handleGenerate } from "./generate";
import { applySecurityHeaders, errorResponse, isSameOrigin, jsonResponse, readJsonBody, RequestBodyError } from "./http";
import { createSessionToken, expiredSessionCookie, readCookie, sessionCookie, verifySessionToken } from "./session";
import { TurnstileUnavailableError, verifyTurnstileToken } from "./turnstile";

async function createSession(request: Request, env: Env): Promise<Response> {
  let input: unknown;
  try {
    input = await readJsonBody(request, SECURITY_LIMITS.maxRequestBytes);
  } catch (error) {
    if (error instanceof RequestBodyError) return errorResponse(error.status, error.code, error.message);
    throw error;
  }

  const parsed = sessionRequestSchema.safeParse(input);
  if (!parsed.success) return errorResponse(400, "INVALID_VERIFICATION", "A valid Turnstile token is required");
  if (!env.TURNSTILE_SECRET_KEY || !env.SESSION_SIGNING_SECRET) return errorResponse(503, "DEMO_NOT_CONFIGURED", "The verification service is not configured");

  const verified = await verifyTurnstileToken(request, parsed.data.turnstileToken, env);
  if (!verified) return errorResponse(403, "VERIFICATION_FAILED", "Turnstile verification failed");

  const { token, payload } = await createSessionToken(
    env.SESSION_SIGNING_SECRET,
    SECURITY_LIMITS.sessionTtlSeconds,
  );
  return jsonResponse(
    { expiresAt: new Date(payload.exp * 1000).toISOString() },
    201,
    { "Set-Cookie": sessionCookie(env.SESSION_COOKIE_NAME, token, SECURITY_LIMITS.sessionTtlSeconds) },
  );
}

async function readSession(request: Request, env: Env): Promise<Response> {
  const token = readCookie(request, env.SESSION_COOKIE_NAME);
  if (!token || !env.SESSION_SIGNING_SECRET) return errorResponse(401, "SESSION_REQUIRED", "No active demo session");
  const session = await verifySessionToken(token, env.SESSION_SIGNING_SECRET);
  if (!session) return errorResponse(401, "SESSION_INVALID", "The demo session is invalid or expired");
  return jsonResponse({ expiresAt: new Date(session.exp * 1000).toISOString() });
}

function deleteSession(env: Env): Response {
  return jsonResponse(
    { success: true },
    200,
    { "Set-Cookie": expiredSessionCookie(env.SESSION_COOKIE_NAME) },
  );
}

async function handleApi(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  if (!isSameOrigin(request)) return errorResponse(403, "ORIGIN_FORBIDDEN", "Cross-origin requests are not allowed");

  if (url.pathname === "/api/demo/config" && request.method === "GET") {
    return jsonResponse({
      turnstileSiteKey: env.TURNSTILE_SITE_KEY,
      turnstileAction: env.TURNSTILE_EXPECTED_ACTION,
      burstLimit: SECURITY_LIMITS.burstLimit,
      burstWindowSeconds: SECURITY_LIMITS.burstWindowSeconds,
    });
  }
  if (url.pathname === "/api/demo/session" && request.method === "GET") return readSession(request, env);
  if (url.pathname === "/api/demo/session" && request.method === "POST") return createSession(request, env);
  if (url.pathname === "/api/demo/session" && request.method === "DELETE") return deleteSession(env);
  if (url.pathname === "/api/demo/generate" && request.method === "POST") return handleGenerate(request, env);
  return errorResponse(404, "NOT_FOUND", "API route not found");
}

export async function handleRequest(request: Request, env: Env): Promise<Response> {
  try {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/api/")) return await handleApi(request, env);
    return applySecurityHeaders(await env.ASSETS.fetch(request));
  } catch (error) {
    if (error instanceof TurnstileUnavailableError) return errorResponse(502, "VERIFICATION_UNAVAILABLE", "Turnstile verification is temporarily unavailable");
    console.error("Foundry Worker request failed", error instanceof Error ? error.message : "unknown error");
    return errorResponse(500, "INTERNAL_ERROR", "The demo request could not be completed");
  }
}

export default { fetch: handleRequest };
