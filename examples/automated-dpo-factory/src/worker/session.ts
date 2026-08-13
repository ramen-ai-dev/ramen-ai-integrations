interface SessionPayload {
  session_id: string;
  iat: number;
  exp: number;
}

const encoder = new TextEncoder();
const TOKEN_HEADER = encodeBase64Url(encoder.encode(JSON.stringify({ alg: "HS256", typ: "JWT" })));

function encodeBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/u, "");
}

function decodeBase64Url(value: string): Uint8Array {
  const base64 = value.replaceAll("-", "+").replaceAll("_", "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  const binary = atob(base64);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

async function importSigningKey(secret: string): Promise<CryptoKey> {
  if (secret.length < 32) throw new Error("SESSION_SIGNING_SECRET must contain at least 32 characters");
  return crypto.subtle.importKey("raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}

export async function createSessionToken(
  secret: string,
  ttlSeconds: number,
  nowSeconds = Math.floor(Date.now() / 1000),
): Promise<{ token: string; payload: SessionPayload }> {
  const payload: SessionPayload = {
    session_id: crypto.randomUUID(),
    iat: nowSeconds,
    exp: nowSeconds + ttlSeconds,
  };
  const encodedPayload = encodeBase64Url(encoder.encode(JSON.stringify(payload)));
  const unsignedToken = `${TOKEN_HEADER}.${encodedPayload}`;
  const key = await importSigningKey(secret);
  const signature = new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(unsignedToken)));
  return { token: `${unsignedToken}.${encodeBase64Url(signature)}`, payload };
}

export async function verifySessionToken(
  token: string,
  secret: string,
  nowSeconds = Math.floor(Date.now() / 1000),
): Promise<SessionPayload | null> {
  const parts = token.split(".");
  const header = parts[0];
  const encodedPayload = parts[1];
  const encodedSignature = parts[2];
  if (parts.length !== 3 || header !== TOKEN_HEADER || !encodedPayload || !encodedSignature) return null;

  try {
    const key = await importSigningKey(secret);
    const valid = await crypto.subtle.verify(
      "HMAC",
      key,
      decodeBase64Url(encodedSignature),
      encoder.encode(`${header}.${encodedPayload}`),
    );
    if (!valid) return null;

    const parsed = JSON.parse(new TextDecoder().decode(decodeBase64Url(encodedPayload))) as Partial<SessionPayload>;
    if (typeof parsed.session_id !== "string" || !/^[0-9a-f-]{36}$/iu.test(parsed.session_id)) return null;
    if (!Number.isInteger(parsed.iat) || !Number.isInteger(parsed.exp)) return null;
    if ((parsed.iat as number) > nowSeconds + 60 || (parsed.exp as number) <= nowSeconds) return null;
    return parsed as SessionPayload;
  } catch {
    return null;
  }
}

export function readCookie(request: Request, name: string): string | undefined {
  const cookieHeader = request.headers.get("Cookie");
  if (!cookieHeader) return undefined;
  for (const pair of cookieHeader.split(";")) {
    const separator = pair.indexOf("=");
    if (separator === -1) continue;
    const key = pair.slice(0, separator).trim();
    if (key === name) return pair.slice(separator + 1).trim();
  }
  return undefined;
}

export function sessionCookie(name: string, token: string, maxAgeSeconds: number): string {
  return `${name}=${token}; Path=/; Max-Age=${maxAgeSeconds}; HttpOnly; Secure; SameSite=Strict`;
}

export function expiredSessionCookie(name: string): string {
  return `${name}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict`;
}
