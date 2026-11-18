"""Public request and receipt types for ramen-ai-core."""

from __future__ import annotations

from typing import Any, TypedDict


class _RequiredAttestationPayload(TypedDict):
    vendor: str
    evidence: str


class AttestationPayload(_RequiredAttestationPayload, total=False):
    """Optional hardware or platform attestation sent with an evaluation."""

    challenge: str
    metadata: dict[str, Any]


class _RequiredRamenReceipt(TypedDict):
    id: str
    schema_version: str
    kid: str
    signature: str
    canonical_payload: str


class RamenReceipt(_RequiredRamenReceipt, total=False):
    """Schema V5 receipt fields returned by the evaluation API."""

    statutory_anchors: list[str]
    attestation: dict[str, Any] | None


class EvaluationResponse(TypedDict, total=False):
    """The ``data`` payload of a successful ``POST /api/v1/paas/evaluate``."""

    allowed: bool
    policy_ids: list[str]
    policies_evaluated: int
    policies_passed: int
    policies_failed: int
    policies_errored: int
    total_violations: list[dict[str, Any]]
    results: list[dict[str, Any]]
    execution_time_ms: int
    executed_at: str
    statutory_anchors: list[str]
    receipt: RamenReceipt
    receipt_alert: str


class ComplianceVerdict(TypedDict):
    """What ``RamenClient.evaluate_compliance`` returns (a plain ``dict`` at runtime)."""

    allowed: bool
    """The server's verdict. Trust it only when ``receipt_verified`` is true."""
    receipt_verified: bool
    """True only if a V5 receipt was present and the signed verdict, input hash,
    id, kid, timestamp, policy ids and anchors all agree with the response."""
    receipt_valid: bool | None
    """Raw verification result; ``None`` if no receipt was present."""
    receipt_reason: str | None
    """Why verification failed; ``None`` on success or when no receipt was present."""
    receipt_alert: str | None
    """Set when the server could not sign the receipt."""
    steering: str | None
    """Pipe-joined recovery instructions from blocking violations and gentle-hand policies."""
    policy_ids: list[str]
    """The resolved policy UUIDs that were actually evaluated and signed."""
    data: EvaluationResponse
