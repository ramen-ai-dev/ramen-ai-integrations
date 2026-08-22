from __future__ import annotations

import unittest

from municipal_water_degraded_telemetry.attribution import aggregate_attributions


class AttributionTests(unittest.TestCase):
    def test_groups_all_descendants_by_physical_source(self) -> None:
        result = aggregate_attributions(
            ["s1_latest", "s1_lag", "s2_latest"],
            [0.25, -0.35, 0.20],
            {
                "s1_latest": "s1",
                "s1_lag": "s1",
                "s2_latest": "s2",
            },
            0.5,
        )
        self.assertAlmostEqual(result["total_absolute_shap"], 0.8)
        self.assertEqual(result["dominant_source_id"], "s1")
        self.assertAlmostEqual(result["dominant_source_share"], 0.75)
        self.assertTrue(result["materiality_triggered"])

    def test_rejects_missing_source_lineage(self) -> None:
        with self.assertRaisesRegex(ValueError, "lacks physical-source lineage"):
            aggregate_attributions(["unknown"], [1.0], {}, 0.5)

    def test_rejects_zero_denominator(self) -> None:
        with self.assertRaisesRegex(ValueError, "denominator"):
            aggregate_attributions(["s1"], [0.0], {"s1": "s1"}, 0.5)


if __name__ == "__main__":
    unittest.main()
