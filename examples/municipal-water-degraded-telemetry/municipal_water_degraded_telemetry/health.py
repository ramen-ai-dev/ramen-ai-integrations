from __future__ import annotations

from datetime import datetime
from typing import Any

from .canonical import canonical_sha256
from .profile import EvidenceProfile


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Health timestamps must include a UTC offset")
    return parsed


def intervals_overlap(
    first_start: str,
    first_end: str,
    second_start: str,
    second_end: str,
) -> bool:
    a_start, a_end = _parse_utc(first_start), _parse_utc(first_end)
    b_start, b_end = _parse_utc(second_start), _parse_utc(second_end)
    if a_start >= a_end or b_start >= b_end:
        raise ValueError("Intervals must be non-empty half-open intervals")
    return a_start < b_end and b_start < a_end


def build_health_evidence(
    *,
    profile: EvidenceProfile,
    source_id: str,
    feature_start: str,
    feature_end: str,
    generated_at: str,
    fault_start: str | None,
    fault_end: str | None,
    max_value_age_seconds: int,
    identical_consecutive_intervals: int,
    affected_row_ids: list[int],
    window_coverage: float = 1.0,
) -> dict[str, Any]:
    overlap = False
    if (fault_start is None) != (fault_end is None):
        raise ValueError("Fault interval must supply both start and end")
    if fault_start is not None and fault_end is not None:
        overlap = intervals_overlap(feature_start, feature_end, fault_start, fault_end)

    manifest = {
        "physical_source_id": source_id,
        "transform": "freeze" if fault_start is not None else "none",
        "fault_start": fault_start,
        "fault_end": fault_end,
        "expected_cadence_seconds": profile.expected_cadence_seconds,
        "observed_maximum_age_seconds": max_value_age_seconds,
        "observed_identical_interval_count": identical_consecutive_intervals,
        "feature_window_overlap": overlap,
        "affected_row_ids": affected_row_ids,
    }
    coverage_ok = window_coverage >= profile.feature_window_coverage_required
    stale = max_value_age_seconds > profile.max_value_age_seconds
    frozen = (
        identical_consecutive_intervals
        >= profile.freeze_failure_consecutive_intervals
    )
    failed = coverage_ok and overlap and (stale or frozen)
    status = "FAILED" if failed else "PASSED" if coverage_ok else "UNKNOWN"
    failure_modes = [
        mode
        for mode, active in (("freeze", frozen), ("staleness", stale))
        if active and overlap
    ]
    return {
        "health_profile_id": profile.health_profile_id,
        "authority": "deterministic_demo_injection_manifest",
        "record_generated_at": generated_at,
        "window_coverage": window_coverage,
        "source_id": source_id,
        "status": status,
        "failure_modes": failure_modes,
        "fault_interval": {"start": fault_start, "end": fault_end},
        "overlaps_feature_window": overlap,
        "max_value_age_seconds": max_value_age_seconds,
        "identical_consecutive_intervals": identical_consecutive_intervals,
        "health_manifest_sha256": canonical_sha256(manifest),
    }
