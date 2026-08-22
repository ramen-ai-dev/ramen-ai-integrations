from __future__ import annotations

import unittest

from municipal_water_degraded_telemetry.canonical import canonical_json, canonical_sha256


class CanonicalTests(unittest.TestCase):
    def test_key_order_does_not_change_hash(self) -> None:
        left = {"z": 1, "a": {"y": 2, "b": 3}}
        right = {"a": {"b": 3, "y": 2}, "z": 1}
        self.assertEqual(canonical_json(left), canonical_json(right))
        self.assertEqual(canonical_sha256(left), canonical_sha256(right))

    def test_rejects_non_finite_numbers(self) -> None:
        with self.assertRaises(ValueError):
            canonical_json({"value": float("nan")})


if __name__ == "__main__":
    unittest.main()
