from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from showcase_pipeline import (
    GovernanceDeniedException,
    _required_policy_uuid,
    _verified_policy_alert,
)

POLICY_UUID = "0d5ed2af-5e98-4a8c-92c3-dea26c07bf9a"


class EnvironmentValidationTests(unittest.TestCase):
    def test_accepts_enterprise_environment_without_provider_key(self) -> None:
        environment = {
            "RAMEN_API_KEY": "ramen_ak_test",
            "RAMEN_POLICY_UUID": POLICY_UUID,
        }
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(_required_policy_uuid(), POLICY_UUID)

    def test_rejects_credential_placeholders(self) -> None:
        environment = {
            "RAMEN_API_KEY": "ramen_ak_test",
            "OPENAI_API_KEY": "sk-...",
            "RAMEN_POLICY_UUID": POLICY_UUID,
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                _required_policy_uuid()


class VerifiedPolicyAlertTests(unittest.TestCase):
    def _exception(
        self,
        *,
        receipt_verified: bool,
        policy_ids: list[str],
    ) -> GovernanceDeniedException:
        return GovernanceDeniedException(
            steering="Remove postcode from the model.",
            receipt_verified=receipt_verified,
            statutory_anchors=["EU AI Act Annex III"],
            policy_ids=policy_ids,
            receipt={"version": "v5"},
        )

    def test_renders_verified_matching_policy_denial(self) -> None:
        alert = _verified_policy_alert(
            self._exception(
                receipt_verified=True,
                policy_ids=[POLICY_UUID],
            ),
            POLICY_UUID,
        )
        self.assertIn("[x] Verdict: BLOCKED", alert)
        self.assertIn("Receipt Verified (Ed25519)", alert)

    def test_rejects_unverified_denial(self) -> None:
        with self.assertRaisesRegex(ValueError, "verified receipt"):
            _verified_policy_alert(
                self._exception(
                    receipt_verified=False,
                    policy_ids=[POLICY_UUID],
                ),
                POLICY_UUID,
            )

    def test_rejects_wrong_policy_denial(self) -> None:
        with self.assertRaisesRegex(ValueError, "configured policy"):
            _verified_policy_alert(
                self._exception(
                    receipt_verified=True,
                    policy_ids=["11111111-1111-4111-8111-111111111111"],
                ),
                POLICY_UUID,
            )


if __name__ == "__main__":
    unittest.main()
