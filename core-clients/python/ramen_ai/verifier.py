"""
ramen_ai.verifier — Ed25519 receipt verification for Schema V5.

V5 simplification: the API returns the exact signed string as
``receipt.canonical_payload``.  Clients verify against it directly and
confirm ``payload_hash`` matches SHA-256 of the original input.  No
manual reconstruction of the canonical JSON is required.

Two-step verification
---------------------
1. Verify the Ed25519 signature over ``receipt['canonical_payload']``.
2. Parse the payload; recompute ``SHA-256(input_text)``; confirm it
   equals ``payload_hash``.

If both steps pass the receipt is authentic and cryptographically bound
to the exact input that was submitted.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.serialization import load_der_public_key

# ---------------------------------------------------------------------------
# Production public keys — keyed by ``kid`` (key-rotation safe).
# These are SPKI DER blobs encoded as standard base64.
# Safe to embed in client-side code per the API contract.
# ---------------------------------------------------------------------------
AUDIT_PUBLIC_KEYS: dict[str, str] = {
    "ramen_pk_v1": "MCowBQYDK2VwAyEA8iTL9lJGYn2alGn1yMWVAIqLImTpADb9CqaLhisTuto=",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _decode_base64url(value: str) -> bytes:
    """Decode a standard base64 or base64url string to bytes."""
    # Normalise base64url alphabet to standard base64.
    standard = value.replace("-", "+").replace("_", "/")
    # Re-add stripped padding.
    padding = (4 - len(standard) % 4) % 4
    standard += "=" * padding
    return base64.b64decode(standard)


def sha256_hex(text: str) -> str:
    """Return the hex-encoded SHA-256 digest of *text* encoded as UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def verify_receipt(
    receipt: dict[str, Any],
    executed_at: str,
    policy_ids: list[str],
    input_text: str,
    allowed: bool,
    violations: list[dict[str, Any]],
    statutory_anchors: list[str] | None,
    *,
    _public_keys: dict[str, str] | None = None,
) -> tuple[bool, str | None]:
    """
    Verify a Schema V5 evaluation receipt.

    Parameters
    ----------
    receipt:
        The ``receipt`` object returned by the evaluate endpoint.
        Must contain at minimum: ``kid``, ``signature``,
        ``canonical_payload`` (all present on every V5 receipt).
    executed_at:
        The ``executed_at`` ISO 8601 timestamp from the response root — used
        for optional binding cross-check against the parsed payload.
    policy_ids:
        The resolved ``policy_ids`` array from the response root — used for
        optional binding cross-check against the parsed payload.
    input_text:
        The raw input string that was submitted to the evaluate endpoint.
        Step 2 re-hashes this and compares it against ``payload_hash``.
    allowed:
        The ``allowed`` boolean from the response root — used for optional
        binding cross-check (``verdict`` field in the payload).
    violations:
        The ``total_violations`` list from the response root — accepted for
        API symmetry; cross-checks are performed against the canonical
        payload values, not re-derived from this list.
    statutory_anchors:
        The ``statutory_anchors`` list from the response root — accepted for
        API symmetry; cross-checked against the canonical payload.
    _public_keys:
        Override the production key map.  Pass a dict keyed by ``kid`` to
        use test-vector or rotated keys without touching the module constant.

    Returns
    -------
    ``(True, None)`` if the receipt is valid and fully bound to
    ``input_text``.  ``(False, reason)`` otherwise — ``reason`` is a
    human-readable description of what failed, suitable for logging.

    Raises
    ------
    Does not raise.  All exceptions are caught and surfaced as
    ``(False, "Verification error: <message>")``.
    """
    keys = _public_keys if _public_keys is not None else AUDIT_PUBLIC_KEYS

    try:
        # ------------------------------------------------------------------ #
        # Guard: V5 receipts must carry canonical_payload.                    #
        # ------------------------------------------------------------------ #
        canonical_payload: str | None = receipt.get("canonical_payload")
        if not canonical_payload:
            return False, (
                "Receipt is missing 'canonical_payload' — this is not a V5 receipt. "
                "Verify pre-V5 receipts with the appropriate schema-version verifier."
            )

        kid: str | None = receipt.get("kid")
        if not kid:
            return False, "Receipt is missing 'kid' field."

        public_key_b64: str | None = keys.get(kid)
        if not public_key_b64:
            return False, f"Unknown kid: '{kid}'. Add the public key to AUDIT_PUBLIC_KEYS."

        signature_b64: str | None = receipt.get("signature")
        if not signature_b64:
            return False, "Receipt is missing 'signature' field."

        # ------------------------------------------------------------------ #
        # Step 1 — Ed25519 signature over the exact canonical_payload string. #
        # ------------------------------------------------------------------ #
        spki_der: bytes = base64.b64decode(public_key_b64)
        public_key = load_der_public_key(spki_der)

        try:
            public_key.verify(  # type: ignore[union-attr]
                _decode_base64url(signature_b64),
                canonical_payload.encode("utf-8"),
            )
        except InvalidSignature:
            return False, "Signature does not verify against canonical_payload."

        # ------------------------------------------------------------------ #
        # Step 2 — Bind the signed payload to the caller's input.             #
        # ------------------------------------------------------------------ #
        payload: dict[str, Any] = json.loads(canonical_payload)

        schema_version: str | None = payload.get("schema_version")
        if schema_version != "5.0":
            return False, f"Unexpected schema_version: '{schema_version}' (expected '5.0')."

        recomputed_hash: str = sha256_hex(input_text)
        if payload.get("payload_hash") != recomputed_hash:
            return False, (
                "payload_hash does not match SHA-256 of the supplied input_text. "
                "The receipt was not signed over the input you submitted."
            )

        # ------------------------------------------------------------------ #
        # Optional cross-checks — binding the signed payload to the response  #
        # fields the caller supplied.  These catch response-tampering where    #
        # an attacker swaps metadata around a valid signature.                 #
        # ------------------------------------------------------------------ #
        expected_verdict: int = 1 if allowed else 0
        if payload.get("verdict") != expected_verdict:
            return False, (
                f"Verdict mismatch: payload contains {payload.get('verdict')}, "
                f"response claims {'allowed' if allowed else 'blocked'}."
            )

        if payload.get("timestamp") != executed_at:
            return False, (
                f"Timestamp mismatch: payload contains '{payload.get('timestamp')}', "
                f"response claims '{executed_at}'."
            )

        if payload.get("policy_ids") != policy_ids:
            return False, (
                f"policy_ids mismatch: payload {payload.get('policy_ids')} != "
                f"response {policy_ids}."
            )

        signed_anchors: list[str] = payload.get("statutory_anchors") or []
        caller_anchors: list[str] = statutory_anchors or []
        if signed_anchors != caller_anchors:
            return False, (
                f"statutory_anchors mismatch: payload {signed_anchors} != "
                f"response {caller_anchors}."
            )

        return True, None

    except Exception as exc:  # noqa: BLE001
        return False, f"Verification error: {exc}"
