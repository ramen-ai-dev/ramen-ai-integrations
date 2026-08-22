from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from municipal_water_degraded_telemetry.canonical import sha256_bytes
from municipal_water_degraded_telemetry.data_pipeline import (
    explain_row,
    prepare_dataset,
    select_degraded_replay,
    train_model,
)
from municipal_water_degraded_telemetry.profile import load_profile
from municipal_water_degraded_telemetry.runner import _build_scenarios


class DataPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_profile()

    def _frame(self) -> pd.DataFrame:
        row_count = 700
        events = np.array([100, 170, 240, 310, 380, 450, 520, 590, 660])
        indices = np.arange(row_count)
        distance = np.min(np.abs(indices[:, None] - events[None, :]), axis=1)
        rng = np.random.default_rng(2026)
        status = np.full(row_count, "NORMAL", dtype=object)
        status[events] = "RECOVERING"
        return pd.DataFrame(
            {
                "timestamp": pd.date_range(
                    "2026-01-01T00:00:00Z", periods=row_count, freq="min"
                ),
                "machine_status": status,
                "sensor_00": np.maximum(0.0, 35.0 - distance)
                + rng.normal(0.0, 0.2, row_count),
                "sensor_01": rng.normal(0.0, 1.0, row_count),
            }
        )

    def _prepare(self, frame: pd.DataFrame):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "sensor.csv"
        frame.to_csv(path, index=False)
        return prepare_dataset(
            path,
            self.profile,
            max_sources=2,
            expected_dataset_sha256=sha256_bytes(path.read_bytes()),
        )

    def test_trains_xgboost_and_computes_authentic_treeshap(self) -> None:
        prepared = self._prepare(self._frame())
        bundle = train_model(prepared)
        positive_heldout = [
            index
            for index in prepared.heldout_indices
            if bool(prepared.target.loc[index])
        ]
        self.assertTrue(positive_heldout)
        row = prepared.features.loc[[positive_heldout[0]], list(bundle.feature_names)]
        evidence = explain_row(bundle, row, self.profile)

        self.assertTrue(prepared.provenance_verified)
        self.assertEqual(len(evidence.shap_values), len(bundle.feature_names))
        self.assertGreater(evidence.attribution["total_absolute_shap"], 0.0)
        self.assertAlmostEqual(
            sum(item["share"] for item in evidence.attribution["source_aggregates"]),
            1.0,
        )
        self.assertGreaterEqual(evidence.probability, 0.0)
        self.assertLessEqual(evidence.probability, 1.0)

    def test_builds_all_governance_scenarios_with_independent_fallback(self) -> None:
        prepared = self._prepare(self._frame())
        bundle = train_model(prepared)
        replay = select_degraded_replay(
            prepared, bundle, self.profile, candidate_limit=120
        )
        scenarios, fallback_bundle, proof = _build_scenarios(
            self.profile, prepared, bundle, replay
        )
        by_name = {scenario.name: scenario for scenario in scenarios}

        self.assertEqual(
            set(by_name),
            {
                "healthy-baseline",
                "degraded-rural-original",
                "degraded-bridge-original",
                "missing-untrusted-evidence",
                "source-excluding-fallback",
            },
        )
        self.assertTrue(by_name["healthy-baseline"].expected_allowed)
        self.assertFalse(by_name["degraded-rural-original"].expected_allowed)
        self.assertFalse(by_name["degraded-bridge-original"].expected_allowed)
        self.assertEqual(
            by_name["missing-untrusted-evidence"].local_disposition,
            "REVIEW_REQUIRED",
        )
        rural = by_name["degraded-rural-original"].envelope
        bridge = by_name["degraded-bridge-original"].envelope
        self.assertEqual(rural["attribution"], bridge["attribution"])
        self.assertEqual(rural["sensor_health"], bridge["sensor_health"])
        fallback = by_name["source-excluding-fallback"].envelope
        self.assertEqual(fallback["sensor_health"]["status"], "PASSED")
        self.assertEqual(
            fallback["corroboration"]["gate"],
            "NOT_REQUIRED_HEALTHY_SOURCE",
        )
        self.assertNotEqual(
            fallback_bundle.feature_schema_sha256,
            bundle.feature_schema_sha256,
        )
        self.assertFalse(
            set(proof["excluded_descendants"])
            & set(proof["fallback_feature_names"])
        )

    def test_rejects_unapproved_dataset_digest(self) -> None:
        frame = self._frame()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sensor.csv"
            frame.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "operator-approved"):
                prepare_dataset(
                    path,
                    self.profile,
                    expected_dataset_sha256="0" * 64,
                )

    def test_rejects_timestamp_gap_even_when_median_is_one_minute(self) -> None:
        frame = self._frame()
        frame.loc[350:, "timestamp"] = frame.loc[350:, "timestamp"] + pd.Timedelta(
            minutes=1
        )
        with self.assertRaisesRegex(ValueError, "Every adjacent timestamp"):
            self._prepare(frame)

    def test_rejects_unknown_machine_state(self) -> None:
        frame = self._frame()
        frame.loc[10, "machine_status"] = "UNRECOGNIZED"
        with self.assertRaisesRegex(ValueError, "unsupported machine states"):
            self._prepare(frame)


if __name__ == "__main__":
    unittest.main()
