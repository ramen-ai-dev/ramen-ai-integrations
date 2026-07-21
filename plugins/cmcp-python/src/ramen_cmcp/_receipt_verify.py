"""_receipt_verify — standalone V5 Ed25519 receipt verifier.

Normative algorithm (alane-v5-conformance.md §4.3):

    Step 1 — Signature
        publicKey  = AUDIT_PUBLIC_KEYS[receipt.kid]   # fail if kid unknown
        valid_sig  = Ed25519.verify(publicKey,
                                    base64url_decode(receipt.signature),
                                    UTF8(receipt.canonical_payload))

    Step 2 — Input binding
        payload       = JSON.parse(receipt.canonical_payload)
        assert payload.schema_version == "5.0"
        expected_hash = SHA256_hex(UTF8(original_input_string))
        valid_bind    = (payload.payload_hash == expected_hash)

    valid = valid_sig AND valid_bind

Key registry
────────────
The production key (ramen_pk_v1) and the ephemeral document-build key
(ramen_pk_ephemeral_test) are embedded here.  Both are SPKI DER base64.

    ramen_pk_v1             — active production key
    ramen_pk_ephemeral_test — conformance-doc vectors only (§3.2)

An unknown kid always returns (False, "Unknown kid: <value>").
"""

from __future__ import annotations

import base64
import hashlib
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.hazmat.primitives import serialization

# SPKI DER base64 — sourced from alane-v5-conformance.md §3
_AUDIT_PUBLIC_KEYS: dict[str, str] = {
    "ramen_pk_v1": "MCowBQYDK2VwAyEA8iTL9lJGYn2alGn1yMWVAIqLImTpADb9CqaLhisTuto=",
    "ramen_pk_ephemeral_test": "MCowBQYDK2VwAyEACmDytPXlfjKUMgV5l4w31xHt/G5p30UsNm/AmOI9OaM=",
}


def verify_v5_receipt(
    receipt: dict,
    original_input: str,
    *,
    extra_keys: dict[str, str] | None = None,
) -> tuple[bool, str | None]:
    """Verify a ramen-ai V5 receipt.

    Performs both verification steps from alane-v5-conformance.md §4.3:
    Ed25519 signature over ``canonical_payload``, and SHA-256 input binding.

    Args:
        receipt:
            The ``data.receipt`` sub-object.  Must contain ``kid``,
            ``signature`` (base64url, no padding), and ``canonical_payload``
            (raw JSON string — verified as-is, not reconstructed).
        original_input:
            The exact UTF-8 string that was submitted to the evaluation API.
            Used to re-derive ``payload_hash`` for input-binding verification.
        extra_keys:
            Optional additional SPKI DER base64 keys keyed by ``kid``.
            Merged with the built-in registry; caller-supplied keys take
            precedence.

    Returns:
        ``(True, None)`` on success.
        ``(False, reason: str)`` on any failure.  Never raises.
    """
    try:
        return _verify(receipt, original_input, extra_keys or {})
    except Exception as exc:  # pragma: no cover — unexpected internal error
        return False, f"Unexpected verifier error: {exc}"


# ── internal ──────────────────────────────────────────────────────────────────

def _verify(
    receipt: dict,
    original_input: str,
    extra_keys: dict[str, str],
) -> tuple[bool, str | None]:
    kid: str = receipt.get("kid", "")
    signature_b64url: str = receipt.get("signature", "")
    canonical_payload: str = receipt.get("canonical_payload", "")

    # ── Step 1: Ed25519 signature ──────────────────────────────────────────
    key_registry = {**_AUDIT_PUBLIC_KEYS, **extra_keys}
    if kid not in key_registry:
        return False, f"Unknown kid: {kid!r}"

    pub_key = _load_spki_key(key_registry[kid])

    sig_bytes = _b64url_decode(signature_b64url)
    try:
        pub_key.verify(sig_bytes, canonical_payload.encode("utf-8"))
    except InvalidSignature:
        return False, "Signature does not verify over canonical_payload"

    # ── Step 2: input binding (SHA-256) ───────────────────────────────────
    try:
        payload = json.loads(canonical_payload)
    except json.JSONDecodeError as exc:
        return False, f"canonical_payload is not valid JSON: {exc}"

    if payload.get("schema_version") != "5.0":
        return False, (
            f"Unexpected schema_version {payload.get('schema_version')!r}; expected '5.0'"
        )

    expected_hash = hashlib.sha256(original_input.encode("utf-8")).hexdigest()
    if payload.get("payload_hash") != expected_hash:
        return False, (
            "payload_hash does not match SHA-256 of the provided input"
        )

    return True, None


def _load_spki_key(spki_b64: str) -> Ed25519PublicKey:
    der = base64.b64decode(spki_b64)
    key = serialization.load_der_public_key(der)
    if not isinstance(key, Ed25519PublicKey):
        raise TypeError(f"Expected Ed25519PublicKey, got {type(key)}")
    return key


def _b64url_decode(s: str) -> bytes:
    """Decode a base64url string, with or without padding."""
    padded = s.replace("-", "+").replace("_", "/")
    padding = 4 - len(padded) % 4
    if padding != 4:
        padded += "=" * padding
    return base64.b64decode(padded)
