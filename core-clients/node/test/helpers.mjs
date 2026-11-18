// Shared test helpers. Not a test file (the runner only matches *.test.mjs).
import { createHash, generateKeyPairSync, sign } from "node:crypto";

export const POLICY_ID = "1006492f-db62-4f46-8775-48b966c5c956";
export const RECEIPT_ID = "b1d9c3e0-7a52-4f8c-9e21-0c4a6f7b2d18";
export const EXECUTED_AT = "2026-06-18T15:00:00.000Z";

/** A throwaway Ed25519 signer registered under the given kid. */
export function makeSigner(kid = "ramen_pk_v1") {
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  const keys = { [kid]: publicKey.export({ type: "spki", format: "der" }).toString("base64") };
  /** Sign a receipt. `payload` overrides signed fields; `receipt` overrides unsigned ones. */
  function receipt(input, { verdict, payload = {}, receipt: overrides = {} } = {}) {
    const signed = {
      schema_version: "5.0",
      kid,
      id: RECEIPT_ID,
      timestamp: EXECUTED_AT,
      policy_ids: [POLICY_ID],
      payload_hash: createHash("sha256").update(input, "utf8").digest("hex"),
      verdict,
      reasoning: "",
      steering: "",
      statutory_anchors: ["FCA PRIN 2A.2.8"],
      ...payload,
    };
    const canonical = JSON.stringify(signed);
    return {
      id: RECEIPT_ID,
      schema_version: "5.0",
      kid,
      signature: sign(null, Buffer.from(canonical, "utf8"), privateKey).toString("base64url"),
      canonical_payload: canonical,
      statutory_anchors: ["FCA PRIN 2A.2.8"],
      ...overrides,
    };
  }
  return { keys, receipt };
}

/** A well-formed evaluation `data` object around a receipt. */
export function evaluationData(allowed, receipt, extra = {}) {
  return {
    allowed,
    policy_ids: [POLICY_ID],
    policies_evaluated: 1,
    policies_passed: allowed ? 1 : 0,
    policies_failed: allowed ? 0 : 1,
    policies_errored: 0,
    total_violations: [],
    results: [],
    execution_time_ms: 3,
    executed_at: EXECUTED_AT,
    statutory_anchors: ["FCA PRIN 2A.2.8"],
    ...(receipt === undefined ? {} : { receipt }),
    ...extra,
  };
}

export function jsonResponse(body, init = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

/** A fetch stub that records each call and answers from `handler`. */
export function recordingFetch(handler) {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({
      url: String(url),
      method: init?.method,
      headers: init?.headers ?? {},
      body: init?.body === undefined ? undefined : JSON.parse(init.body),
    });
    return handler(calls[calls.length - 1], calls.length);
  };
  return { fetchImpl, calls };
}
