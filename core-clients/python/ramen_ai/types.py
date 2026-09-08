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
