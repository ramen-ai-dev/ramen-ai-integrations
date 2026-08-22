from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from .envelope import finalize_envelope
from .schema import EvidenceEnvelope

LocalDisposition = Literal["ALLOW", "BLOCK", "REVIEW_REQUIRED"]


@dataclass(frozen=True)
class Scenario:
    name: str
    envelope: EvidenceEnvelope
    expected_allowed: bool
    local_disposition: LocalDisposition


def scenario_variant(
    base: EvidenceEnvelope,
    *,
    name: str,
    asset_context: str,
    urgency: str,
    expected_allowed: bool,
    local_disposition: LocalDisposition,
) -> Scenario:
    payload = deepcopy(dict(base))
    payload.pop("envelope_sha256", None)
    payload["envelope_id"] = str(uuid4())
    payload["decision_context"]["decision_id"] = str(uuid4())
    payload["decision_context"]["asset_context"] = asset_context
    payload["decision_context"]["urgency"] = urgency
    return Scenario(
        name=name,
        envelope=finalize_envelope(payload),
        expected_allowed=expected_allowed,
        local_disposition=local_disposition,
    )


def missing_evidence_variant(base: EvidenceEnvelope) -> Scenario:
    payload = deepcopy(dict(base))
    payload.pop("envelope_sha256", None)
    payload["envelope_id"] = str(uuid4())
    payload["decision_context"]["decision_id"] = str(uuid4())
    payload["trust"] = {
        "local_registry_verified": False,
        "all_artifact_hashes_verified": False,
        "evidence_complete": False,
        "defects": ["unknown_profile_identity"],
    }
    payload["sensor_health"]["status"] = "UNKNOWN"
    payload["sensor_health"]["window_coverage"] = 0.0
    return Scenario(
        name="missing-untrusted-evidence",
        envelope=finalize_envelope(payload),
        expected_allowed=False,
        local_disposition="REVIEW_REQUIRED",
    )
