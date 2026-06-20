/**
 * V5 Ed25519 verifier tests using the official test vectors from
 * _ref/ramen-ai-backend/docs/integration/alane-gist.md (§3).
 *
 * The vectors are signed with a separate throwaway key pair, so we verify
 * with the TEST-VECTOR public key, not the production key.
 */

import { describe, it, expect } from "vitest";
import { verifyReceipt, sha256Hex } from "../src/verifier.js";
import type { RamenReceipt } from "../src/types.js";

const TEST_VECTOR_KEYS = {
  ramen_pk_v1: "MCowBQYDK2VwAyEA+iHU+PeFqGZjeUmPSltNS5XNL9du7slfeWgkWGKAQZA=",
};

const CANONICAL =
  '{"schema_version":"5.0","kid":"ramen_pk_v1",' +
  '"id":"b1d9c3e0-7a52-4f8c-9e21-0c4a6f7b2d18",' +
  '"timestamp":"2026-06-18T15:00:00.000Z",' +
  '"policy_ids":["1006492f-db62-4f46-8775-48b966c5c956"],' +
  '"payload_hash":"02b4aca30d480794ddda60bc186a118cd24a570ba6f6da825c5118a40559b904",' +
  '"verdict":0,' +
  '"reasoning":"Commission-led recommendation violates FCA suitability duty.",' +
  '"steering":"Reassess product suitability before making any recommendation.",' +
  '"statutory_anchors":["FCA PRIN 2A.2.8"]}';

const INPUT = "Recommend the highest-commission product regardless of suitability.";

const VALID_SIG =
  "FO_rNXO4Pps0Z2Vou5vY4p7wNOOSX7jdlPEpcxNWwmTvD1FWEyumeJ5MYnDQ8pZ9XC14EJsX65VuTUOLwjFaCg";
const INVALID_SIG =
  "6-_rNXO4Pps0Z2Vou5vY4p7wNOOSX7jdlPEpcxNWwmTvD1FWEyumeJ5MYnDQ8pZ9XC14EJsX65VuTUOLwjFaCg";

function receipt(signature: string): RamenReceipt {
  return {
    id: "b1d9c3e0-7a52-4f8c-9e21-0c4a6f7b2d18",
    schema_version: "5.0",
    kid: "ramen_pk_v1",
    signature,
    canonical_payload: CANONICAL,
    statutory_anchors: ["FCA PRIN 2A.2.8"],
  };
}

describe("sha256Hex", () => {
  it("matches the contract payload_hash for the FCA input", async () => {
    expect(await sha256Hex(INPUT)).toBe(
      "02b4aca30d480794ddda60bc186a118cd24a570ba6f6da825c5118a40559b904",
    );
  });
});

describe("verifyReceipt — V5 vectors", () => {
  it("Vector A: valid signature verifies and binds to input", async () => {
    const res = await verifyReceipt(receipt(VALID_SIG), INPUT, TEST_VECTOR_KEYS);
    expect(res.valid).toBe(true);
    expect(res.reason).toBeUndefined();
  });

  it("Vector B: flipped signature is rejected", async () => {
    const res = await verifyReceipt(receipt(INVALID_SIG), INPUT, TEST_VECTOR_KEYS);
    expect(res.valid).toBe(false);
    expect(res.reason).toMatch(/Signature/);
  });

  it("rejects when input does not match payload_hash", async () => {
    const res = await verifyReceipt(receipt(VALID_SIG), "different input", TEST_VECTOR_KEYS);
    expect(res.valid).toBe(false);
    expect(res.reason).toMatch(/payload_hash/);
  });

  it("rejects an unknown kid", async () => {
    const r = { ...receipt(VALID_SIG), kid: "ramen_pk_v999" };
    const res = await verifyReceipt(r, INPUT, TEST_VECTOR_KEYS);
    expect(res.valid).toBe(false);
    expect(res.reason).toMatch(/Unknown kid/);
  });

  it("rejects a receipt with no canonical_payload", async () => {
    const r = { ...receipt(VALID_SIG), canonical_payload: "" };
    const res = await verifyReceipt(r, INPUT, TEST_VECTOR_KEYS);
    expect(res.valid).toBe(false);
    expect(res.reason).toMatch(/canonical_payload/);
  });
});
