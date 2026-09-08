import assert from "node:assert/strict";
import test from "node:test";

import {
  MockPassThroughAdapter,
  canonicalizeAttestationChallenge,
  deriveAttestationChallenge,
} from "../dist/index.js";

const challengeInput = {
  requestId: "req-123",
  inputHash: "a".repeat(64),
  policyScopeHash: "b".repeat(64),
  expiry: "2026-08-12T12:00:00Z",
};

test("canonical challenge derivation matches the fixed vector", async () => {
  assert.equal(
    canonicalizeAttestationChallenge(challengeInput),
    `7:req-12364:${"a".repeat(64)}64:${"b".repeat(64)}20:2026-08-12T12:00:00Z`,
  );
  assert.equal(
    await deriveAttestationChallenge(challengeInput),
    "dd281e7d074cd81034bf0d874b5e14c832c9c2a7447f040fe3f8942a333ee870",
  );
});

test("canonical challenge normalizes Unicode and avoids JSON escaping variance", async () => {
  const unicodeInput = {
    requestId: "re\u0301q\"\\\n",
    inputHash: "hash-☃",
    policyScopeHash: "scope",
    expiry: "2026-08-12T12:00:00Z",
  };

  assert.equal(
    canonicalizeAttestationChallenge(unicodeInput),
    "7:réq\"\\\n8:hash-☃5:scope20:2026-08-12T12:00:00Z",
  );
  assert.equal(
    await deriveAttestationChallenge(unicodeInput),
    "a1053518975f5a3b276e05c0bcbaa0ba76de16d337fdfc394ff416cb742e89bd",
  );
});

test("mock adapter collects and verifies challenge-bound evidence", async () => {
  const adapter = new MockPassThroughAdapter("mock-tee");
  const challenge = await deriveAttestationChallenge(challengeInput);
  const attestation = await adapter.collect({
    challenge,
    context: { measurement: "test-image" },
  });

  assert.deepEqual(attestation, {
    vendor: "mock-tee",
    evidence: `mock:${challenge}`,
    challenge,
    metadata: { measurement: "test-image" },
  });
  assert.deepEqual(
    await adapter.verify({ attestation, expectedChallenge: challenge }),
    {
      verified: true,
      vendor: "mock-tee",
    },
  );
});

test("mock adapter rejects mismatched challenges", async () => {
  const adapter = new MockPassThroughAdapter();
  const attestation = await adapter.collect({ challenge: "expected" });

  assert.deepEqual(
    await adapter.verify({ attestation, expectedChallenge: "different" }),
    {
      verified: false,
      vendor: "mock",
      reason: "Attestation challenge does not match",
    },
  );
});

test("mock adapter rejects evidence and vendor tampering", async () => {
  const adapter = new MockPassThroughAdapter("mock-tee");
  const attestation = await adapter.collect({ challenge: "expected" });

  assert.deepEqual(
    await adapter.verify({
      attestation: { ...attestation, evidence: "tampered" },
      expectedChallenge: "expected",
    }),
    {
      verified: false,
      vendor: "mock-tee",
      reason: "Mock evidence does not match the challenge",
    },
  );
  assert.deepEqual(
    await adapter.verify({
      attestation: { ...attestation, vendor: "other-vendor" },
      expectedChallenge: "expected",
    }),
    {
      verified: false,
      vendor: "other-vendor",
      reason: "Unexpected vendor: other-vendor",
    },
  );
});