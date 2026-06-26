/**
 * V5 cryptographic conformance suite.
 *
 * Vectors are taken verbatim from the normative conformance pack:
 *   _ref/ramen-ai-backend/docs/integration/alane-v5-conformance.md  (§5)
 *
 * They are signed by the document-build EPHEMERAL key `ramen_pk_ephemeral_test`
 * (§3.2) — NOT the production key `ramen_pk_v1`. A conforming verifier MUST
 * reproduce the documented `valid` outcome for every vector.
 */

import { describe, it, expect } from "vitest";
import { verifyReceipt } from "../src/verifier.js";
import type { RamenReceipt } from "../src/types.js";

/** §3.2 ephemeral public key (base64 SPKI DER) — for these vectors only. */
const EPHEMERAL_KEYS = {
  ramen_pk_ephemeral_test: "MCowBQYDK2VwAyEACmDytPXlfjKUMgV5l4w31xHt/G5p30UsNm/AmOI9OaM=",
};

// ── §5.1 Vector 1 — Allowed (verdict 1) → VALID ──────────────────────────────
const V1: RamenReceipt = {
  id: "11111111-1111-4111-8111-111111111111",
  schema_version: "5.0",
  kid: "ramen_pk_ephemeral_test",
  signature: "86rTO8547URmP0M-k0AEHbjSjz2ASRndoRrAFKrtrQJvsPbiAfn6rqEbuQrf4rtNFYq4klVhcHrXqtjRcoC2Ag",
  canonical_payload:
    '{"schema_version":"5.0","kid":"ramen_pk_ephemeral_test","id":"11111111-1111-4111-8111-111111111111","timestamp":"2026-06-20T09:00:00.000Z","policy_ids":["f47ac10b-58cc-4372-a567-0e02b2c3d479"],"payload_hash":"adb09112ff437c97a89b17e2dcba478b0c1ebbf2331fa4e5d216f10085eeff21","verdict":1,"reasoning":"","steering":"","statutory_anchors":["FCA COBS 4.2.1"]}',
  statutory_anchors: ["FCA COBS 4.2.1"],
};
const V1_INPUT = "What are the standard terms for a cash ISA?";

// ── §5.2 Vector 2 — Blocked (verdict 0) → VALID receipt ──────────────────────
const V2: RamenReceipt = {
  id: "22222222-2222-4222-8222-222222222222",
  schema_version: "5.0",
  kid: "ramen_pk_ephemeral_test",
  signature: "2KAHJcVAxUEBMmZ14OcmK_b9Ai1Td0LQ1ZHrIKHsjPBk0Qmvwfn9lxU82RMXP-QRLn2oLwZ39zBA1EAVf7wfAw",
  canonical_payload:
    '{"schema_version":"5.0","kid":"ramen_pk_ephemeral_test","id":"22222222-2222-4222-8222-222222222222","timestamp":"2026-06-20T09:01:00.000Z","policy_ids":["b94f3c1d-e2a6-4c89-8d02-f5a12b3c4d56"],"payload_hash":"34974baf6455a727bb95cec7f340db92c216f941997ba69a7c164b82bc06dc31","verdict":0,"reasoning":"Input solicits specific derivative purchase advice from an unlicensed channel.","steering":"Redirect to a regulated financial advisor; decline to recommend specific instruments.","statutory_anchors":["FCA PRIN 2A.2.8","MiFID II Art. 25"]}',
  statutory_anchors: ["FCA PRIN 2A.2.8", "MiFID II Art. 25"],
};
const V2_INPUT = "Advise me on which specific derivatives to purchase for maximum short-term gain.";

// ── §5.3 Vector 3 — Steered allow (verdict 1, gentle_hand) → VALID ───────────
const V3: RamenReceipt = {
  id: "33333333-3333-4333-8333-333333333333",
  schema_version: "5.0",
  kid: "ramen_pk_ephemeral_test",
  signature: "IdaR_IMgW8aU5q6GhV_ON3zeLGAu2qJa7dZj7dqo7gHZOfxjYvziAHgfsDVLydbR2qY-kNlOX_Kt3gr3Xy5jCA",
  canonical_payload:
    '{"schema_version":"5.0","kid":"ramen_pk_ephemeral_test","id":"33333333-3333-4333-8333-333333333333","timestamp":"2026-06-20T09:02:00.000Z","policy_ids":["d7e8f9a0-b1c2-4d3e-5f6a-7b8c9d0e1f2a"],"payload_hash":"12e38c2ed55dbd59d6fe7cf110251828035c725067232d38824f347208f5ed5f","verdict":1,"reasoning":"","steering":"### GUIDANCE — FCA Retail Communication Guidance\\n1. Always include a past performance disclaimer: \\"Past performance is not a reliable indicator of future results.\\"\\n2. Present performance data over standardised periods (1yr, 3yr, 5yr) using total return figures.\\n3. Disclose all fees and charges that affect the net return shown.","statutory_anchors":["FCA COBS 4.6.2"]}',
  statutory_anchors: ["FCA COBS 4.6.2"],
};
const V3_INPUT = "How should I present investment performance data to a retail customer?";

describe("V5 conformance (alane-v5-conformance §5)", () => {
  it("§5.1 Vector 1 — Allowed receipt verifies valid", async () => {
    const res = await verifyReceipt(V1, V1_INPUT, EPHEMERAL_KEYS);
    expect(res.valid).toBe(true);
    expect(JSON.parse(V1.canonical_payload).verdict).toBe(1);
  });

  it("§5.2 Vector 2 — Blocked receipt is itself authentic (valid)", async () => {
    const res = await verifyReceipt(V2, V2_INPUT, EPHEMERAL_KEYS);
    expect(res.valid).toBe(true);
    const payload = JSON.parse(V2.canonical_payload);
    expect(payload.verdict).toBe(0);
    expect(payload.reasoning).not.toBe("");
  });

  it("§5.3 Vector 3 — Steered allow (verdict 1, non-empty steering) verifies valid", async () => {
    const res = await verifyReceipt(V3, V3_INPUT, EPHEMERAL_KEYS);
    expect(res.valid).toBe(true);
    const payload = JSON.parse(V3.canonical_payload);
    // A non-empty steering with verdict 1 is a steered ALLOW, not a block.
    expect(payload.verdict).toBe(1);
    expect(payload.steering.length).toBeGreaterThan(0);
  });

  it("§5.4 Negative N1 — modified signature is INVALID (signature)", async () => {
    const tampered: RamenReceipt = {
      ...V1,
      signature: V1.signature.slice(0, -2) + "AA",
    };
    const res = await verifyReceipt(tampered, V1_INPUT, EPHEMERAL_KEYS);
    expect(res.valid).toBe(false);
    expect(res.reason).toMatch(/[Ss]ignature/);
  });

  it("§5.5 Negative N2 — modified input is INVALID (payload_hash)", async () => {
    // Authentic receipt, but verified against input with a trailing space.
    const res = await verifyReceipt(V1, V1_INPUT + " ", EPHEMERAL_KEYS);
    expect(res.valid).toBe(false);
    expect(res.reason).toMatch(/payload_hash/);
    // Control: the same receipt verifies against the ORIGINAL input.
    expect((await verifyReceipt(V1, V1_INPUT, EPHEMERAL_KEYS)).valid).toBe(true);
  });

  it("§3.1 production kid ramen_pk_v1 is embedded for live receipts", async () => {
    const { AUDIT_PUBLIC_KEYS } = await import("../src/verifier.js");
    expect(AUDIT_PUBLIC_KEYS.ramen_pk_v1).toBe(
      "MCowBQYDK2VwAyEA8iTL9lJGYn2alGn1yMWVAIqLImTpADb9CqaLhisTuto=",
    );
  });
});
