"""trace_mapper — convert a ramen-ai V5 receipt into a TRACE Trust Record.

TRACE EAT profile: tag:agentrust.io,2026:trace-v0.1
Spec: https://github.com/agentrust-io/trace-spec

V5 receipt schema (normative source): v5-conformance.md §4.2
TRACE Trust Record shape: derived from agentrust-io/integrations spendguard reference.

Field mapping
─────────────
TRACE field                         ← ramen-ai V5 source
────────────────────────────────────────────────────────────────────────────────
eat_profile                         constant "tag:agentrust.io,2026:trace-v0.1"
iat                                 caller-supplied (int, Unix seconds)
subject                             "spiffe://ramenai.dev/evaluation/<receipt.id>"
cnf.jwk                             caller-supplied (public JWK for signing)
policy.bundle_hash                  "sha256:" + canonical_payload.payload_hash
                                    (SHA-256 of the evaluated input, prefixed)
policy.enforcement_mode             "enforce"
policy.version                      canonical_payload.schema_version ("5.0")
runtime.measurement                 receipt.id  (UUID that uniquely names this
                                    evaluation event)
runtime.platform                    "software-only"
tool_transcript.call_count          1  (one evaluation per record)
tool_transcript.hash                "sha256:" + canonical_payload.payload_hash
tool_transcript.transcript_uri      "urn:ramen-ai:evaluation:<receipt.id>"
appraisal.policy_ref                comma-joined canonical_payload.policy_ids
appraisal.status                    "affirming" if verdict==1 else "denying"
appraisal.timestamp                 iat
appraisal.verifier                  "ramen-ai-core"
appraisal.statutory_anchors         canonical_payload.statutory_anchors
appraisal.steering                  canonical_payload.steering  (empty str → omit)
transparency                        "pending"
"""

from __future__ import annotations

import json
from typing import Any

EAT_PROFILE = "tag:agentrust.io,2026:trace-v0.1"
VERIFIER = "ramen-ai-core"


def build_trace_record(
    receipt: dict[str, Any],
    *,
    iat: int,
    jwk: dict[str, str],
) -> dict[str, Any]:
    """Map a ramen-ai V5 receipt dict onto a TRACE Trust Record dict.

    The returned dict is unsigned.  Sign it with ``agentrust_trace.sign_record``
    to produce the cMCP envelope form expected by ``agentrust-trace-tests``.

    Args:
        receipt:
            The ``data.receipt`` sub-object from a ``POST /api/v1/paas/evaluate``
            response.  Must contain ``id``, ``schema_version``, ``kid``,
            ``signature``, and ``canonical_payload`` (the raw JSON string).
        iat:
            Unix timestamp (integer seconds) to embed as the record issue time.
        jwk:
            Public JWK dict to embed in ``cnf.jwk``.  Pass the counterpart of
            whatever private key you will use to sign the record.

    Returns:
        Unsigned TRACE Trust Record dict.

    Raises:
        ValueError: if required receipt fields are missing or
                    ``schema_version`` is not ``"5.0"``.
    """
    _validate_receipt(receipt)

    payload: dict[str, Any] = json.loads(receipt["canonical_payload"])

    verdict: int = payload["verdict"]
    receipt_id: str = receipt["id"]
    kid: str = receipt["kid"]
    payload_hash: str = payload["payload_hash"]
    policy_ids: list[str] = payload.get("policy_ids", [])
    statutory_anchors: list[str] = payload.get("statutory_anchors", [])
    steering: str = payload.get("steering", "")

    # TR-POL-001: bundle_hash must carry an algorithm prefix (sha256:<hex>).
    # The V5 payload_hash is a raw 64-char hex SHA-256; prefix it.
    prefixed_hash = f"sha256:{payload_hash}"

    # TR-ENV: subject must be a SPIFFE or DID URI.
    # We use the ramen-ai trust domain with the receipt UUID as the workload ID.
    subject = f"spiffe://ramenai.dev/evaluation/{receipt_id}"

    appraisal: dict[str, Any] = {
        "policy_ref": ", ".join(policy_ids),
        "status": "affirming" if verdict == 1 else "denying",
        "timestamp": iat,
        "verifier": VERIFIER,
    }
    if statutory_anchors:
        appraisal["statutory_anchors"] = statutory_anchors
    if steering:
        appraisal["steering"] = steering

    return {
        "eat_profile": EAT_PROFILE,
        "iat": iat,
        "subject": subject,
        "cnf": {"jwk": jwk},
        "policy": {
            "bundle_hash": prefixed_hash,
            "enforcement_mode": "enforce",
            "version": payload["schema_version"],
        },
        "runtime": {
            "measurement": receipt_id,
            "platform": "software-only",
        },
        "tool_transcript": {
            "call_count": 1,
            "hash": prefixed_hash,
            "transcript_uri": f"urn:ramen-ai:evaluation:{receipt_id}",
        },
        "appraisal": appraisal,
        "transparency": "pending",
    }


# ── internal ──────────────────────────────────────────────────────────────────

def _validate_receipt(receipt: dict[str, Any]) -> None:
    required = {"id", "schema_version", "kid", "signature", "canonical_payload"}
    missing = required - receipt.keys()
    if missing:
        raise ValueError(f"Receipt missing required fields: {missing}")
    if receipt["schema_version"] != "5.0":
        raise ValueError(
            f"Unsupported schema_version '{receipt['schema_version']}'; expected '5.0'"
        )
    # canonical_payload must be parseable JSON
    try:
        json.loads(receipt["canonical_payload"])
    except json.JSONDecodeError as exc:
        raise ValueError(f"canonical_payload is not valid JSON: {exc}") from exc
