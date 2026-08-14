import type { Env } from "./env";
import { handleGenerate } from "./generate";
import { applySecurityHeaders, errorResponse, isSameOrigin } from "./http";

async function handleApi(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  if (!isSameOrigin(request)) return errorResponse(403, "ORIGIN_FORBIDDEN", "Cross-origin requests are not allowed");
  if (url.pathname === "/api/demo/generate" && request.method === "POST") return handleGenerate(request, env);
  return errorResponse(404, "NOT_FOUND", "API route not found");
}

export async function handleRequest(request: Request, env: Env): Promise<Response> {
  try {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/api/")) return await handleApi(request, env);
    return applySecurityHeaders(await env.ASSETS.fetch(request));
  } catch (error) {
    console.error("Foundry Worker request failed", error instanceof Error ? error.message : "unknown error");
    return errorResponse(500, "INTERNAL_ERROR", "The demo request could not be completed");
  }
}

export default { fetch: handleRequest };
