const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "base-uri 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "object-src 'none'",
  "img-src 'self' data:",
  "style-src 'self'",
  "script-src 'self' https://challenges.cloudflare.com",
  "frame-src https://challenges.cloudflare.com",
  "connect-src 'self' https://challenges.cloudflare.com",
].join("; ");

export function applySecurityHeaders(response: Response, api = false): Response {
  const headers = new Headers(response.headers);
  headers.set("Content-Security-Policy", CONTENT_SECURITY_POLICY);
  headers.set("Referrer-Policy", "no-referrer");
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("X-Frame-Options", "DENY");
  headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()");
  if (api) headers.set("Cache-Control", "no-store");
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}

export function jsonResponse(value: unknown, status = 200, headers?: HeadersInit): Response {
  const responseHeaders = new Headers(headers);
  responseHeaders.set("Content-Type", "application/json; charset=utf-8");
  responseHeaders.set("Cache-Control", "no-store");
  return applySecurityHeaders(
    new Response(JSON.stringify(value), { status, headers: responseHeaders }),
    true,
  );
}

export function errorResponse(status: number, code: string, message: string): Response {
  return jsonResponse({ success: false, error: { code, message } }, status);
}

export function isSameOrigin(request: Request): boolean {
  const origin = request.headers.get("Origin");
  return origin === null || origin === new URL(request.url).origin;
}

export async function readJsonBody(request: Request, maxBytes: number): Promise<unknown> {
  const contentType = request.headers.get("Content-Type")?.toLowerCase() ?? "";
  if (!contentType.startsWith("application/json")) throw new RequestBodyError(415, "CONTENT_TYPE_REQUIRED", "Content-Type must be application/json");

  const declaredLength = Number(request.headers.get("Content-Length") ?? "0");
  if (Number.isFinite(declaredLength) && declaredLength > maxBytes) throw new RequestBodyError(413, "REQUEST_TOO_LARGE", "Request body is too large");

  const bytes = new Uint8Array(await request.arrayBuffer());
  if (bytes.byteLength > maxBytes) throw new RequestBodyError(413, "REQUEST_TOO_LARGE", "Request body is too large");
  try {
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    throw new RequestBodyError(400, "INVALID_JSON", "Request body must contain valid JSON");
  }
}

export class RequestBodyError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}
