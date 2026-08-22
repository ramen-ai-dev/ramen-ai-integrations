from __future__ import annotations

import math
from typing import Any

from .canonical import canonical_sha256, envelope_sha256
from .constants import SCHEMA_ID
from .schema import EvidenceEnvelope


def finalize_envelope(payload: dict[str, Any]) -> EvidenceEnvelope:
    candidate = dict(payload)
    candidate["schema"] = SCHEMA_ID
    candidate["envelope_sha256"] = ""
    validate_envelope(candidate)
    candidate["envelope_sha256"] = envelope_sha256(candidate)
    return candidate  # type: ignore[return-value]


def validate_envelope(envelope: dict[str, Any]) -> None:
    required = {
        "schema",
        "envelope_id",
        "generated_at",
        "decision_context",
        "evidence_profile",
        "model_identity",
        "explanation_identity",
        "prediction",
        "attribution",
        "sensor_health",
        "corroboration",
        "fallback",
        "trust",
        "envelope_sha256",
    }
    missing = sorted(required - envelope.keys())
    if missing:
        raise ValueError(f"Evidence envelope missing fields: {', '.join(missing)}")
    if envelope["schema"] != SCHEMA_ID:
        raise ValueError("Unsupported evidence envelope schema")

    attribution = envelope["attribution"]
    total = float(attribution["total_absolute_shap"])
    aggregates = attribution["source_aggregates"]
    aggregate_total = sum(float(item["absolute_shap"]) for item in aggregates)
    if not math.isclose(total, aggregate_total, rel_tol=1e-9, abs_tol=1e-12):
        raise ValueError("Source aggregates do not equal the SHAP denominator")
    if not math.isclose(
        sum(float(item["share"]) for item in aggregates),
        1.0,
        rel_tol=1e-9,
        abs_tol=1e-12,
    ):
        raise ValueError("Physical-source shares must sum to one")
    threshold = float(attribution["registered_threshold"])
    expected_materiality = float(attribution["dominant_source_share"]) >= threshold
    if attribution["materiality_triggered"] is not expected_materiality:
        raise ValueError("Materiality result does not match the registered comparator")

    dominant_id = attribution["dominant_source_id"]
    health_source = envelope["sensor_health"]["source_id"]
    if dominant_id != health_source:
        raise ValueError("Health evidence must cover the evaluated dominant source")

    fallback = envelope["fallback"]
    if fallback["is_fallback"]:
        _validate_fallback(envelope)

    trust = envelope["trust"]
    if trust["local_registry_verified"] and not trust["all_artifact_hashes_verified"]:
        raise ValueError("Registry cannot be verified while artifact hashes fail")


def _validate_fallback(envelope: dict[str, Any]) -> None:
    fallback = envelope["fallback"]
    if not fallback.get("fallback_model_id"):
        raise ValueError("Fallback requires a separate model identity")
    if fallback.get("all_descendants_excluded") is not True:
        raise ValueError("Fallback must exclude every suspect-source descendant")
    excluded = fallback.get("excluded_descendants")
    features = fallback.get("fallback_feature_names")
    if not isinstance(excluded, list) or not excluded:
        raise ValueError("Fallback exclusion proof lacks suspect descendants")
    if not isinstance(features, list) or not features:
        raise ValueError("Fallback exclusion proof lacks fallback features")
    if set(excluded) & set(features):
        raise ValueError("Fallback still contains a suspect-source descendant")
    proof = {
        "excluded_source_id": fallback["excluded_source_id"],
        "excluded_descendants": excluded,
        "fallback_feature_names": features,
    }
    if canonical_sha256(proof) != fallback.get("exclusion_proof_sha256"):
        raise ValueError("Fallback exclusion proof hash is invalid")
    if envelope["sensor_health"]["status"] != "PASSED":
        raise ValueError("Fallback dominant source must pass its health gate")
    if envelope["corroboration"]["gate"] not in {
        "PASSED",
        "NOT_REQUIRED_HEALTHY_SOURCE",
    }:
        raise ValueError("Fallback corroboration/support gate did not pass")
    trust = envelope["trust"]
    if not (
        trust["local_registry_verified"]
        and trust["all_artifact_hashes_verified"]
        and trust["evidence_complete"]
    ):
        raise ValueError("Fallback must independently pass every trust gate")


def verify_envelope_hash(envelope: EvidenceEnvelope) -> bool:
    return envelope_sha256(envelope) == envelope["envelope_sha256"]
