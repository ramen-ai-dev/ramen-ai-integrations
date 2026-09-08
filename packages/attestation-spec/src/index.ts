export const ATTESTATION_CHALLENGE_DOMAIN = "ramen-evidence-v1" as const;

export interface AttestationPayload {
  vendor: string;
  evidence: string;
  challenge?: string;
  metadata?: Record<string, unknown>;
}

export interface AttestationChallengeInput {
  requestId: string;
  inputHash: string;
  policyScopeHash: string;
  expiry: string;
}

export interface AttestationCollectionRequest {
  challenge: string;
  context?: Record<string, unknown>;
}

export interface AttestationVerificationRequest {
  attestation: AttestationPayload;
  expectedChallenge: string;
}

export interface AttestationVerificationResult {
  verified: boolean;
  vendor: string;
  claims?: Record<string, unknown>;
  reason?: string;
}

/** Client-side adapter for collecting a vendor quote or evidence token. */
export interface AttestationCollector {
  collect(
    request: Readonly<AttestationCollectionRequest>,
  ): Promise<AttestationPayload>;
}

/** Server/notary-side adapter for verifying vendor evidence. */
export interface AttestationVerifier {
  verify(
    request: Readonly<AttestationVerificationRequest>,
  ): Promise<AttestationVerificationResult>;
}

/** Encode one challenge field as NFC-normalized UTF-8 byte-length:value. */
function canonicalizeField(value: string): string {
  const normalized = value.normalize("NFC");
  const encoded = new TextEncoder().encode(normalized);
  if (new TextDecoder().decode(encoded) !== normalized) {
    throw new Error("Attestation challenge fields must contain valid Unicode");
  }
  return `${encoded.byteLength}:${normalized}`;
}

/**
 * Canonical challenge fields as NFC-normalized, length-prefixed UTF-8 values.
 * Fields are concatenated in requestId, inputHash, policyScopeHash, expiry
 * order. Byte lengths make the representation unambiguous without relying on
 * language-specific JSON escaping.
 */
export function canonicalizeAttestationChallenge(
  input: Readonly<AttestationChallengeInput>,
): string {
  return [
    input.requestId,
    input.inputHash,
    input.policyScopeHash,
    input.expiry,
  ]
    .map(canonicalizeField)
    .join("");
}

/**
 * Derive SHA-256("ramen-evidence-v1" || canonical challenge fields).
 * The returned challenge is lowercase hexadecimal.
 */
export async function deriveAttestationChallenge(
  input: Readonly<AttestationChallengeInput>,
): Promise<string> {
  const value = `${ATTESTATION_CHALLENGE_DOMAIN}${canonicalizeAttestationChallenge(input)}`;
  const encoded = new TextEncoder().encode(value);
  const bytes = new ArrayBuffer(encoded.byteLength);
  new Uint8Array(bytes).set(encoded);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * Deterministic non-production adapter used to exercise collector/verifier
 * composition without coupling tests to a TEE vendor.
 */
export class MockPassThroughAdapter
  implements AttestationCollector, AttestationVerifier
{
  readonly vendor: string;

  constructor(vendor = "mock") {
    if (!vendor) throw new Error("MockPassThroughAdapter requires a vendor");
    this.vendor = vendor;
  }

  async collect(
    request: Readonly<AttestationCollectionRequest>,
  ): Promise<AttestationPayload> {
    if (!request.challenge) throw new Error("Attestation challenge is required");
    return {
      vendor: this.vendor,
      evidence: `mock:${request.challenge}`,
      challenge: request.challenge,
      ...(request.context === undefined ? {} : { metadata: request.context }),
    };
  }

  async verify(
    request: Readonly<AttestationVerificationRequest>,
  ): Promise<AttestationVerificationResult> {
    const { attestation, expectedChallenge } = request;
    if (attestation.vendor !== this.vendor) {
      return {
        verified: false,
        vendor: attestation.vendor,
        reason: `Unexpected vendor: ${attestation.vendor}`,
      };
    }
    if (!expectedChallenge || attestation.challenge !== expectedChallenge) {
      return {
        verified: false,
        vendor: attestation.vendor,
        reason: "Attestation challenge does not match",
      };
    }
    if (attestation.evidence !== `mock:${expectedChallenge}`) {
      return {
        verified: false,
        vendor: attestation.vendor,
        reason: "Mock evidence does not match the challenge",
      };
    }
    return {
      verified: true,
      vendor: attestation.vendor,
    };
  }
}
