from __future__ import annotations

from typing import Any, TypedDict


class FeatureWindow(TypedDict):
    start: str
    end: str


class FeatureAttribution(TypedDict):
    feature: str
    physical_source_id: str
    phi: float


class SourceAggregate(TypedDict):
    physical_source_id: str
    absolute_shap: float
    share: float


class AttributionEvidence(TypedDict):
    denominator_valid: bool
    total_absolute_shap: float
    feature_attributions: list[FeatureAttribution]
    source_aggregates: list[SourceAggregate]
    dominant_source_id: str
    dominant_source_absolute_shap: float
    dominant_source_share: float
    registered_threshold: float
    comparison: str
    materiality_triggered: bool


class EvidenceEnvelope(TypedDict):
    schema: str
    envelope_id: str
    generated_at: str
    decision_context: dict[str, Any]
    evidence_profile: dict[str, Any]
    model_identity: dict[str, Any]
    explanation_identity: dict[str, Any]
    prediction: dict[str, Any]
    attribution: AttributionEvidence
    sensor_health: dict[str, Any]
    corroboration: dict[str, Any]
    fallback: dict[str, Any]
    trust: dict[str, Any]
    envelope_sha256: str
