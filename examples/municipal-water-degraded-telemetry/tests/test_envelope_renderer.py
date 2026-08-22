from __future__ import annotations

import unittest

from municipal_water_degraded_telemetry.envelope import verify_envelope_hash
from municipal_water_degraded_telemetry.renderer import render_evidence

from tests.helpers import sample_envelope


class EnvelopeRendererTests(unittest.TestCase):
    def test_finalized_envelope_hash_verifies(self) -> None:
        self.assertTrue(verify_envelope_hash(sample_envelope()))

    def test_renderer_is_byte_stable_and_does_not_supply_verdict(self) -> None:
        envelope = sample_envelope()
        first = render_evidence(envelope)
        second = render_evidence(envelope)
        self.assertEqual(first, second)
        self.assertIn("share:0.750000", first)
        self.assertIn("reports FAILED", first)
        self.assertNotIn("therefore BLOCK", first)
        self.assertNotIn("expected_allowed", first)
        self.assertTrue(first.endswith(f"{envelope['envelope_sha256']}."))

    def test_renderer_rejects_tampered_envelope(self) -> None:
        envelope = sample_envelope()
        envelope["decision_context"]["urgency"] = "emergency"
        with self.assertRaisesRegex(ValueError, "hash"):
            render_evidence(envelope)


if __name__ == "__main__":
    unittest.main()
