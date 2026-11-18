"""
ramen_ai.verifier — Ed25519 receipt verification for Schema V5.

V5 simplification: the API returns the exact signed string as
``receipt.canonical_payload``.  Clients verify against it directly and
confirm ``payload_hash`` matches SHA-256 of the original input.  No
manual reconstruction of the canonical JSON is required.

Verification
------------
1. Verify the Ed25519 signature over ``receipt['canonical_payload']``.
2. Parse the payload; require ``schema_version`` "5.0" and the same ``kid``
   and ``id`` as the receipt; recompute ``SHA-256(input_text)`` and confirm it
   equals ``payload_hash``.
3. Read the verdict from the signed bytes and compare it with the verdict the
   caller expects.
4. Optionally bind the signed ``timestamp``, ``policy_ids`` and
   ``statutory_anchors`` to the unsigned response fields.

Use :func:`signed_verdict_problem` for any allow/deny decision. If every step
passes, the receipt is authentic and cryptographically bound to the exact
input that was submitted and to the verdict that was reported.
"""
from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, TypedDict

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_der_public_key

VERDICT_BLOCK = 0
VERDICT_ALLOW = 1

# ---------------------------------------------------------------------------
# Production public keys — keyed by ``kid`` (key-rotation safe).
# These are SPKI DER blobs encoded as standard base64.
# Safe to embed in client-side code per the API contract.
# ---------------------------------------------------------------------------
AUDIT_PUBLIC_KEYS: dict[str, str] = {
    "ramen_pk_v1": "MCowBQYDK2VwAyEA8iTL9lJGYn2alGn1yMWVAIqLImTpADb9CqaLhisTuto=",
}


class SignedVerdictBinding(TypedDict, total=False):
    """Unsigned response fields that the signed payload must agree with."""

    executed_at: str
    """The response ``executed_at``; must equal the signed ``timestamp``."""
    policy_ids: Sequence[str]
    """The response ``policy_ids``; must equal the signed list, in order."""
    statutory_anchors: Sequence[str] | None
    """The response ``statutory_anchors``; absent counts as empty."""


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


def _signed_payload(
    receipt: Any, keys: Mapping[str, str]
) -> tuple[dict[str, Any] | None, str | None]:
    """Check the signature and the receipt-to-payload identity.

    Returns ``(payload, None)`` or ``(None, problem)``. Everything in
    ``payload`` comes from the signed bytes.
    """
    if not isinstance(receipt, Mapping):
        return None, "No Schema V5 receipt was returned."
    canonical_payload = receipt.get("canonical_payload")
    if not canonical_payload or not isinstance(canonical_payload, str):
        return None, (
            "Receipt is missing 'canonical_payload' — this is not a V5 receipt. "
            "Verify pre-V5 receipts with the appropriate schema-version verifier."
        )
    kid = receipt.get("kid")
    if not kid or not isinstance(kid, str):
        return None, "Receipt is missing 'kid' field."
    public_key_b64 = keys.get(kid)
    if not public_key_b64:
        return None, f"Unknown kid: '{kid}'. Add the public key to AUDIT_PUBLIC_KEYS."
    signature_b64 = receipt.get("signature")
    if not signature_b64 or not isinstance(signature_b64, str):
        return None, "Receipt is missing 'signature' field."
    receipt_id = receipt.get("id")
    if not receipt_id or not isinstance(receipt_id, str):
        return None, "Receipt is missing 'id' field."

    # Step 1 — Ed25519 signature over the exact canonical_payload string.
    public_key = load_der_public_key(base64.b64decode(public_key_b64))
    if not isinstance(public_key, Ed25519PublicKey):
        return None, f"Key '{kid}' is not an Ed25519 public key."
    try:
        public_key.verify(
            _decode_base64url(signature_b64),
            canonical_payload.encode("utf-8"),
        )
    except InvalidSignature:
        return None, "Signature does not verify against canonical_payload."

    payload = json.loads(canonical_payload)
    if not isinstance(payload, dict):
        return None, "canonical_payload is not a JSON object."
    schema_version = payload.get("schema_version")
    if schema_version != "5.0":
        return None, f"Unexpected schema_version: '{schema_version}' (expected '5.0')."
    if payload.get("kid") != kid:
        return None, "Signed kid does not match receipt.kid."
    if payload.get("id") != receipt_id:
        return None, "Signed id does not match receipt.id."
    return payload, None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def signed_verdict_problem(
    receipt: Any,
    input_text: str,
    expected_verdict: int,
    *,
    public_keys: Mapping[str, str] | None = None,
    binding: SignedVerdictBinding | None = None,
) -> str | None:
    """Return why *receipt* does not prove a verdict, or ``None`` if it does.

    All of these must hold, read from the signed bytes rather than from the
    response's unsigned fields:

    1. The receipt carries ``id``, ``kid``, ``signature`` and ``canonical_payload``.
    2. The Ed25519 signature over ``canonical_payload`` verifies under the key
       pinned for ``kid`` (``ramen_pk_v1`` in production).
    3. The signed payload has ``schema_version`` "5.0", the same ``kid`` and
       ``id`` as the receipt, and ``payload_hash == SHA-256(input_text)``.
    4. The signed ``verdict`` equals *expected_verdict*
       (:data:`VERDICT_ALLOW` or :data:`VERDICT_BLOCK`).
    5. When *binding* is given, the signed ``timestamp``, ``policy_ids`` and
       ``statutory_anchors`` equal the response's own values.

    Never raises on a malformed receipt: failures come back as a string.
    Raises ``ValueError`` only if *expected_verdict* is not 0 or 1, which is a
    caller bug.
    """
    if (
        isinstance(expected_verdict, bool)
        or not isinstance(expected_verdict, int)
        or expected_verdict not in (VERDICT_BLOCK, VERDICT_ALLOW)
    ):
        raise ValueError("expected_verdict must be VERDICT_ALLOW (1) or VERDICT_BLOCK (0)")
    keys = AUDIT_PUBLIC_KEYS if public_keys is None else public_keys
    try:
        payload, problem = _signed_payload(receipt, keys)
        if payload is None:
            return problem
        if payload.get("payload_hash") != sha256_hex(input_text):
            return (
                "payload_hash does not match SHA-256 of the supplied input_text. "
                "The receipt was not signed over the input you submitted."
            )
        signed_verdict = payload.get("verdict")
        if isinstance(signed_verdict, bool) or signed_verdict != expected_verdict:
            return (
                f"Verdict mismatch: payload contains {signed_verdict}, "
                f"response claims {'allowed' if expected_verdict == VERDICT_ALLOW else 'blocked'}."
            )
        if binding is not None:
            executed_at = binding.get("executed_at")
            if payload.get("timestamp") != executed_at:
                return (
                    f"Timestamp mismatch: payload contains '{payload.get('timestamp')}', "
                    f"response claims '{executed_at}'."
                )
            policy_ids = list(binding.get("policy_ids") or [])
            if payload.get("policy_ids") != policy_ids:
                return (
                    f"policy_ids mismatch: payload {payload.get('policy_ids')} != "
                    f"response {policy_ids}."
                )
            signed_anchors = payload.get("statutory_anchors") or []
            caller_anchors = list(binding.get("statutory_anchors") or [])
            if signed_anchors != caller_anchors:
                return (
                    f"statutory_anchors mismatch: payload {signed_anchors} != "
                    f"response {caller_anchors}."
                )
        return None
    except Exception as exc:  # noqa: BLE001
        return f"Verification error: {exc}"


def verify_allow_receipt_signature(
    receipt: Any,
    *,
    public_keys: Mapping[str, str] | None = None,
) -> tuple[bool, str | None]:
    """Verify that *receipt* is an authentic, signed ALLOW verdict.

    Unlike :func:`signed_verdict_problem` this does not bind the receipt to an
    input string. Use it when the evaluated input is not available, for
    example when contributing an exemplar to ramen forge. It checks the
    signature, the signed ``schema_version``, ``kid`` and ``id``, and that the
    signed ``verdict`` is 1. It does not prove which input the receipt covers.

    Never raises: returns ``(True, None)`` or ``(False, reason)``.
    """
    keys = AUDIT_PUBLIC_KEYS if public_keys is None else public_keys
    try:
        payload, problem = _signed_payload(receipt, keys)
        if payload is None:
            return False, problem
        verdict = payload.get("verdict")
        if isinstance(verdict, bool) or verdict != VERDICT_ALLOW:
            return False, "Signed verdict is not 1 (the evaluated call was blocked)."
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, f"Verification error: {exc}"


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
    Verify a Schema V5 evaluation receipt against a response.

    A thin wrapper over :func:`signed_verdict_problem`: the expected verdict is
    ``1`` when *allowed* is true and ``0`` otherwise, and the signed timestamp,
    policy ids and statutory anchors must equal the response's own values.

    Parameters
    ----------
    receipt:
        The ``receipt`` object returned by the evaluate endpoint.
        Must contain ``id``, ``kid``, ``signature`` and ``canonical_payload``.
    executed_at:
        The ``executed_at`` ISO 8601 timestamp from the response root.
    policy_ids:
        The resolved ``policy_ids`` array from the response root.
    input_text:
        The raw input string that was submitted to the evaluate endpoint.
    allowed:
        The ``allowed`` boolean from the response root.
    violations:
        Accepted for API symmetry; not used.
    statutory_anchors:
        The ``statutory_anchors`` list from the response root.
    _public_keys:
        Override the production key map.  Pass a dict keyed by ``kid`` to
        use test-vector or rotated keys without touching the module constant.

    Returns
    -------
    ``(True, None)`` if the receipt is valid, bound to ``input_text`` and to the
    reported verdict. ``(False, reason)`` otherwise — ``reason`` is a
    human-readable description of what failed, suitable for logging.

    Raises
    ------
    Does not raise.  All exceptions are caught and surfaced as
    ``(False, "Verification error: <message>")``.
    """
    problem = signed_verdict_problem(
        receipt,
        input_text,
        VERDICT_ALLOW if allowed else VERDICT_BLOCK,
        public_keys=_public_keys,
        binding={
            "executed_at": executed_at,
            "policy_ids": policy_ids,
            "statutory_anchors": statutory_anchors,
        },
    )
    return problem is None, problem
