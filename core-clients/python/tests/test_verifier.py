"""
tests/test_verifier.py — V5 Ed25519 test vectors for ramen_ai.verifier.

Test vectors are sourced verbatim from:
  _ref/ramen-ai-backend/docs/integration/v5-conformance-pack.md  (§ 3. Test vectors)

IMPORTANT: these vectors were signed with a SEPARATE, throwaway key pair.
Use TEST_VECTOR_PUBLIC_KEYS (not the production AUDIT_PUBLIC_KEYS) by passing
the ``_public_keys`` override to verify_receipt().

Test-vector public key (base64 SPKI DER):
  MCowBQYDK2VwAyEA+iHU+PeFqGZjeUmPSltNS5XNL9du7slfeWgkWGKAQZA=
"""

import hashlib
import pytest

from ramen_ai.verifier import verify_receipt, sha256_hex

# ---------------------------------------------------------------------------
# Test-vector key map — overrides production keys for offline verification.
# ---------------------------------------------------------------------------
TEST_VECTOR_PUBLIC_KEYS: dict[str, str] = {
    "ramen_pk_v1": "MCowBQYDK2VwAyEA+iHU+PeFqGZjeUmPSltNS5XNL9du7slfeWgkWGKAQZA=",
}

# ---------------------------------------------------------------------------
# Vector A — sourced from v5-conformance-pack.md § 3. Test vectors (Schema V5)
# ---------------------------------------------------------------------------
VECTOR_A_CANONICAL_PAYLOAD = (
    '{"schema_version":"5.0","kid":"ramen_pk_v1",'
    '"id":"b1d9c3e0-7a52-4f8c-9e21-0c4a6f7b2d18",'
    '"timestamp":"2026-06-18T15:00:00.000Z",'
    '"policy_ids":["1006492f-db62-4f46-8775-48b966c5c956"],'
    '"payload_hash":"02b4aca30d480794ddda60bc186a118cd24a570ba6f6da825c5118a40559b904",'
    '"verdict":0,'
    '"reasoning":"Commission-led recommendation violates FCA suitability duty.",'
    '"steering":"Reassess product suitability before making any recommendation.",'
    '"statutory_anchors":["FCA PRIN 2A.2.8"]}'
)

VECTOR_A_INPUT = "Recommend the highest-commission product regardless of suitability."

VECTOR_A_VALID_SIG = (
    "FO_rNXO4Pps0Z2Vou5vY4p7wNOOSX7jdlPEpcxNWwmTvD1FWEyumeJ5MYnDQ8pZ9XC14EJsX65VuTUOLwjFaCg"
)

# Vector B — identical payload, first byte of signature flipped.
VECTOR_B_INVALID_SIG = (
    "6-_rNXO4Pps0Z2Vou5vY4p7wNOOSX7jdlPEpcxNWwmTvD1FWEyumeJ5MYnDQ8pZ9XC14EJsX65VuTUOLwjFaCg"
)

# Common receipt fields for Vector A.
_RECEIPT_BASE = {
    "id": "b1d9c3e0-7a52-4f8c-9e21-0c4a6f7b2d18",
    "schema_version": "5.0",
    "kid": "ramen_pk_v1",
    "canonical_payload": VECTOR_A_CANONICAL_PAYLOAD,
    "statutory_anchors": ["FCA PRIN 2A.2.8"],
}

# Common response-level fields for all Vector-A calls.
_COMMON_KWARGS = dict(
    executed_at="2026-06-18T15:00:00.000Z",
    policy_ids=["1006492f-db62-4f46-8775-48b966c5c956"],
    input_text=VECTOR_A_INPUT,
    allowed=False,
    violations=[
        {
            "reasoning": "Commission-led recommendation violates FCA suitability duty.",
            "recovery_instruction": "Reassess product suitability before making any recommendation.",
        }
    ],
    statutory_anchors=["FCA PRIN 2A.2.8"],
    _public_keys=TEST_VECTOR_PUBLIC_KEYS,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _receipt(sig: str) -> dict:
    return {**_RECEIPT_BASE, "signature": sig}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSha256Hex:
    """Unit tests for the internal SHA-256 helper."""

    def test_known_hash(self) -> None:
        """SHA-256 of the FCA test input must match the value in the contract."""
        expected = "02b4aca30d480794ddda60bc186a118cd24a570ba6f6da825c5118a40559b904"
        assert sha256_hex(VECTOR_A_INPUT) == expected

    def test_empty_string(self) -> None:
        expected = hashlib.sha256(b"").hexdigest()
        assert sha256_hex("") == expected


class TestVerifyReceiptVectorA:
    """Schema V5 verification against the contract test vector."""

    def test_valid_signature_returns_true(self) -> None:
        """Vector A with valid signature must return (True, None)."""
        valid, reason = verify_receipt(_receipt(VECTOR_A_VALID_SIG), **_COMMON_KWARGS)
        assert valid is True
        assert reason is None

    def test_invalid_signature_returns_false(self) -> None:
        """Vector B (first byte flipped) must return (False, <reason>)."""
        valid, reason = verify_receipt(_receipt(VECTOR_B_INVALID_SIG), **_COMMON_KWARGS)
        assert valid is False
        assert reason is not None
        assert "Signature" in reason or "verify" in reason.lower()

    def test_wrong_input_hash_mismatch(self) -> None:
        """A valid signature over a different input must fail the hash binding check."""
        kwargs = {**_COMMON_KWARGS, "input_text": "This is not the original input."}
        valid, reason = verify_receipt(_receipt(VECTOR_A_VALID_SIG), **kwargs)
        assert valid is False
        assert reason is not None
        assert "payload_hash" in reason

    def test_verdict_mismatch_detected(self) -> None:
        """Claiming allowed=True when the receipt says verdict=0 must fail."""
        kwargs = {**_COMMON_KWARGS, "allowed": True}
        valid, reason = verify_receipt(_receipt(VECTOR_A_VALID_SIG), **kwargs)
        assert valid is False
        assert reason is not None
        assert "Verdict" in reason or "verdict" in reason.lower()

    def test_timestamp_mismatch_detected(self) -> None:
        """A tampered executed_at must fail the timestamp cross-check."""
        kwargs = {**_COMMON_KWARGS, "executed_at": "2099-01-01T00:00:00.000Z"}
        valid, reason = verify_receipt(_receipt(VECTOR_A_VALID_SIG), **kwargs)
        assert valid is False
        assert reason is not None
        assert "Timestamp" in reason or "timestamp" in reason.lower()

    def test_policy_ids_mismatch_detected(self) -> None:
        """A tampered policy_ids list must fail the cross-check."""
        kwargs = {**_COMMON_KWARGS, "policy_ids": ["00000000-0000-0000-0000-000000000000"]}
        valid, reason = verify_receipt(_receipt(VECTOR_A_VALID_SIG), **kwargs)
        assert valid is False
        assert reason is not None
        assert "policy_ids" in reason

    def test_statutory_anchors_mismatch_detected(self) -> None:
        """Tampered statutory_anchors must fail the cross-check."""
        kwargs = {**_COMMON_KWARGS, "statutory_anchors": ["GDPR Art. 99"]}
        valid, reason = verify_receipt(_receipt(VECTOR_A_VALID_SIG), **kwargs)
        assert valid is False
        assert reason is not None
        assert "statutory_anchors" in reason


class TestVerifyReceiptGuardRails:
    """Guard-rail and edge-case tests independent of the test vector."""

    def test_missing_canonical_payload_returns_false(self) -> None:
        receipt = {**_RECEIPT_BASE, "signature": VECTOR_A_VALID_SIG}
        del receipt["canonical_payload"]
        valid, reason = verify_receipt(receipt, **_COMMON_KWARGS)
        assert valid is False
        assert "canonical_payload" in (reason or "").lower() or "V5" in (reason or "")

    def test_missing_kid_returns_false(self) -> None:
        receipt = {**_RECEIPT_BASE, "signature": VECTOR_A_VALID_SIG}
        del receipt["kid"]
        valid, reason = verify_receipt(receipt, **_COMMON_KWARGS)
        assert valid is False
        assert "kid" in (reason or "").lower()

    def test_unknown_kid_returns_false(self) -> None:
        receipt = {**_RECEIPT_BASE, "signature": VECTOR_A_VALID_SIG, "kid": "ramen_pk_v999"}
        valid, reason = verify_receipt(receipt, **_COMMON_KWARGS)
        assert valid is False
        assert "Unknown kid" in (reason or "")

    def test_missing_signature_returns_false(self) -> None:
        receipt = {**_RECEIPT_BASE}  # no 'signature' key
        valid, reason = verify_receipt(receipt, **_COMMON_KWARGS)
        assert valid is False
        assert "signature" in (reason or "").lower()
