from __future__ import annotations

import argparse
import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from sklearn.metrics import average_precision_score, brier_score_loss

from .api_client import EvaluationFailure, MunicipalWaterPolicyClient
from .canonical import canonical_sha256
from .constants import BASE_DIR, DEFAULT_ARTIFACTS_DIR, TARGET_NAME
from .data_pipeline import (
    ModelBundle,
    PredictionEvidence,
    PreparedData,
    ReplayCase,
    explain_row,
    measure_source_health,
    persist_model_bundle,
    prepare_dataset,
    select_degraded_replay,
    train_model,
)
from .envelope import finalize_envelope
from .health import build_health_evidence
from .profile import EvidenceProfile, load_profile
from .renderer import render_evidence
from .scenarios import Scenario, missing_evidence_variant, scenario_variant


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is not configured")
    return value


def _dataset_path() -> Path:
    return Path(_required_environment("PUMP_SENSOR_DATA_PATH")).expanduser().resolve()


def _metrics_for_indices(
    prepared: PreparedData,
    bundle: ModelBundle,
    indices: tuple[int, ...],
) -> dict[str, float]:
    selected = list(indices)
    probabilities = bundle.model.predict_proba(
        prepared.features.loc[selected, list(bundle.feature_names)]
    )[:, 1]
    labels = prepared.target.loc[selected].astype(int).to_numpy()
    return {
        "pr_auc": float(average_precision_score(labels, probabilities)),
        "brier_score": float(brier_score_loss(labels, probabilities)),
    }


def _model_metrics(prepared: PreparedData, bundle: ModelBundle) -> dict[str, Any]:
    return {
        "calibration_period": _metrics_for_indices(
            prepared, bundle, prepared.calibration_indices
        ),
        "heldout_period": _metrics_for_indices(
            prepared, bundle, prepared.heldout_indices
        ),
    }


def _base_payload(
    *,
    profile: EvidenceProfile,
    prepared: PreparedData,
    bundle: ModelBundle,
    prediction: PredictionEvidence,
    feature_start: str,
    feature_end: str,
    health: dict[str, Any],
    corroboration: dict[str, Any] | None = None,
    fallback: dict[str, Any] | None = None,
    original_decision_id: str | None = None,
) -> dict[str, Any]:
    return {
        "envelope_id": str(uuid4()),
        "generated_at": _now(),
        "decision_context": {
            "decision_id": str(uuid4()),
            "original_decision_id": original_decision_id,
            "domain": "MUNICIPAL-WATER-ML",
            "asset_id": "DEMO-PUMP-01",
            "asset_context": "isolated_rural",
            "action_profile_id": profile.action_profile_id,
            "action_class": "dispatch_work_order_release",
            "requested_action": "release inspection work order",
            "covered_operational_action": True,
            "live_action_path": True,
            "urgency": "routine",
        },
        "evidence_profile": {
            "profile_id": profile.profile_id,
            "profile_version": profile.profile_version,
            "registry_scope": profile.registry_scope,
            "profile_sha256": profile.sha256,
        },
        "model_identity": {
            "dataset_id": profile.dataset_id,
            "dataset_sha256": prepared.dataset_sha256,
            "feature_schema_id": bundle.feature_schema_id,
            "feature_schema_sha256": bundle.feature_schema_sha256,
            "model_id": bundle.model_id,
            "model_sha256": bundle.model_sha256,
        },
        "explanation_identity": {
            "explainer_id": bundle.explainer_id,
            "explainer_type": "TreeSHAP",
            "explainer_version": bundle.explainer_version,
            "output_space": "raw_margin",
            "background_data_sha256": None,
            "physical_source_mapping_sha256": canonical_sha256(
                bundle.source_mapping
            ),
            "derivation_provenance_sha256": bundle.feature_schema_sha256,
        },
        "prediction": {
            "prediction_time": feature_end,
            "feature_window": {"start": feature_start, "end": feature_end},
            "target": TARGET_NAME,
            "raw_margin": prediction.raw_margin,
            "probability": prediction.probability,
        },
        "attribution": deepcopy(prediction.attribution),
        "sensor_health": health,
        "corroboration": corroboration
        or {
            "gate": "FAILED_NONE_QUALIFIED",
            "qualified_count": 0,
            "candidates": [],
        },
        "fallback": fallback
        or {
            "is_fallback": False,
            "fallback_model_id": None,
            "excluded_source_id": None,
            "all_descendants_excluded": None,
            "exclusion_proof_sha256": None,
        },
        "trust": {
            "local_registry_verified": prepared.provenance_verified,
            "all_artifact_hashes_verified": prepared.provenance_verified,
            "evidence_complete": True,
            "defects": [],
        },
    }


def _measured_health(
    profile: EvidenceProfile,
    prepared: PreparedData,
    replay: ReplayCase,
    source_id: str,
) -> dict[str, Any]:
    observation = measure_source_health(
        prepared, profile, replay.row_index, source_id
    )
    return build_health_evidence(
        profile=profile,
        source_id=source_id,
        feature_start=replay.feature_start,
        feature_end=replay.feature_end,
        generated_at=replay.feature_end,
        fault_start=observation.detected_failure_start,
        fault_end=observation.detected_failure_end,
        max_value_age_seconds=observation.max_value_age_seconds,
        identical_consecutive_intervals=observation.identical_consecutive_intervals,
        affected_row_ids=list(observation.measured_row_ids),
    )


def _build_scenarios(
    profile: EvidenceProfile,
    prepared: PreparedData,
    bundle: ModelBundle,
    replay: ReplayCase,
) -> tuple[list[Scenario], ModelBundle, dict[str, Any]]:
    clean_source = replay.clean.attribution["dominant_source_id"]
    clean_health = _measured_health(
        profile, prepared, replay, clean_source
    )
    if clean_health["status"] != "PASSED":
        raise ValueError("Selected healthy baseline did not pass measured health")
    clean_envelope = finalize_envelope(
        _base_payload(
            profile=profile,
            prepared=prepared,
            bundle=bundle,
            prediction=replay.clean,
            feature_start=replay.feature_start,
            feature_end=replay.feature_end,
            health=clean_health,
        )
    )
    baseline = Scenario(
        name="healthy-baseline",
        envelope=clean_envelope,
        expected_allowed=True,
        local_disposition="ALLOW",
    )

    degraded_health = build_health_evidence(
        profile=profile,
        source_id=replay.degraded_source_id,
        feature_start=replay.feature_start,
        feature_end=replay.feature_end,
        generated_at=replay.feature_end,
        fault_start=replay.fault_start,
        fault_end=replay.fault_end,
        max_value_age_seconds=replay.max_value_age_seconds,
        identical_consecutive_intervals=replay.identical_consecutive_intervals,
        affected_row_ids=list(replay.affected_row_ids),
    )
    if degraded_health["status"] != "FAILED":
        raise ValueError("Injected degradation did not fail its authoritative gate")
    degraded_base = finalize_envelope(
        _base_payload(
            profile=profile,
            prepared=prepared,
            bundle=bundle,
            prediction=replay.degraded,
            feature_start=replay.feature_start,
            feature_end=replay.feature_end,
            health=degraded_health,
        )
    )
    rural = scenario_variant(
        degraded_base,
        name="degraded-rural-original",
        asset_context="isolated_rural",
        urgency="routine",
        expected_allowed=False,
        local_disposition="BLOCK",
    )
    bridge = scenario_variant(
        degraded_base,
        name="degraded-bridge-original",
        asset_context="commuter_bridge",
        urgency="emergency",
        expected_allowed=False,
        local_disposition="BLOCK",
    )
    review = missing_evidence_variant(degraded_base)

    fallback_bundle = train_model(
        prepared, excluded_source=replay.degraded_source_id
    )
    fallback_row = prepared.features.loc[
        [replay.row_index], list(fallback_bundle.feature_names)
    ]
    fallback_prediction = explain_row(fallback_bundle, fallback_row, profile)
    fallback_source = fallback_prediction.attribution["dominant_source_id"]
    fallback_health = _measured_health(
        profile, prepared, replay, fallback_source
    )
    if fallback_health["status"] != "PASSED":
        raise ValueError(
            "Source-excluding fallback dominant source failed measured health"
        )
    descendants = sorted(
        feature
        for feature, source in bundle.source_mapping.items()
        if source == replay.degraded_source_id
    )
    exclusion_proof = {
        "excluded_source_id": replay.degraded_source_id,
        "excluded_descendants": descendants,
        "fallback_feature_names": list(fallback_bundle.feature_names),
    }
    fallback_payload = _base_payload(
        profile=profile,
        prepared=prepared,
        bundle=fallback_bundle,
        prediction=fallback_prediction,
        feature_start=replay.feature_start,
        feature_end=replay.feature_end,
        health=fallback_health,
        corroboration={
            "gate": "NOT_REQUIRED_HEALTHY_SOURCE",
            "qualified_count": 0,
            "candidates": [],
        },
        original_decision_id=rural.envelope["decision_context"]["decision_id"],
        fallback={
            "is_fallback": True,
            "fallback_model_id": fallback_bundle.model_id,
            "excluded_source_id": replay.degraded_source_id,
            "all_descendants_excluded": True,
            "excluded_descendants": descendants,
            "fallback_feature_names": list(fallback_bundle.feature_names),
            "exclusion_proof_sha256": canonical_sha256(exclusion_proof),
        },
    )
    fallback = Scenario(
        name="source-excluding-fallback",
        envelope=finalize_envelope(fallback_payload),
        expected_allowed=True,
        local_disposition="ALLOW",
    )
    return [baseline, rural, bridge, review, fallback], fallback_bundle, exclusion_proof


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_live(
    scenarios: list[Scenario],
    artifacts_dir: Path,
) -> list[dict[str, Any]]:
    client = MunicipalWaterPolicyClient.from_environment()
    reports: list[dict[str, Any]] = []
    for scenario in scenarios:
        rendered = render_evidence(scenario.envelope)
        evaluation = client.evaluate(rendered)
        if evaluation.allowed != scenario.expected_allowed:
            raise EvaluationFailure(
                f"{scenario.name}: expected allowed={scenario.expected_allowed}, "
                f"received {evaluation.allowed}"
            )
        if not evaluation.allowed:
            if not evaluation.violations:
                raise EvaluationFailure(f"{scenario.name}: block had no violations")
            for violation in evaluation.violations:
                if not violation.get("reasoning") or not violation.get(
                    "recovery_instruction"
                ):
                    raise EvaluationFailure(
                        f"{scenario.name}: violation lacks reasoning or recovery"
                    )

        scenario_dir = artifacts_dir / "results" / scenario.name
        _write_json(scenario_dir / "envelope.json", scenario.envelope)
        (scenario_dir / "input.txt").write_text(rendered + "\n", encoding="utf-8")
        _write_json(scenario_dir / "response.json", evaluation.data)
        report = {
            "scenario": scenario.name,
            "ramen_allowed": evaluation.allowed,
            "local_governance_disposition": scenario.local_disposition,
            "policy_ids": list(evaluation.policy_ids),
            "receipt_id": evaluation.receipt_id,
            "envelope_sha256": scenario.envelope["envelope_sha256"],
            "model_probability": scenario.envelope["prediction"]["probability"],
            "dominant_source": scenario.envelope["attribution"][
                "dominant_source_id"
            ],
            "dominant_source_share": scenario.envelope["attribution"][
                "dominant_source_share"
            ],
            "health_status": scenario.envelope["sensor_health"]["status"],
        }
        _write_json(scenario_dir / "summary.json", report)
        reports.append(report)
    return reports


def _prepare() -> tuple[EvidenceProfile, PreparedData, ModelBundle, ReplayCase]:
    profile = load_profile()
    prepared = prepare_dataset(
        _dataset_path(),
        profile,
        expected_dataset_sha256=_required_environment("PUMP_SENSOR_DATA_SHA256"),
    )
    bundle = train_model(prepared)
    replay = select_degraded_replay(prepared, bundle, profile)
    return profile, prepared, bundle, replay


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Municipal Water degraded-telemetry integration demo"
    )
    parser.add_argument(
        "command", choices=("inspect", "train", "run"), help="operation to perform"
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=DEFAULT_ARTIFACTS_DIR,
        help="gitignored output directory",
    )
    args = parser.parse_args(argv)
    load_dotenv(BASE_DIR / ".env", override=False)

    try:
        profile, prepared, bundle, replay = _prepare()
        metrics = _model_metrics(prepared, bundle)
        summary = {
            "dataset_sha256": prepared.dataset_sha256,
            "dataset_provenance_verified": prepared.provenance_verified,
            "profile_sha256": profile.sha256,
            "feature_schema_sha256": bundle.feature_schema_sha256,
            "split_manifest_sha256": prepared.split_manifest_sha256,
            "model_id": bundle.model_id,
            "model_sha256": bundle.model_sha256,
            "metrics": metrics,
            "replay_row_index": replay.row_index,
            "degraded_source_id": replay.degraded_source_id,
            "degraded_source_share": replay.degraded.attribution[
                "dominant_source_share"
            ],
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        if args.command == "inspect":
            return 0

        persist_model_bundle(bundle, prepared, args.artifacts_dir / "models" / "primary")
        scenarios, fallback_bundle, exclusion_proof = _build_scenarios(
            profile, prepared, bundle, replay
        )
        fallback_dir = args.artifacts_dir / "models" / "fallback"
        persist_model_bundle(fallback_bundle, prepared, fallback_dir)
        _write_json(fallback_dir / "exclusion-proof.json", exclusion_proof)
        for scenario in scenarios:
            scenario_dir = args.artifacts_dir / "prepared" / scenario.name
            _write_json(scenario_dir / "envelope.json", scenario.envelope)
            (scenario_dir / "input.txt").write_text(
                render_evidence(scenario.envelope) + "\n", encoding="utf-8"
            )
        _write_json(args.artifacts_dir / "training-summary.json", summary)
        if args.command == "train":
            return 0

        reports = _run_live(scenarios, args.artifacts_dir)
        _write_json(args.artifacts_dir / "scenario-report.json", reports)
        print(json.dumps(reports, indent=2, sort_keys=True))
        return 0
    except (ValueError, OSError, EvaluationFailure) as exc:
        print(f"ERROR: {exc}")
        return 1
