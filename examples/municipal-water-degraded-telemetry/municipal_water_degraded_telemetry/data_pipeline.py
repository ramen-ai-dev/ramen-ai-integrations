from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from numpy.lib.stride_tricks import sliding_window_view
from xgboost import XGBClassifier

from .attribution import aggregate_attributions
from .canonical import canonical_sha256, sha256_bytes
from .constants import TARGET_NAME
from .profile import EvidenceProfile
from .schema import AttributionEvidence


@dataclass(frozen=True)
class PreparedData:
    source_path: Path
    raw: pd.DataFrame
    features: pd.DataFrame
    target: pd.Series
    train_indices: tuple[int, ...]
    calibration_indices: tuple[int, ...]
    heldout_indices: tuple[int, ...]
    feature_names: tuple[str, ...]
    source_mapping: dict[str, str]
    sensor_columns: tuple[str, ...]
    dataset_sha256: str
    provenance_verified: bool
    feature_schema_sha256: str
    split_manifest: dict[str, Any]
    split_manifest_sha256: str


@dataclass(frozen=True)
class ModelBundle:
    model: XGBClassifier
    feature_names: tuple[str, ...]
    source_mapping: dict[str, str]
    model_id: str
    model_sha256: str
    feature_schema_id: str
    feature_schema_sha256: str
    explainer_id: str
    explainer_config_sha256: str
    explainer_version: str
    xgboost_version: str


@dataclass(frozen=True)
class PredictionEvidence:
    raw_margin: float
    probability: float
    base_value: float
    shap_values: tuple[float, ...]
    attribution: AttributionEvidence


@dataclass(frozen=True)
class HealthObservation:
    max_value_age_seconds: int
    identical_consecutive_intervals: int
    measured_row_ids: tuple[int, ...]
    detected_failure_start: str | None
    detected_failure_end: str | None


@dataclass(frozen=True)
class ReplayCase:
    row_index: int
    degraded_source_id: str
    clean: PredictionEvidence
    degraded: PredictionEvidence
    fault_start: str
    fault_end: str
    feature_start: str
    feature_end: str
    affected_row_ids: tuple[int, ...]
    max_value_age_seconds: int
    identical_consecutive_intervals: int


def resolve_dataset_path(path: Path) -> Path:
    if path.is_file():
        return path
    if path.is_dir():
        candidates = sorted(path.glob("*.csv"))
        preferred = [item for item in candidates if "sensor" in item.name.lower()]
        if len(preferred) == 1:
            return preferred[0]
        if len(candidates) == 1:
            return candidates[0]
    raise ValueError(
        "PUMP_SENSOR_DATA_PATH must identify the Kaggle CSV or a directory "
        "containing exactly one unambiguous CSV"
    )


def _future_excursion_target(statuses: np.ndarray, horizon: int) -> np.ndarray:
    normalized = np.char.upper(statuses.astype(str))
    excursion = np.isin(normalized, ["BROKEN", "RECOVERING"])
    padded = np.pad(excursion[1:], (0, horizon), constant_values=False)
    windows = sliding_window_view(padded, horizon)[: len(excursion)]
    return windows.any(axis=1)


def _build_feature_frame(
    raw: pd.DataFrame,
    sensor_columns: tuple[str, ...],
) -> tuple[pd.DataFrame, dict[str, str]]:
    features: dict[str, pd.Series] = {}
    mapping: dict[str, str] = {}
    for source in sensor_columns:
        values = pd.to_numeric(raw[source], errors="coerce")
        definitions = {
            f"{source}_latest": values,
            f"{source}_lag_1": values.shift(1),
            f"{source}_rolling_mean_5": values.rolling(5).mean(),
            f"{source}_rolling_std_5": values.rolling(5).std(),
        }
        for feature, series in definitions.items():
            features[feature] = series
            mapping[feature] = source
    return pd.DataFrame(features, index=raw.index), mapping


def prepare_dataset(
    path: Path,
    profile: EvidenceProfile,
    *,
    expected_dataset_sha256: str,
    max_sources: int = 12,
    horizon_minutes: int = 30,
) -> PreparedData:
    source_path = resolve_dataset_path(path)
    source_bytes = source_path.read_bytes()
    dataset_sha256 = sha256_bytes(source_bytes)
    expected_digest = expected_dataset_sha256.strip().lower()
    if len(expected_digest) != 64 or any(
        character not in "0123456789abcdef" for character in expected_digest
    ):
        raise ValueError("PUMP_SENSOR_DATA_SHA256 must be a 64-character hex digest")
    if dataset_sha256 != expected_digest:
        raise ValueError(
            "Dataset checksum does not match the operator-approved Kaggle artifact"
        )

    raw = pd.read_csv(source_path).drop(columns=["Unnamed: 0"], errors="ignore")
    required = {"timestamp", "machine_status"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"Dataset is missing required columns: {sorted(missing)}")

    timestamps = pd.to_datetime(raw["timestamp"], utc=True, errors="coerce")
    if timestamps.isna().any():
        raise ValueError("Dataset contains invalid timestamps")
    deltas = timestamps.diff().dt.total_seconds().dropna().to_numpy()
    if len(deltas) == 0 or np.any(deltas <= 0):
        raise ValueError("Dataset timestamps must be strictly increasing")
    expected_cadence = float(profile.expected_cadence_seconds)
    if not np.allclose(deltas, expected_cadence, rtol=0.0, atol=1e-6):
        raise ValueError(
            "Every adjacent timestamp must match the profile's exact 60-second cadence"
        )
    raw = raw.copy()
    raw["timestamp"] = timestamps

    statuses = raw["machine_status"].astype(str).str.upper()
    unknown_statuses = sorted(set(statuses) - {"NORMAL", "BROKEN", "RECOVERING"})
    if unknown_statuses:
        raise ValueError(f"Dataset contains unsupported machine states: {unknown_statuses}")

    available = [column for column in raw.columns if column.startswith("sensor_")]
    usable: list[str] = []
    for column in available:
        numeric = pd.to_numeric(raw[column], errors="coerce")
        if numeric.notna().mean() >= 0.95 and numeric.nunique(dropna=True) > 1:
            raw[column] = numeric
            usable.append(column)
    if len(usable) < 2:
        raise ValueError("Dataset must provide at least two usable sensor columns")
    sensor_columns = tuple(usable[:max_sources])

    feature_frame, source_mapping = _build_feature_frame(raw, sensor_columns)
    horizon_rows = max(
        1, int(horizon_minutes * 60 / profile.expected_cadence_seconds)
    )
    target_values = _future_excursion_target(statuses.to_numpy(), horizon_rows)
    target = pd.Series(target_values, index=raw.index, name=TARGET_NAME)
    current_normal = statuses.eq("NORMAL")
    has_complete_future = pd.Series(
        np.arange(len(raw)) + horizon_rows < len(raw), index=raw.index
    )
    eligible = current_normal & has_complete_future & feature_frame.notna().all(axis=1)
    eligible_indices = raw.index[eligible].to_numpy(dtype=int)
    if len(eligible_indices) < 100:
        raise ValueError("Too few eligible normal-state rows after feature preparation")

    first_boundary = int(len(eligible_indices) * 0.60)
    second_boundary = int(len(eligible_indices) * 0.80)
    first_raw_boundary = int(eligible_indices[first_boundary])
    second_raw_boundary = int(eligible_indices[second_boundary])
    train_indices = eligible_indices[
        eligible_indices < first_raw_boundary - horizon_rows
    ]
    calibration_indices = eligible_indices[
        (eligible_indices >= first_raw_boundary)
        & (eligible_indices < second_raw_boundary - horizon_rows)
    ]
    heldout_indices = eligible_indices[eligible_indices >= second_raw_boundary]
    for label, indices in (
        ("training", train_indices),
        ("calibration", calibration_indices),
        ("held-out", heldout_indices),
    ):
        if len(indices) == 0:
            raise ValueError(f"{label} split is empty")
        if target.loc[indices].nunique() < 2:
            raise ValueError(
                f"{label} split does not contain both target classes; "
                "the dataset has too few independent transitions for this profile"
            )

    feature_names = tuple(feature_frame.columns)
    feature_schema = _feature_schema(feature_names, source_mapping)
    split_manifest = {
        "cadence_seconds": profile.expected_cadence_seconds,
        "horizon_minutes": horizon_minutes,
        "purge_rows": horizon_rows,
        "training": _split_summary(raw, target, train_indices),
        "calibration": _split_summary(raw, target, calibration_indices),
        "heldout": _split_summary(raw, target, heldout_indices),
    }
    return PreparedData(
        source_path=source_path,
        raw=raw,
        features=feature_frame,
        target=target,
        train_indices=tuple(int(item) for item in train_indices),
        calibration_indices=tuple(int(item) for item in calibration_indices),
        heldout_indices=tuple(int(item) for item in heldout_indices),
        feature_names=feature_names,
        source_mapping=source_mapping,
        sensor_columns=sensor_columns,
        dataset_sha256=dataset_sha256,
        provenance_verified=True,
        feature_schema_sha256=canonical_sha256(feature_schema),
        split_manifest=split_manifest,
        split_manifest_sha256=canonical_sha256(split_manifest),
    )


def _feature_schema(
    feature_names: tuple[str, ...], source_mapping: dict[str, str]
) -> dict[str, Any]:
    return {
        "features": list(feature_names),
        "physical_source_mapping": source_mapping,
        "target": TARGET_NAME,
    }


def _split_summary(
    raw: pd.DataFrame,
    target: pd.Series,
    indices: np.ndarray,
) -> dict[str, Any]:
    return {
        "start": raw.loc[int(indices[0]), "timestamp"].isoformat(),
        "end": raw.loc[int(indices[-1]), "timestamp"].isoformat(),
        "rows": int(len(indices)),
        "positive_rows": int(target.loc[indices].sum()),
        "negative_rows": int((~target.loc[indices]).sum()),
    }


def train_model(
    prepared: PreparedData,
    *,
    excluded_source: str | None = None,
) -> ModelBundle:
    feature_names = tuple(
        feature
        for feature in prepared.feature_names
        if prepared.source_mapping[feature] != excluded_source
    )
    if not feature_names:
        raise ValueError("Fallback exclusion removed every model feature")
    source_mapping = {
        feature: prepared.source_mapping[feature] for feature in feature_names
    }
    feature_schema_sha256 = canonical_sha256(
        _feature_schema(feature_names, source_mapping)
    )
    model = XGBClassifier(
        n_estimators=240,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=2.0,
        reg_lambda=1.0,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=2026,
        n_jobs=1,
        tree_method="hist",
    )
    train_index = list(prepared.train_indices)
    model.fit(
        prepared.features.loc[train_index, list(feature_names)],
        prepared.target.loc[train_index].astype(int),
    )
    model_bytes = bytes(model.get_booster().save_raw(raw_format="ubj"))
    model_sha = sha256_bytes(model_bytes)
    explainer_config = {
        "implementation": "shap.TreeExplainer",
        "shap_version": shap.__version__,
        "xgboost_version": xgb.__version__,
        "feature_perturbation": "tree_path_dependent",
        "output_space": "raw_margin",
        "background_data_sha256": None,
        "feature_names": list(feature_names),
    }
    config_sha = canonical_sha256(explainer_config)
    model_prefix = (
        f"xgb-pump-excursion-without-{excluded_source}-v1"
        if excluded_source
        else "xgb-pump-excursion-v1"
    )
    return ModelBundle(
        model=model,
        feature_names=feature_names,
        source_mapping=source_mapping,
        model_id=f"{model_prefix}:{model_sha[:12]}",
        model_sha256=model_sha,
        feature_schema_id=f"pump-features-v1:{feature_schema_sha256[:12]}",
        feature_schema_sha256=feature_schema_sha256,
        explainer_id=f"treeshap-xgboost-raw-margin-v1:{config_sha[:12]}",
        explainer_config_sha256=config_sha,
        explainer_version=shap.__version__,
        xgboost_version=xgb.__version__,
    )


def explain_row(
    bundle: ModelBundle,
    row: pd.DataFrame,
    profile: EvidenceProfile,
) -> PredictionEvidence:
    ordered = row.loc[:, list(bundle.feature_names)]
    explainer = shap.TreeExplainer(
        bundle.model,
        feature_perturbation="tree_path_dependent",
        model_output="raw",
    )
    explanation = explainer(ordered)
    values = np.asarray(explanation.values)[0].astype(float)
    base_values = np.asarray(explanation.base_values).reshape(-1)
    raw_margin = float(
        bundle.model.get_booster().predict(
            xgb.DMatrix(ordered, feature_names=list(bundle.feature_names)),
            output_margin=True,
        )[0]
    )
    probability = float(bundle.model.predict_proba(ordered)[0, 1])
    attribution = aggregate_attributions(
        bundle.feature_names,
        values.tolist(),
        bundle.source_mapping,
        profile.materiality_threshold,
    )
    return PredictionEvidence(
        raw_margin=raw_margin,
        probability=probability,
        base_value=float(base_values[0]),
        shap_values=tuple(float(item) for item in values),
        attribution=attribution,
    )


def measure_source_health(
    prepared: PreparedData,
    profile: EvidenceProfile,
    row_index: int,
    source: str,
) -> HealthObservation:
    cadence = profile.expected_cadence_seconds
    feature_end = prepared.raw.loc[row_index, "timestamp"] + pd.Timedelta(
        seconds=cadence
    )
    feature_start = feature_end - pd.Timedelta(minutes=30)
    mask = (prepared.raw["timestamp"] >= feature_start) & (
        prepared.raw["timestamp"] < feature_end
    )
    window = prepared.raw.loc[mask, ["timestamp", source]]
    if window.empty or window[source].isna().any():
        raise ValueError(f"Cannot establish complete health evidence for {source}")

    values = window[source].to_numpy()
    max_run = 1
    current_run = 1
    max_run_start = 0
    current_start = 0
    for index in range(1, len(values)):
        if values[index] == values[index - 1]:
            current_run += 1
        else:
            current_run = 1
            current_start = index
        if current_run > max_run:
            max_run = current_run
            max_run_start = current_start
    identical_intervals = max_run - 1
    max_age = identical_intervals * cadence
    failure_start = None
    failure_end = None
    if (
        max_age > profile.max_value_age_seconds
        or identical_intervals >= profile.freeze_failure_consecutive_intervals
    ):
        repeated_sample = min(max_run_start + 1, len(window) - 1)
        failure_start = window.iloc[repeated_sample]["timestamp"].isoformat()
        failure_end = feature_end.isoformat()
    return HealthObservation(
        max_value_age_seconds=max_age,
        identical_consecutive_intervals=identical_intervals,
        measured_row_ids=tuple(int(item) for item in window.index),
        detected_failure_start=failure_start,
        detected_failure_end=failure_end,
    )


def _frozen_row(
    prepared: PreparedData,
    row_index: int,
    source: str,
    intervals: int,
) -> tuple[pd.DataFrame, tuple[int, ...]]:
    anchor = row_index - intervals
    if anchor < 0:
        raise ValueError("Replay row lacks enough history for the freeze transform")
    affected = tuple(range(row_index - intervals + 1, row_index + 1))
    values = prepared.raw.loc[anchor:row_index, source].copy()
    values.loc[list(affected)] = values.loc[anchor]
    row = prepared.features.loc[[row_index]].copy()
    row.loc[row_index, f"{source}_latest"] = values.loc[row_index]
    row.loc[row_index, f"{source}_lag_1"] = values.loc[row_index - 1]
    full_window = prepared.raw.loc[row_index - 4 : row_index, source].copy()
    full_window.update(values)
    row.loc[row_index, f"{source}_rolling_mean_5"] = float(full_window.mean())
    row.loc[row_index, f"{source}_rolling_std_5"] = float(full_window.std())
    return row, affected


def select_degraded_replay(
    prepared: PreparedData,
    bundle: ModelBundle,
    profile: EvidenceProfile,
    *,
    candidate_limit: int = 80,
) -> ReplayCase:
    heldout = list(prepared.heldout_indices)
    heldout_features = prepared.features.loc[heldout, list(bundle.feature_names)]
    probabilities = bundle.model.predict_proba(heldout_features)[:, 1]
    ranked = np.argsort(probabilities)[::-1][:candidate_limit]

    for rank in ranked:
        row_index = heldout[int(rank)]
        clean_row = prepared.features.loc[[row_index], list(bundle.feature_names)]
        clean = explain_row(bundle, clean_row, profile)
        clean_health = measure_source_health(
            prepared,
            profile,
            row_index,
            clean.attribution["dominant_source_id"],
        )
        if (
            clean_health.max_value_age_seconds > profile.max_value_age_seconds
            or clean_health.identical_consecutive_intervals
            >= profile.freeze_failure_consecutive_intervals
        ):
            continue
        for source in prepared.sensor_columns:
            frozen_row, affected = _frozen_row(
                prepared,
                row_index,
                source,
                profile.freeze_failure_consecutive_intervals,
            )
            degraded = explain_row(bundle, frozen_row, profile)
            if (
                degraded.attribution["dominant_source_id"] == source
                and degraded.attribution["materiality_triggered"]
            ):
                cadence = profile.expected_cadence_seconds
                fault_start = prepared.raw.loc[affected[0], "timestamp"]
                feature_end = prepared.raw.loc[row_index, "timestamp"] + pd.Timedelta(
                    seconds=cadence
                )
                feature_start = feature_end - pd.Timedelta(minutes=30)
                return ReplayCase(
                    row_index=row_index,
                    degraded_source_id=source,
                    clean=clean,
                    degraded=degraded,
                    fault_start=fault_start.isoformat(),
                    fault_end=feature_end.isoformat(),
                    feature_start=feature_start.isoformat(),
                    feature_end=feature_end.isoformat(),
                    affected_row_ids=affected,
                    max_value_age_seconds=(len(affected) * cadence),
                    identical_consecutive_intervals=len(affected),
                )
    raise ValueError(
        "No held-out replay combined a measured-healthy baseline with >=50% "
        "grouped attribution from a frozen source. Report this empirical "
        "limitation; do not fabricate a trigger."
    )


def persist_model_bundle(
    bundle: ModelBundle,
    prepared: PreparedData,
    directory: Path,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    bundle.model.save_model(directory / "model.ubj")
    manifest = {
        "dataset_sha256": prepared.dataset_sha256,
        "dataset_provenance_verified": prepared.provenance_verified,
        "split_manifest": prepared.split_manifest,
        "split_manifest_sha256": prepared.split_manifest_sha256,
        "feature_schema_sha256": bundle.feature_schema_sha256,
        "model_id": bundle.model_id,
        "model_sha256": bundle.model_sha256,
        "feature_names": list(bundle.feature_names),
        "physical_source_mapping": bundle.source_mapping,
        "explainer_id": bundle.explainer_id,
        "explainer_config_sha256": bundle.explainer_config_sha256,
        "shap_version": bundle.explainer_version,
        "xgboost_version": bundle.xgboost_version,
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
