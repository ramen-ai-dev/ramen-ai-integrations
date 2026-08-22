from __future__ import annotations

import unittest
from typing import Any

from municipal_water_degraded_telemetry.api_client import (
    EvaluationFailure,
    MunicipalWaterPolicyClient,
)
from municipal_water_degraded_telemetry.constants import POLICY_UUID


class FakeTransport:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.input_text: str | None = None
        self.policy_ids: list[str] | None = None

    def evaluate_compliance(
        self,
        input_text: str,
        *,
        policy_ids: list[str],
    ) -> dict[str, Any]:
        self.input_text = input_text
        self.policy_ids = policy_ids
        return self.result


def result(*, allowed: bool = False, verified: bool = True) -> dict[str, Any]:
    violations = (
        []
        if allowed
        else [
            {
                "reasoning": "Dominant source failed its aligned health gate.",
                "recovery_instruction": "Use independent evidence or a validated fallback.",
            }
        ]
    )
    return {
        "allowed": allowed,
        "receipt_verified": verified,
        "receipt_reason": None if verified else "bad signature",
        "receipt_alert": None,
        "policy_ids": [POLICY_UUID],
        "data": {
            "allowed": allowed,
            "total_violations": violations,
            "receipt": {"id": "30000000-0000-4000-8000-000000000003"},
        },
    }


class ApiClientTests(unittest.TestCase):
    def test_requires_verified_receipt_and_exact_policy(self) -> None:
        transport = FakeTransport(result())
        evaluation = MunicipalWaterPolicyClient(transport).evaluate("facts")
        self.assertFalse(evaluation.allowed)
        self.assertEqual(evaluation.policy_ids, (POLICY_UUID,))
        self.assertEqual(transport.policy_ids, [POLICY_UUID])

    def test_rejects_unverified_receipt(self) -> None:
        with self.assertRaisesRegex(EvaluationFailure, "Receipt verification"):
            MunicipalWaterPolicyClient(FakeTransport(result(verified=False))).evaluate(
                "facts"
            )

    def test_rejects_duplicate_policy_resolution(self) -> None:
        payload = result()
        payload["policy_ids"] = [POLICY_UUID, POLICY_UUID]
        with self.assertRaisesRegex(EvaluationFailure, "exactly once"):
            MunicipalWaterPolicyClient(FakeTransport(payload)).evaluate("facts")

    def test_rejects_unsigned_receipt_alert(self) -> None:
        payload = result()
        payload["receipt_alert"] = "signing unavailable"
        with self.assertRaisesRegex(EvaluationFailure, "unsigned-receipt"):
            MunicipalWaterPolicyClient(FakeTransport(payload)).evaluate("facts")


if __name__ == "__main__":
    unittest.main()
