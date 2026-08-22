from __future__ import annotations

import unittest

from municipal_water_degraded_telemetry.health import build_health_evidence, intervals_overlap
from municipal_water_degraded_telemetry.profile import load_profile


class HealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_profile()

    def test_half_open_intervals_do_not_overlap_at_boundary(self) -> None:
        self.assertFalse(
            intervals_overlap(
                "2026-08-10T10:00:00+00:00",
                "2026-08-10T10:30:00+00:00",
                "2026-08-10T10:30:00+00:00",
                "2026-08-10T10:40:00+00:00",
            )
        )

    def test_overlapping_freeze_fails_authoritative_gate(self) -> None:
        evidence = build_health_evidence(
            profile=self.profile,
            source_id="sensor_04",
            feature_start="2026-08-10T10:00:00+00:00",
            feature_end="2026-08-10T10:30:00+00:00",
            generated_at="2026-08-10T10:30:00+00:00",
            fault_start="2026-08-10T10:27:00+00:00",
            fault_end="2026-08-10T10:30:00+00:00",
            max_value_age_seconds=180,
            identical_consecutive_intervals=3,
            affected_row_ids=[27, 28, 29],
        )
        self.assertEqual(evidence["status"], "FAILED")
        self.assertEqual(evidence["failure_modes"], ["freeze", "staleness"])

    def test_partial_window_is_unknown(self) -> None:
        evidence = build_health_evidence(
            profile=self.profile,
            source_id="sensor_04",
            feature_start="2026-08-10T10:00:00+00:00",
            feature_end="2026-08-10T10:30:00+00:00",
            generated_at="2026-08-10T10:30:00+00:00",
            fault_start=None,
            fault_end=None,
            max_value_age_seconds=0,
            identical_consecutive_intervals=1,
            affected_row_ids=[],
            window_coverage=0.5,
        )
        self.assertEqual(evidence["status"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
