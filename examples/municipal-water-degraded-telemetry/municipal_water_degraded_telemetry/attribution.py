from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence

from .schema import AttributionEvidence, FeatureAttribution, SourceAggregate


def aggregate_attributions(
    feature_names: Sequence[str],
    shap_values: Sequence[float],
    source_mapping: Mapping[str, str],
    threshold: float,
) -> AttributionEvidence:
    if len(feature_names) != len(shap_values):
        raise ValueError("Feature names and SHAP values must have equal length")
    if not feature_names:
        raise ValueError("Attribution evidence cannot be empty")

    grouped: dict[str, float] = defaultdict(float)
    features: list[FeatureAttribution] = []
    for feature, raw_phi in zip(feature_names, shap_values, strict=True):
        if feature not in source_mapping:
            raise ValueError(f"Feature lacks physical-source lineage: {feature}")
        phi = float(raw_phi)
        if not math.isfinite(phi):
            raise ValueError(f"Non-finite SHAP value for {feature}")
        source = source_mapping[feature]
        grouped[source] += abs(phi)
        features.append({"feature": feature, "physical_source_id": source, "phi": phi})

    denominator = float(sum(grouped.values()))
    if not math.isfinite(denominator) or denominator <= 0.0:
        raise ValueError("Absolute SHAP denominator must be finite and positive")

    aggregates: list[SourceAggregate] = [
        {
            "physical_source_id": source,
            "absolute_shap": absolute,
            "share": absolute / denominator,
        }
        for source, absolute in sorted(grouped.items())
    ]
    dominant = max(aggregates, key=lambda item: item["absolute_shap"])
    share = dominant["share"]
    return {
        "denominator_valid": True,
        "total_absolute_shap": denominator,
        "feature_attributions": features,
        "source_aggregates": aggregates,
        "dominant_source_id": dominant["physical_source_id"],
        "dominant_source_absolute_shap": dominant["absolute_shap"],
        "dominant_source_share": share,
        "registered_threshold": threshold,
        "comparison": "gte",
        "materiality_triggered": share >= threshold,
    }
