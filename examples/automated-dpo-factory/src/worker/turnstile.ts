import type { Env } from "./env";

interface TurnstileResponse {
  success?: boolean;
  hostname?: string;
  action?: string;
  "error-codes"?: string[];
}

export class TurnstileUnavailableError extends Error {}

function hostnameMatches(requestHostname: string, verifiedHostname: string | undefined): boolean {
  if (verifiedHostname === requestHostname) return true;
  const isLocal = requestHostname === "localhost" || requestHostname === "127.0.0.1";
  return isLocal && verifiedHostname === "dummy-key-pass";
}

export async function verifyTurnstileToken(
  request: Request,
  token: string,
  env: Env,
): Promise<boolean> {
  const form = new FormData();
  form.set("secret", env.TURNSTILE_SECRET_KEY);
  form.set("response", token);
  const remoteIp = request.headers.get("CF-Connecting-IP");
  if (remoteIp) form.set("remoteip", remoteIp);

  let response: Response;
  try {
    response = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
      method: "POST",
      body: form,
    });
  } catch {
    throw new TurnstileUnavailableError("Turnstile verification request failed");
  }
  if (!response.ok) throw new TurnstileUnavailableError("Turnstile verification service rejected the request");

  let verification: TurnstileResponse;
  try {
    verification = (await response.json()) as TurnstileResponse;
  } catch {
    throw new TurnstileUnavailableError("Turnstile verification returned malformed data");
  }

  const requestHostname = new URL(request.url).hostname;
  return (
    verification.success === true &&
    verification.action === env.TURNSTILE_EXPECTED_ACTION &&
    hostnameMatches(requestHostname, verification.hostname)
  );
}
