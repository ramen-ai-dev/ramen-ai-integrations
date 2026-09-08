# @ramen-ai/attestation-spec

Vendor-neutral TypeScript contracts for collecting and verifying hardware or platform attestation evidence.

## Challenge derivation

`deriveAttestationChallenge` computes:

```text
SHA256("ramen-evidence-v1" || canonical(requestId, inputHash, policyScopeHash, expiry))
```

Each field is normalized to Unicode NFC, encoded as UTF-8, and prefixed with its decimal UTF-8 byte length plus `:`. The encoded fields are concatenated in this fixed order with no separators:

```text
byteLength(requestId):requestId
byteLength(inputHash):inputHash
byteLength(policyScopeHash):policyScopeHash
byteLength(expiry):expiry
```

For example, `req-123` begins `7:req-123`. Length prefixes make boundaries unambiguous without relying on language-specific JSON escaping. The final digest is returned as lowercase hexadecimal.

## Adapter roles

- `AttestationCollector` gathers a quote or evidence token in the client workload.
- `AttestationVerifier` validates evidence in a server or Evidence Notary.
- `MockPassThroughAdapter` implements both interfaces for tests only. It provides no hardware security.

Vendor adapters remain responsible for certificate chains, endorsements, freshness, TCB status, measurements, revocation, and policy enforcement.
