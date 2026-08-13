import { describe, expect, it } from "vitest";
import { createSessionToken, expiredSessionCookie, sessionCookie, verifySessionToken } from "../src/worker/session";

const secret = "test-session-signing-secret-that-is-long-enough";

describe("signed demo sessions", () => {
  it("creates and verifies a bounded session token", async () => {
    const { token, payload } = await createSessionToken(secret, 3_600, 1_000);
    const verified = await verifySessionToken(token, secret, 1_001);

    expect(verified).toEqual(payload);
    expect(payload.exp).toBe(4_600);
    expect(payload.session_id).toMatch(/^[0-9a-f-]{36}$/u);
  });

  it("rejects tampered and expired tokens", async () => {
    const { token } = await createSessionToken(secret, 60, 1_000);
    const parts = token.split(".");
    const encodedPayload = parts[1] ?? "";
    const replacement = encodedPayload.startsWith("a") ? "b" : "a";
    const tampered = `${parts[0]}.${replacement}${encodedPayload.slice(1)}.${parts[2]}`;

    await expect(verifySessionToken(tampered, secret, 1_001)).resolves.toBeNull();
    await expect(verifySessionToken(token, secret, 1_061)).resolves.toBeNull();
  });

  it("emits strict cookie attributes for issuance and deletion", () => {
    expect(sessionCookie("demo", "token", 3_600)).toBe(
      "demo=token; Path=/; Max-Age=3600; HttpOnly; Secure; SameSite=Strict",
    );
    expect(expiredSessionCookie("demo")).toContain("Max-Age=0; HttpOnly; Secure; SameSite=Strict");
  });
});
