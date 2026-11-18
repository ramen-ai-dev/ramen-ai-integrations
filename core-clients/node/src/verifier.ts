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
 * Checks the signature and the input binding only. It does not read the
 * signed verdict, so it cannot tell an ALLOW receipt from a BLOCK receipt.
 * Use {@link signedVerdictProblem} for any allow/deny decision.
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

/** Result of {@link verifyAllowReceiptSignature}. */
export type AllowReceiptCheck = { valid: true } | { valid: false; reason: string };

/**
 * Verify that a V5 receipt is an authentic, signed ALLOW verdict, without the
 * input-hash binding step of {@link verifyReceipt}.
 *
 * Use this when the evaluated input string is not available, for example
 * when contributing an exemplar to ramen forge. It checks the Ed25519
 * signature over `canonical_payload` (key by `kid`) and that the *signed*
 * payload says schema_version "5.0", the same `kid` and `id`, and
 * `verdict === 1`. It does not prove which input the receipt covers.
 *
 * Never throws — failures are returned as `{ valid: false, reason }`.
 */
export async function verifyAllowReceiptSignature(
  receipt: RamenReceipt,
  publicKeys: Record<string, string> = AUDIT_PUBLIC_KEYS,
): Promise<AllowReceiptCheck> {
  try {
    if (!receipt?.canonical_payload || !receipt.signature || !receipt.kid || !receipt.id) {
      return { valid: false, reason: "Receipt must include id, kid, signature, and canonical_payload" };
    }
    const publicKeyB64 = publicKeys[receipt.kid];
    if (!publicKeyB64) return { valid: false, reason: `Unknown kid: ${receipt.kid}` };
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

    // Everything below is read from the signed bytes, not the unsigned fields.
    const signed = JSON.parse(receipt.canonical_payload) as Record<string, unknown>;
    if (signed === null || typeof signed !== "object" || Array.isArray(signed)) {
      return { valid: false, reason: "canonical_payload is not a JSON object" };
    }
    if (signed.schema_version !== "5.0") {
      return { valid: false, reason: `Unexpected signed schema_version: ${String(signed.schema_version)}` };
    }
    if (signed.kid !== receipt.kid) return { valid: false, reason: "Signed kid does not match receipt.kid" };
    if (signed.id !== receipt.id) return { valid: false, reason: "Signed id does not match receipt.id" };
    if (signed.verdict !== 1) {
      return { valid: false, reason: "Signed verdict is not 1 (the evaluated call was blocked)" };
    }
    return { valid: true };
  } catch (err) {
    return { valid: false, reason: `Verification error: ${(err as Error).message}` };
  }
}

/** Unsigned response fields that the signed payload must agree with. */
export interface SignedVerdictBinding {
  /** The response's `executed_at`; must equal the signed `timestamp`. */
  executedAt?: string;
  /** The response's resolved `policy_ids`; must equal the signed list, in order. */
  policyIds?: readonly string[];
  /** The response's `statutory_anchors`; must equal the signed list. Absent counts as empty. */
  statutoryAnchors?: readonly string[] | null;
}

function sameList(left: unknown, right: readonly string[]): boolean {
  return Array.isArray(left) && left.length === right.length && left.every((item, i) => item === right[i]);
}

/**
 * Return why a receipt does not prove a verdict, or `null` if it does.
 *
 * Everything is read from the signed bytes, not from the unsigned response
 * fields. All of these must hold:
 *
 *   1. The receipt carries `id`, `kid`, `signature` and `canonical_payload`.
 *   2. The Ed25519 signature over `canonical_payload` verifies under the key
 *      pinned for `kid` (`ramen_pk_v1` in production).
 *   3. The signed payload has `schema_version` "5.0", the same `kid` and `id`
 *      as the receipt, and `payload_hash === SHA-256(input)`.
 *   4. The signed `verdict` equals `expectedVerdict` (1 = ALLOW, 0 = BLOCK).
 *   5. When `binding` is given, the signed `timestamp`, `policy_ids` and
 *      `statutory_anchors` equal the response's own values.
 *
 * Never throws.
 */
export async function signedVerdictProblem(
  receipt: RamenReceipt | undefined | null,
  input: string,
  expectedVerdict: 0 | 1,
  publicKeys: Record<string, string> = AUDIT_PUBLIC_KEYS,
  binding?: SignedVerdictBinding,
): Promise<string | null> {
  try {
    if (receipt === undefined || receipt === null || typeof receipt !== "object") {
      return "no Schema V5 receipt was returned";
    }
    const { id, kid, signature, canonical_payload: canonical } = receipt;
    if (![id, kid, signature, canonical].every((value) => typeof value === "string" && value.length > 0)) {
      return "receipt is missing id, kid, signature, or canonical_payload";
    }
    if (!Object.hasOwn(publicKeys, kid)) return `Unknown kid: ${kid}`;
    const key = await crypto.subtle.importKey(
      "spki",
      fromBase64(publicKeys[kid] as string),
      { name: "Ed25519" },
      false,
      ["verify"],
    );
    const sigValid = await crypto.subtle.verify("Ed25519", key, fromBase64(signature), utf8(canonical));
    if (!sigValid) return "Signature does not verify against canonical_payload";

    const signed: unknown = JSON.parse(canonical);
    if (signed === null || typeof signed !== "object" || Array.isArray(signed)) {
      return "canonical_payload is not a JSON object";
    }
    const payload = signed as Record<string, unknown>;
    if (payload.schema_version !== "5.0") {
      return `signed schema_version is ${JSON.stringify(payload.schema_version)}, not "5.0"`;
    }
    if (payload.kid !== kid) return "signed kid does not match receipt.kid";
    if (payload.id !== id) return "signed id does not match receipt.id";
    if (payload.payload_hash !== (await sha256Hex(input))) {
      return "signed payload_hash does not match the evaluated input";
    }
    if (typeof payload.verdict !== "number" || payload.verdict !== expectedVerdict) {
      return `signed verdict is ${JSON.stringify(payload.verdict)}, not ${expectedVerdict} (${expectedVerdict === 1 ? "ALLOW" : "BLOCK"})`;
    }
    if (binding !== undefined) {
      if (payload.timestamp !== binding.executedAt) return "signed timestamp does not match the response executed_at";
      if (!sameList(payload.policy_ids, binding.policyIds ?? [])) return "signed policy_ids do not match the response policy_ids";
      const signedAnchors = payload.statutory_anchors ?? [];
      if (!sameList(signedAnchors, binding.statutoryAnchors ?? [])) {
        return "signed statutory_anchors do not match the response statutory_anchors";
      }
    }
    return null;
  } catch (err) {
    return `Verification error: ${(err as Error).message}`;
  }
}
