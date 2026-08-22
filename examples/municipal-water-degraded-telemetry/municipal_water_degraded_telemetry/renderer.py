from __future__ import annotations

from .envelope import validate_envelope, verify_envelope_hash
from .schema import EvidenceEnvelope


def _number(value: float) -> str:
    return f"{float(value):.6f}"


def render_evidence(envelope: EvidenceEnvelope) -> str:
    validate_envelope(envelope)
    if not verify_envelope_hash(envelope):
        raise ValueError("Evidence envelope hash is invalid")

    context = envelope["decision_context"]
    profile = envelope["evidence_profile"]
    model = envelope["model_identity"]
    explanation = envelope["explanation_identity"]
    prediction = envelope["prediction"]
    window = prediction["feature_window"]
    attribution = envelope["attribution"]
    health = envelope["sensor_health"]
    fault = health["fault_interval"]
    corroboration = envelope["corroboration"]
    fallback = envelope["fallback"]
    trust = envelope["trust"]

    fault_interval = (
        f"{fault['start']}..{fault['end']}"
        if fault["start"] is not None
        else "none"
    )
    failure_modes = ",".join(health["failure_modes"]) or "none"
    profile_label = "Trusted" if trust["local_registry_verified"] else "Untrusted"
    fallback_summary = (
        f"separate fallback:true; fallback_model:{fallback['fallback_model_id']}; "
        f"excluded_source:{fallback['excluded_source_id']}; "
        f"all_descendants_excluded:{str(fallback['all_descendants_excluded']).lower()}; "
        f"exclusion_proof_sha256:{fallback['exclusion_proof_sha256']}; "
        "original record retained and remains unusable"
        if fallback["is_fallback"]
        else "original prediction:true; fallback:false; original record retained"
    )

    return "\n".join(
        [
            (
                "Covered municipal-water action: "
                f"{context['requested_action']} for asset {context['asset_id']} from "
                f"decision {context['decision_id']}; live_action_path:"
                f"{str(context['live_action_path']).lower()}; asset_context:"
                f"{context['asset_context']}; urgency:{context['urgency']}."
            ),
            (
                f"{profile_label} local demo profile {profile['profile_id']} "
                f"hash:{profile['profile_sha256']}; model:{model['model_id']}; "
                f"feature_schema:{model['feature_schema_id']}; explainer:"
                f"{explanation['explainer_id']}; output_space:"
                f"{explanation['output_space']}; all_artifact_hashes_verified:"
                f"{str(trust['all_artifact_hashes_verified']).lower()}."
            ),
            (
                f"Prediction target:{prediction['target']}; model_probability:"
                f"{_number(prediction['probability'])}; feature_window:"
                f"{window['start']}..{window['end']}."
            ),
            (
                f"Physical source {attribution['dominant_source_id']} aggregates all "
                "raw, transformed, lagged, rolling, residual, imputed, and aliased "
                f"descendants; absolute_shap:{_number(attribution['dominant_source_absolute_shap'])}; "
                f"total_absolute_shap:{_number(attribution['total_absolute_shap'])}; "
                f"share:{_number(attribution['dominant_source_share'])}; "
                f"registered_demo_rule:share>={_number(attribution['registered_threshold'])}; "
                f"materiality_triggered:{str(attribution['materiality_triggered']).lower()}."
            ),
            (
                f"Authoritative demo health gate {health['health_profile_id']} covers "
                f"{_number(health['window_coverage'] * 100.0)}% of the feature window "
                f"and reports {health['status']} for {health['source_id']}; "
                f"failure_modes:{failure_modes}; max_value_age_seconds:"
                f"{health['max_value_age_seconds']}; identical_consecutive_intervals:"
                f"{health['identical_consecutive_intervals']}; fault_interval:"
                f"{fault_interval}; overlaps_feature_window:"
                f"{str(health['overlaps_feature_window']).lower()}."
            ),
            (
                f"Corroboration gate:{corroboration['gate']}; qualified_count:"
                f"{corroboration['qualified_count']}; common-mode-independent support:"
                f"{'present' if corroboration['qualified_count'] else 'none'}."
            ),
            f"{fallback_summary}.",
            f"evidence_envelope_sha256:{envelope['envelope_sha256']}.",
        ]
    )
