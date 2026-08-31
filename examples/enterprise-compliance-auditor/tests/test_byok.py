from __future__ import annotations

import os
import unittest
from typing import Any
from unittest.mock import patch

import auditor
import ciso_dashboard


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def evaluate_compliance(self, input_text: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"input_text": input_text, **kwargs})
        return {
            "allowed": True,
            "receipt_verified": True,
            "receipt_reason": None,
            "receipt_alert": None,
            "steering": None,
            "data": {
                "allowed": True,
                "policy_ids": ["policy-test"],
                "total_violations": [],
                "results": [],
                "receipt": {
                    "kid": "test-kid",
                    "signature": "test-signature",
                },
            },
        }


class ProviderCredentialTests(unittest.TestCase):
    def test_normalises_managed_provider_environments(self) -> None:
        for module in (auditor, ciso_dashboard):
            for environment in ({}, {"OPENAI_API_KEY": "   "}, {"OPENAI_API_KEY": "sk-..."}):
                with self.subTest(module=module.__name__, environment=environment):
                    with patch.dict(os.environ, environment, clear=True):
                        self.assertEqual(module._provider_credentials(), (None, None))

    def test_normalises_openai_byok_environment(self) -> None:
        for module in (auditor, ciso_dashboard):
            with self.subTest(module=module.__name__):
                with patch.dict(
                    os.environ,
                    {"OPENAI_API_KEY": "test-provider-key"},
                    clear=True,
                ):
                    self.assertEqual(
                        module._provider_credentials(),
                        ("test-provider-key", "openai"),
                    )

    def test_historical_evaluation_supports_managed_and_byok_modes(self) -> None:
        log = auditor.load_logs()[0]

        managed_client = FakeClient()
        managed_result = auditor.evaluate_log(managed_client, "policy-test", log)
        self.assertIsNone(managed_result.evidence_error)
        self.assertIsNone(managed_client.calls[0]["provider_key"])
        self.assertIsNone(managed_client.calls[0]["provider_name"])

        byok_client = FakeClient()
        byok_result = auditor.evaluate_log(
            byok_client,
            "policy-test",
            log,
            provider_key="test-provider-key",
            provider_name="openai",
        )
        self.assertIsNone(byok_result.evidence_error)
        self.assertEqual(byok_client.calls[0]["provider_key"], "test-provider-key")
        self.assertEqual(byok_client.calls[0]["provider_name"], "openai")

    def test_historical_executor_forwards_byok(self) -> None:
        client = FakeClient()
        results = auditor.run_audit(
            client,
            "policy-test",
            [auditor.load_logs()[0]],
            provider_key="test-provider-key",
            provider_name="openai",
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(client.calls[0]["provider_key"], "test-provider-key")
        self.assertEqual(client.calls[0]["provider_name"], "openai")

    def test_dashboard_evaluation_supports_managed_and_byok_modes(self) -> None:
        tool_call = ciso_dashboard.load_tool_calls()[0]
        scope = {"bundle_ids": [ciso_dashboard.DEFAULT_BUNDLE_ID]}

        managed_client = FakeClient()
        managed_result = ciso_dashboard.evaluate_tool_call(
            managed_client,
            scope,
            tool_call,
        )
        self.assertIsNone(managed_result.evidence_error)
        self.assertIsNone(managed_client.calls[0]["provider_key"])
        self.assertIsNone(managed_client.calls[0]["provider_name"])

        byok_client = FakeClient()
        byok_result = ciso_dashboard.evaluate_tool_call(
            byok_client,
            scope,
            tool_call,
            provider_key="test-provider-key",
            provider_name="openai",
        )
        self.assertIsNone(byok_result.evidence_error)
        self.assertEqual(byok_client.calls[0]["provider_key"], "test-provider-key")
        self.assertEqual(byok_client.calls[0]["provider_name"], "openai")

    def test_dashboard_executor_forwards_byok(self) -> None:
        client = FakeClient()
        results = ciso_dashboard.run_evaluations(
            client,
            {"bundle_ids": [ciso_dashboard.DEFAULT_BUNDLE_ID]},
            [ciso_dashboard.load_tool_calls()[0]],
            1,
            lambda result: None,
            provider_key="test-provider-key",
            provider_name="openai",
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(client.calls[0]["provider_key"], "test-provider-key")
        self.assertEqual(client.calls[0]["provider_name"], "openai")


if __name__ == "__main__":
    unittest.main()
