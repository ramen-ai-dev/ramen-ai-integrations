/**
 * Shared JSON transport for the ledger, bundle and Memory Mesh clients.
 *
 * Every failure becomes a {@link RamenApiError}. Success bodies must use the
 * platform envelope `{ success: true, data }`; `data` is returned.
 */
import { RamenApiError } from "./errors.js";

export interface Transport {
  readonly apiKey: string;
  readonly baseUrl: string;
  readonly fetchImpl: typeof fetch;
  readonly timeoutMs: number;
}

export interface RequestOptions {
  query?: Record<string, string | number | undefined>;
  body?: unknown;
  headers?: Record<string, string>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

/** Parse the platform error envelope, tolerating non-JSON bodies. */
export function parseErrorBody(text: string, status: number, statusText: string): RamenApiError {
  let code = `HTTP_${status}`;
  let message = `HTTP ${status} ${statusText}`.trim();
  let details: unknown;
  try {
    const parsed: unknown = JSON.parse(text);
    if (isRecord(parsed) && isRecord(parsed.error)) {
      if (typeof parsed.error.code === "string" && parsed.error.code) code = parsed.error.code;
      if (typeof parsed.error.message === "string" && parsed.error.message) message = parsed.error.message;
      details = parsed.error.details;
    }
  } catch {
    // Not JSON: keep the HTTP-derived code and message.
  }
  return new RamenApiError(status, code, message, details);
}

/** Wrap a fetch rejection (timeout, DNS, TLS, reset) as a typed error. */
export function transportError(error: unknown, timedOut: boolean): RamenApiError {
  if (timedOut || (error instanceof Error && error.name === "AbortError")) {
    return new RamenApiError(null, "TRANSPORT_TIMEOUT", "Request timed out", undefined, error);
  }
  const reason = error instanceof Error && error.message ? error.message : String(error);
  return new RamenApiError(null, "TRANSPORT_ERROR", `Request failed before a response was received: ${reason}`, undefined, error);
}

export async function requestJson<T>(
  transport: Transport,
  method: "GET" | "POST" | "PATCH" | "DELETE",
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const url = new URL(`${transport.baseUrl.replace(/\/+$/, "")}${path}`);
  for (const [key, value] of Object.entries(options.query ?? {})) {
    if (value !== undefined) url.searchParams.set(key, String(value));
  }
  const headers: Record<string, string> = {
    Authorization: `Bearer ${transport.apiKey}`,
    Accept: "application/json",
    ...options.headers,
  };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, transport.timeoutMs);

  let response: Response;
  let text: string;
  try {
    response = await transport.fetchImpl(url.toString(), {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
    });
    text = await response.text();
  } catch (error) {
    throw transportError(error, timedOut);
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) throw parseErrorBody(text, response.status, response.statusText);

  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    throw new RamenApiError(response.status, "INVALID_RESPONSE", "Response body was not valid JSON", undefined, error);
  }
  if (!isRecord(parsed) || parsed.success === false || !("data" in parsed)) {
    throw new RamenApiError(response.status, "INVALID_RESPONSE", "Response did not use the { success, data } envelope");
  }
  return parsed.data as T;
}
