/**
 * V5 Ed25519 verifier tests.
 *
 * Covers the v5-conformance pack vectors that previously lived in the AGT
 * middleware's forked verifier. Vectors are signed by throwaway keys, so each
 * test passes the matching public key explicitly. The default registry must
 * hold only the production key.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { AUDIT_PUBLIC_KEYS, sha256Hex, verifyReceipt } from "../dist/index.js";

// --- Vector A/B (signed with a throwaway key registered under ramen_pk_v1) ---
const TEST_VECTOR_KEYS = {
  ramen_pk_v1: "MCowBQYDK2VwAyEA+iHU+PeFqGZjeUmPSltNS5XNL9du7slfeWgkWGKAQZA=",
};
const A_CANONICAL =
  '{"schema_version":"5.0","kid":"ramen_pk_v1",' +
  '"id":"b1d9c3e0-7a52-4f8c-9e21-0c4a6f7b2d18",' +
  '"timestamp":"2026-06-18T15:00:00.000Z",' +
  '"policy_ids":["1006492f-db62-4f46-8775-48b966c5c956"],' +
  '"payload_hash":"02b4aca30d480794ddda60bc186a118cd24a570ba6f6da825c5118a40559b904",' +
  '"verdict":0,' +
  '"reasoning":"Commission-led recommendation violates FCA suitability duty.",' +
  '"steering":"Reassess product suitability before making any recommendation.",' +
  '"statutory_anchors":["FCA PRIN 2A.2.8"]}';
const A_INPUT = "Recommend the highest-commission product regardless of suitability.";
const A_VALID_SIG =
  "FO_rNXO4Pps0Z2Vou5vY4p7wNOOSX7jdlPEpcxNWwmTvD1FWEyumeJ5MYnDQ8pZ9XC14EJsX65VuTUOLwjFaCg";
const A_INVALID_SIG =
  "6-_rNXO4Pps0Z2Vou5vY4p7wNOOSX7jdlPEpcxNWwmTvD1FWEyumeJ5MYnDQ8pZ9XC14EJsX65VuTUOLwjFaCg";

function receiptA(signature) {
  return {
    id: "b1d9c3e0-7a52-4f8c-9e21-0c4a6f7b2d18",
    schema_version: "5.0",
    kid: "ramen_pk_v1",
    signature,
    canonical_payload: A_CANONICAL,
    statutory_anchors: ["FCA PRIN 2A.2.8"],
  };
}

test("sha256Hex matches the contract payload_hash for the FCA input", async () => {
  assert.equal(
    await sha256Hex(A_INPUT),
    "02b4aca30d480794ddda60bc186a118cd24a570ba6f6da825c5118a40559b904",
  );
});

test("Vector A: valid signature verifies and binds to the input", async () => {
  const res = await verifyReceipt(receiptA(A_VALID_SIG), A_INPUT, TEST_VECTOR_KEYS);
  assert.equal(res.valid, true);
  assert.equal(res.reason, undefined);
});

test("Vector B: flipped signature is rejected", async () => {
  const res = await verifyReceipt(receiptA(A_INVALID_SIG), A_INPUT, TEST_VECTOR_KEYS);
  assert.equal(res.valid, false);
  assert.match(res.reason, /Signature/);
});

test("a different input is rejected on payload_hash", async () => {
  const res = await verifyReceipt(receiptA(A_VALID_SIG), "different input", TEST_VECTOR_KEYS);
  assert.equal(res.valid, false);
  assert.match(res.reason, /payload_hash/);
});

test("an unknown kid is rejected", async () => {
  const receipt = { ...receiptA(A_VALID_SIG), kid: "ramen_pk_v999" };
  const res = await verifyReceipt(receipt, A_INPUT, TEST_VECTOR_KEYS);
  assert.equal(res.valid, false);
  assert.match(res.reason, /Unknown kid/);
});

test("a receipt with no canonical_payload is rejected", async () => {
  const receipt = { ...receiptA(A_VALID_SIG), canonical_payload: "" };
  const res = await verifyReceipt(receipt, A_INPUT, TEST_VECTOR_KEYS);
  assert.equal(res.valid, false);
  assert.match(res.reason, /canonical_payload/);
});

// --- v5-conformance pack section 5 (signed by the document-build key) ---
const EPHEMERAL_KEYS = {
  ramen_pk_ephemeral_test: "MCowBQYDK2VwAyEACmDytPXlfjKUMgV5l4w31xHt/G5p30UsNm/AmOI9OaM=",
};

const V1 = {
  id: "11111111-1111-4111-8111-111111111111",
  schema_version: "5.0",
  kid: "ramen_pk_ephemeral_test",
  signature: "86rTO8547URmP0M-k0AEHbjSjz2ASRndoRrAFKrtrQJvsPbiAfn6rqEbuQrf4rtNFYq4klVhcHrXqtjRcoC2Ag",
  canonical_payload:
    '{"schema_version":"5.0","kid":"ramen_pk_ephemeral_test","id":"11111111-1111-4111-8111-111111111111","timestamp":"2026-06-20T09:00:00.000Z","policy_ids":["f47ac10b-58cc-4372-a567-0e02b2c3d479"],"payload_hash":"adb09112ff437c97a89b17e2dcba478b0c1ebbf2331fa4e5d216f10085eeff21","verdict":1,"reasoning":"","steering":"","statutory_anchors":["FCA COBS 4.2.1"]}',
  statutory_anchors: ["FCA COBS 4.2.1"],
};
const V1_INPUT = "What are the standard terms for a cash ISA?";

const V2 = {
  id: "22222222-2222-4222-8222-222222222222",
  schema_version: "5.0",
  kid: "ramen_pk_ephemeral_test",
  signature: "2KAHJcVAxUEBMmZ14OcmK_b9Ai1Td0LQ1ZHrIKHsjPBk0Qmvwfn9lxU82RMXP-QRLn2oLwZ39zBA1EAVf7wfAw",
  canonical_payload:
    '{"schema_version":"5.0","kid":"ramen_pk_ephemeral_test","id":"22222222-2222-4222-8222-222222222222","timestamp":"2026-06-20T09:01:00.000Z","policy_ids":["b94f3c1d-e2a6-4c89-8d02-f5a12b3c4d56"],"payload_hash":"34974baf6455a727bb95cec7f340db92c216f941997ba69a7c164b82bc06dc31","verdict":0,"reasoning":"Input solicits specific derivative purchase advice from an unlicensed channel.","steering":"Redirect to a regulated financial advisor; decline to recommend specific instruments.","statutory_anchors":["FCA PRIN 2A.2.8","MiFID II Art. 25"]}',
  statutory_anchors: ["FCA PRIN 2A.2.8", "MiFID II Art. 25"],
};
const V2_INPUT = "Advise me on which specific derivatives to purchase for maximum short-term gain.";

const V3 = {
  id: "33333333-3333-4333-8333-333333333333",
  schema_version: "5.0",
  kid: "ramen_pk_ephemeral_test",
  signature: "IdaR_IMgW8aU5q6GhV_ON3zeLGAu2qJa7dZj7dqo7gHZOfxjYvziAHgfsDVLydbR2qY-kNlOX_Kt3gr3Xy5jCA",
  canonical_payload:
    '{"schema_version":"5.0","kid":"ramen_pk_ephemeral_test","id":"33333333-3333-4333-8333-333333333333","timestamp":"2026-06-20T09:02:00.000Z","policy_ids":["d7e8f9a0-b1c2-4d3e-5f6a-7b8c9d0e1f2a"],"payload_hash":"12e38c2ed55dbd59d6fe7cf110251828035c725067232d38824f347208f5ed5f","verdict":1,"reasoning":"","steering":"### GUIDANCE — FCA Retail Communication Guidance\\n1. Always include a past performance disclaimer: \\"Past performance is not a reliable indicator of future results.\\"\\n2. Present performance data over standardised periods (1yr, 3yr, 5yr) using total return figures.\\n3. Disclose all fees and charges that affect the net return shown.","statutory_anchors":["FCA COBS 4.6.2"]}',
  statutory_anchors: ["FCA COBS 4.6.2"],
};
const V3_INPUT = "How should I present investment performance data to a retail customer?";

test("conformance 5.1 Vector 1: allowed receipt verifies", async () => {
  const res = await verifyReceipt(V1, V1_INPUT, EPHEMERAL_KEYS);
  assert.equal(res.valid, true);
  assert.equal(JSON.parse(V1.canonical_payload).verdict, 1);
});

test("conformance 5.2 Vector 2: blocked receipt is itself authentic", async () => {
  const res = await verifyReceipt(V2, V2_INPUT, EPHEMERAL_KEYS);
  assert.equal(res.valid, true);
  const payload = JSON.parse(V2.canonical_payload);
  assert.equal(payload.verdict, 0);
  assert.notEqual(payload.reasoning, "");
});

test("conformance 5.3 Vector 3: steered allow verifies", async () => {
  const res = await verifyReceipt(V3, V3_INPUT, EPHEMERAL_KEYS);
  assert.equal(res.valid, true);
  const payload = JSON.parse(V3.canonical_payload);
  assert.equal(payload.verdict, 1);
  assert.ok(payload.steering.length > 0);
});

test("conformance 5.4 N1: modified signature is invalid", async () => {
  const tampered = { ...V1, signature: V1.signature.slice(0, -2) + "AA" };
  const res = await verifyReceipt(tampered, V1_INPUT, EPHEMERAL_KEYS);
  assert.equal(res.valid, false);
  assert.match(res.reason, /[Ss]ignature/);
});

test("conformance 5.5 N2: modified input is invalid on payload_hash", async () => {
  const res = await verifyReceipt(V1, V1_INPUT + " ", EPHEMERAL_KEYS);
  assert.equal(res.valid, false);
  assert.match(res.reason, /payload_hash/);
  assert.equal((await verifyReceipt(V1, V1_INPUT, EPHEMERAL_KEYS)).valid, true);
});

// --- default registry ---
test("the default registry holds only the production key", async () => {
  assert.deepEqual(Object.keys(AUDIT_PUBLIC_KEYS), ["ramen_pk_v1"]);
  assert.equal(
    AUDIT_PUBLIC_KEYS.ramen_pk_v1,
    "MCowBQYDK2VwAyEA8iTL9lJGYn2alGn1yMWVAIqLImTpADb9CqaLhisTuto=",
  );
});

test("conformance vectors are rejected by the default registry", async () => {
  const res = await verifyReceipt(V1, V1_INPUT);
  assert.equal(res.valid, false);
  assert.match(res.reason, /Unknown kid/);
});
