from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .canonical import canonical_sha256
from .constants import DEFAULT_PROFILE_PATH


@dataclass(frozen=True)
class EvidenceProfile:
    raw: dict[str, Any]
    sha256: str
    profile_id: str
    profile_version: str
    registry_scope: str
    action_profile_id: str
    dataset_id: str
    materiality_threshold: float
    expected_cadence_seconds: int
    max_value_age_seconds: int
    freeze_failure_consecutive_intervals: int
    feature_window_coverage_required: float
    health_profile_id: str
    common_mode_dimensions: tuple[str, ...]


def load_profile(path: Path = DEFAULT_PROFILE_PATH) -> EvidenceProfile:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot load evidence profile {path}: {exc}") from exc

    if raw.get("schema") != "ramen.mwdta.evidence-profile.v1":
        raise ValueError("Unsupported evidence profile schema")
    if raw.get("registry_scope") != "integration_demo_local":
        raise ValueError("Evidence profile must remain integration_demo_local")

    materiality = raw.get("materiality", {})
    health = raw.get("health", {})
    corroboration = raw.get("corroboration", {})
    if materiality.get("comparator") != "gte":
        raise ValueError("Demo profile requires the explicit gte comparator")
    threshold = float(materiality.get("threshold", -1.0))
    if not 0.0 < threshold <= 1.0:
        raise ValueError("Materiality threshold must be in (0, 1]")

    return EvidenceProfile(
        raw=raw,
        sha256=canonical_sha256(raw),
        profile_id=str(raw["profile_id"]),
        profile_version=str(raw["profile_version"]),
        registry_scope=str(raw["registry_scope"]),
        action_profile_id=str(raw["action_profile_id"]),
        dataset_id=str(raw["dataset_id"]),
        materiality_threshold=threshold,
        expected_cadence_seconds=int(health["expected_cadence_seconds"]),
        max_value_age_seconds=int(health["max_value_age_seconds"]),
        freeze_failure_consecutive_intervals=int(
            health["freeze_failure_consecutive_intervals"]
        ),
        feature_window_coverage_required=float(
            health["feature_window_coverage_required"]
        ),
        health_profile_id=str(health["health_profile_id"]),
        common_mode_dimensions=tuple(corroboration["common_mode_dimensions"]),
    )
