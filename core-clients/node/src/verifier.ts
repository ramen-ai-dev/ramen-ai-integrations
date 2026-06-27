/**
 * V5 Ed25519 receipt verifier — Web Crypto implementation.
 *
 * This mirrors the backend's Web Crypto signing/verification path exactly
 * (SPKI-DER public key import + one-shot Ed25519 verify over the raw
 * `canonical_payload` string), so there is no cross-language canonicalisation
 * risk. Two steps, per the V5 contract:
 *
 *   1. Verify the signature over `receipt.canonical_payload` (key by `kid`).
 *   2. Parse the payload and confirm `payload_hash === SHA-256(input)`.
 */

import type { RamenReceipt, VerificationResult } from "./types.js";

/** Production public keys by `kid` (base64 SPKI DER). Safe to embed. */
export const AUDIT_PUBLIC_KEYS: Record<string, string> = {
  ramen_pk_v1: "MCowBQYDK2VwAyEA8iTL9lJGYn2alGn1yMWVAIqLImTpADb9CqaLhisTuto=",
};

/** Decode a base64 or base64url string into an ArrayBuffer. */
function fromBase64(b64: string): ArrayBuffer {
  const standard = b64.replace(/-/g, "+").replace(/_/g, "/");
  const pad = (4 - (standard.length % 4)) % 4;
  const bin = atob(standard + "=".repeat(pad));
  const ab = new ArrayBuffer(bin.length);
  const bytes = new Uint8Array(ab);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return ab;
}

/** Encode a UTF-8 string into a fresh ArrayBuffer (BufferSource-safe). */
function utf8(text: string): ArrayBuffer {
  const encoded = new TextEncoder().encode(text);
  const ab = new ArrayBuffer(encoded.byteLength);
  new Uint8Array(ab).set(encoded);
  return ab;
}

/** SHA-256 hex digest of a UTF-8 string. */
export async function sha256Hex(text: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", utf8(text));
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * Verify a V5 receipt against the input that was submitted.
 *
 * Never throws — failures are returned as `{ valid: false, reason }`.
 *
 * @param receipt   The `receipt` object from the evaluate response.
 * @param input     The raw input string that was submitted.
 * @param publicKeys Optional override of the key map (e.g. test-vector keys).
 */
export async function verifyReceipt(
  receipt: RamenReceipt,
  input: string,
  publicKeys: Record<string, string> = AUDIT_PUBLIC_KEYS,
): Promise<VerificationResult> {
  try {
    if (!receipt?.canonical_payload) {
      return { valid: false, reason: "Receipt missing canonical_payload (not a V5 receipt)" };
    }
    const publicKeyB64 = publicKeys[receipt.kid];
    if (!publicKeyB64) return { valid: false, reason: `Unknown kid: ${receipt.kid}` };

    // Step 1 — signature over the exact returned string.
    const key = await crypto.subtle.importKey(
      "spki",
      fromBase64(publicKeyB64),
      { name: "Ed25519" },
      false,
      ["verify"],
    );
    const sigValid = await crypto.subtle.verify(
      "Ed25519",
      key,
      fromBase64(receipt.signature),
      utf8(receipt.canonical_payload),
    );
    if (!sigValid) return { valid: false, reason: "Signature does not verify" };

    // Step 2 — bind the signed payload to the caller's input.
    const payload = JSON.parse(receipt.canonical_payload) as {
      schema_version?: string;
      payload_hash?: string;
    };
    if (payload.schema_version !== "5.0") {
      return { valid: false, reason: `Unexpected schema_version: ${payload.schema_version}` };
    }
    if (payload.payload_hash !== (await sha256Hex(input))) {
      return { valid: false, reason: "payload_hash does not match input" };
    }
    return { valid: true };
  } catch (err) {
    return { valid: false, reason: `Verification error: ${(err as Error).message}` };
  }
}
