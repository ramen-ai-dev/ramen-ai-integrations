from __future__ import annotations

from typing import Any

from municipal_water_degraded_telemetry.attribution import aggregate_attributions
from municipal_water_degraded_telemetry.envelope import finalize_envelope
from municipal_water_degraded_telemetry.schema import EvidenceEnvelope


def sample_envelope() -> EvidenceEnvelope:
    attribution = aggregate_attributions(
        [
            "sensor_04_latest",
            "sensor_04_lag_1",
            "sensor_12_latest",
        ],
        [0.3, 0.3, -0.2],
        {
            "sensor_04_latest": "sensor_04",
            "sensor_04_lag_1": "sensor_04",
            "sensor_12_latest": "sensor_12",
        },
        0.5,
    )
    payload: dict[str, Any] = {
        "envelope_id": "10000000-0000-4000-8000-000000000001",
        "generated_at": "2026-08-10T10:31:00+00:00",
        "decision_context": {
            "decision_id": "20000000-0000-4000-8000-000000000002",
            "original_decision_id": None,
            "domain": "MUNICIPAL-WATER-ML",
            "asset_id": "DEMO-PUMP-01",
            "asset_context": "isolated_rural",
            "action_profile_id": "municipal-water-dispatch-work-order-v1",
            "action_class": "dispatch_work_order_release",
            "requested_action": "release inspection work order",
            "covered_operational_action": True,
            "live_action_path": True,
            "urgency": "routine",
        },
        "evidence_profile": {
            "profile_id": "demo.mwdta.kaggle-pump.xgb-treeshap.dispatch.v1",
            "profile_version": "1.0.0",
            "registry_scope": "integration_demo_local",
            "profile_sha256": "a" * 64,
        },
        "model_identity": {
            "dataset_id": "kaggle:nphantawee/pump-sensor-data:v1",
            "dataset_sha256": "b" * 64,
            "feature_schema_id": "pump-features-v1:123456789abc",
            "feature_schema_sha256": "c" * 64,
            "model_id": "xgb-pump-excursion-v1:123456789abc",
            "model_sha256": "d" * 64,
        },
        "explanation_identity": {
            "explainer_id": "treeshap-xgboost-raw-margin-v1:123456789abc",
            "explainer_type": "TreeSHAP",
            "explainer_version": "0.52.0",
            "output_space": "raw_margin",
            "background_data_sha256": None,
            "physical_source_mapping_sha256": "e" * 64,
            "derivation_provenance_sha256": "f" * 64,
        },
        "prediction": {
            "prediction_time": "2026-08-10T10:31:00+00:00",
            "feature_window": {
                "start": "2026-08-10T10:01:00+00:00",
                "end": "2026-08-10T10:31:00+00:00",
            },
            "target": "pump_excursion_within_30_minutes",
            "raw_margin": 2.0,
            "probability": 0.88,
            "calibrated_probability": 0.88,
        },
        "attribution": attribution,
        "sensor_health": {
            "health_profile_id": "demo-freeze-health-gate-v1",
            "authority": "deterministic_demo_injection_manifest",
            "record_generated_at": "2026-08-10T10:31:00+00:00",
            "window_coverage": 1.0,
            "source_id": "sensor_04",
            "status": "FAILED",
            "failure_modes": ["freeze", "staleness"],
            "fault_interval": {
                "start": "2026-08-10T10:28:00+00:00",
                "end": "2026-08-10T10:31:00+00:00",
            },
            "overlaps_feature_window": True,
            "max_value_age_seconds": 180,
            "identical_consecutive_intervals": 3,
            "health_manifest_sha256": "1" * 64,
        },
        "corroboration": {
            "gate": "FAILED_NONE_QUALIFIED",
            "qualified_count": 0,
            "candidates": [],
        },
        "fallback": {
            "is_fallback": False,
            "fallback_model_id": None,
            "excluded_source_id": None,
            "all_descendants_excluded": None,
            "exclusion_proof_sha256": None,
        },
        "trust": {
            "local_registry_verified": True,
            "all_artifact_hashes_verified": True,
            "evidence_complete": True,
            "defects": [],
        },
    }
    return finalize_envelope(payload)
