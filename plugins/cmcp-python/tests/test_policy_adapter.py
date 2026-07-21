"""Tests for ramen_cmcp.policy_adapter.RamenCmcpAdapter.

All HTTP calls are intercepted by pytest-httpx so no network or real API key
is required.  The response fixtures mirror the V5 production envelope shape
from v5-conformance.md §2.
"""
from __future__ import annotations

import json

import pytest
from pytest_httpx import HTTPXMock

from ramen_cmcp.policy_adapter import RamenCmcpAdapter, AdapterDecision

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

API_URL = "https://api.ramenai.dev/api/v1/paas/evaluate"

ALLOWED_RESPONSE = {
    "success": True,
    "data": {
        "allowed": True,
        "policy_ids": ["f47ac10b-58cc-4372-a567-0e02b2c3d479"],
        "policies_evaluated": 1,
        "policies_passed": 1,
        "policies_failed": 0,
        "policies_errored": 0,
        "total_violations": [],
        "results": [
            {
                "policy_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "policy_name": "Test Policy",
                "status": "fulfilled",
                "allowed": True,
                "violations": [],
                "rules_checked": 2,
                "statutory_anchors": ["FCA COBS 4.2.1"],
            }
        ],
        "execution_time_ms": 12,
        "executed_at": "2026-06-20T09:00:00.000Z",
        "statutory_anchors": ["FCA COBS 4.2.1"],
        "receipt": {
            "id": "11111111-1111-4111-8111-111111111111",
            "schema_version": "5.0",
            "kid": "ramen_pk_ephemeral_test",
            "signature": "86rTO8547URmP0M-k0AEHbjSjz2ASRndoRrAFKrtrQJvsPbiAfn6rqEbuQrf4rtNFYq4klVhcHrXqtjRcoC2Ag",
            "canonical_payload": (
                '{"schema_version":"5.0","kid":"ramen_pk_ephemeral_test",'
                '"id":"11111111-1111-4111-8111-111111111111",'
                '"timestamp":"2026-06-20T09:00:00.000Z",'
                '"policy_ids":["f47ac10b-58cc-4372-a567-0e02b2c3d479"],'
                '"payload_hash":"adb09112ff437c97a89b17e2dcba478b0c1ebbf2331fa4e5d216f10085eeff21",'
                '"verdict":1,"reasoning":"","steering":"",'
                '"statutory_anchors":["FCA COBS 4.2.1"]}'
            ),
            "statutory_anchors": ["FCA COBS 4.2.1"],
        },
    },
}

DENIED_RESPONSE = {
    "success": True,
    "data": {
        "allowed": False,
        "policy_ids": ["b94f3c1d-e2a6-4c89-8d02-f5a12b3c4d56"],
        "policies_evaluated": 1,
        "policies_passed": 0,
        "policies_failed": 1,
        "policies_errored": 0,
        "total_violations": [
            {
                "rule_id": "c1d2e3f4-a5b6-7890-cdef-012345678901",
                "rule_name": "No Specific Investment Advice",
                "rule_content": "Do not provide specific investment recommendations.",
                "enforcement_level": "strict",
                "reasoning": "Solicits derivative advice.",
                "recovery_instruction": "Redirect to a regulated financial advisor.",
            }
        ],
        "results": [
            {
                "policy_id": "b94f3c1d-e2a6-4c89-8d02-f5a12b3c4d56",
                "policy_name": "Test Policy",
                "status": "rejected",
                "allowed": False,
                "violations": [],
                "rules_checked": 2,
            }
        ],
        "execution_time_ms": 18,
        "executed_at": "2026-06-20T09:01:00.000Z",
        "receipt": {
            "id": "22222222-2222-4222-8222-222222222222",
            "schema_version": "5.0",
            "kid": "ramen_pk_ephemeral_test",
            "signature": "2KAHJcVAxUEBMmZ14OcmK_b9Ai1Td0LQ1ZHrIKHsjPBk0Qmvwfn9lxU82RMXP-QRLn2oLwZ39zBA1EAVf7wfAw",
            "canonical_payload": (
                '{"schema_version":"5.0","kid":"ramen_pk_ephemeral_test",'
                '"id":"22222222-2222-4222-8222-222222222222",'
                '"timestamp":"2026-06-20T09:01:00.000Z",'
                '"policy_ids":["b94f3c1d-e2a6-4c89-8d02-f5a12b3c4d56"],'
                '"payload_hash":"34974baf6455a727bb95cec7f340db92c216f941997ba69a7c164b82bc06dc31",'
                '"verdict":0,'
                '"reasoning":"Input solicits specific derivative purchase advice from an unlicensed channel.",'
                '"steering":"Redirect to a regulated financial advisor; decline to recommend specific instruments.",'
                '"statutory_anchors":["FCA PRIN 2A.2.8","MiFID II Art. 25"]}'
            ),
            "statutory_anchors": ["FCA PRIN 2A.2.8", "MiFID II Art. 25"],
        },
    },
}

NO_RECEIPT_RESPONSE = {
    "success": True,
    "data": {
        "allowed": True,
        "policy_ids": ["f47ac10b-58cc-4372-a567-0e02b2c3d479"],
        "policies_evaluated": 1,
        "policies_passed": 1,
        "policies_failed": 0,
        "policies_errored": 0,
        "total_violations": [],
        "results": [],
        "execution_time_ms": 5,
        "executed_at": "2026-06-20T09:00:00.000Z",
        "receipt_alert": "RECEIPT_SIGNING_FAILED: evaluation verdict is valid but UNVERIFIABLE",
    },
}

# A minimal cMCP JSON-RPC tool-call payload
TOOL_CALL = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "salesforce.contacts",
        "arguments": {"query": "Acme Corp"},
        "_cmcp": {"session_id": "s1", "workflow_id": "demo-agent"},
    },
}


def _make_adapter(**kwargs) -> RamenCmcpAdapter:
    return RamenCmcpAdapter(
        api_key="ramen_ak_test",
        bundle_ids=["ramen__shield_core_it"],
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------

class TestAdapterConstructor:
    def test_requires_api_key(self, monkeypatch):
        monkeypatch.delenv("RAMEN_API_KEY", raising=False)
        with pytest.raises(ValueError, match="api_key"):
            RamenCmcpAdapter(api_key="", bundle_ids=["ramen__shield_core_it"])

    def test_requires_bundle_or_policy_ids(self):
        with pytest.raises(ValueError, match="bundle_ids"):
            RamenCmcpAdapter(api_key="ramen_ak_test")

    def test_accepts_policy_ids_alone(self):
        adapter = RamenCmcpAdapter(
            api_key="ramen_ak_test",
            policy_ids=["f47ac10b-58cc-4372-a567-0e02b2c3d479"],
        )
        adapter.close()


# ---------------------------------------------------------------------------
# Payload extraction
# ---------------------------------------------------------------------------

class TestPayloadExtraction:
    def test_missing_tool_name_raises(self):
        adapter = _make_adapter()
        bad_payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {}}
        with pytest.raises(ValueError, match="params.name"):
            adapter.evaluate(bad_payload)
        adapter.close()

    def test_input_text_is_sorted_json(self, httpx_mock: HTTPXMock):
        """The API must receive a JSON object with tool + sorted arguments."""
        httpx_mock.add_response(url=API_URL, json=ALLOWED_RESPONSE)
        adapter = _make_adapter()
        adapter.evaluate(TOOL_CALL)
        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        parsed = json.loads(body["input"])
        assert parsed["tool"] == "salesforce.contacts"
        assert parsed["arguments"] == {"query": "Acme Corp"}
        adapter.close()

    def test_cmcp_fields_forwarded_as_context(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(url=API_URL, json=ALLOWED_RESPONSE)
        adapter = _make_adapter()
        adapter.evaluate(TOOL_CALL)
        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        assert body["context"]["session_id"] == "s1"
        assert body["context"]["workflow_id"] == "demo-agent"
        assert body["context"]["tool_name"] == "salesforce.contacts"
        adapter.close()


# ---------------------------------------------------------------------------
# Allow decision
# ---------------------------------------------------------------------------

class TestAllowDecision:
    @pytest.fixture
    def decision(self, httpx_mock: HTTPXMock) -> AdapterDecision:
        httpx_mock.add_response(url=API_URL, json=ALLOWED_RESPONSE)
        with _make_adapter() as adapter:
            return adapter.evaluate(TOOL_CALL)

    def test_allowed_is_true(self, decision):
        assert decision.allowed is True

    def test_deny_message_is_none(self, decision):
        assert decision.deny_message is None

    def test_receipt_is_present(self, decision):
        assert decision.receipt is not None
        assert decision.receipt["id"] == "11111111-1111-4111-8111-111111111111"

    def test_policy_ids_populated(self, decision):
        assert "f47ac10b-58cc-4372-a567-0e02b2c3d479" in decision.policy_ids

    def test_statutory_anchors_populated(self, decision):
        assert "FCA COBS 4.2.1" in decision.statutory_anchors


# ---------------------------------------------------------------------------
# Deny decision
# ---------------------------------------------------------------------------

class TestDenyDecision:
    @pytest.fixture
    def decision(self, httpx_mock: HTTPXMock) -> AdapterDecision:
        httpx_mock.add_response(url=API_URL, json=DENIED_RESPONSE)
        with _make_adapter() as adapter:
            return adapter.evaluate(TOOL_CALL)

    def test_allowed_is_false(self, decision):
        assert decision.allowed is False

    def test_deny_message_starts_with_denied(self, decision):
        assert decision.deny_message is not None
        assert decision.deny_message.startswith("[DENIED]")

    def test_deny_message_contains_steering(self, decision):
        assert "Redirect to a regulated financial advisor" in decision.deny_message

    def test_receipt_present_on_deny(self, decision):
        assert decision.receipt is not None
        assert decision.receipt["id"] == "22222222-2222-4222-8222-222222222222"

    def test_steering_attribute_set(self, decision):
        assert decision.steering is not None
        assert "Redirect" in decision.steering


# ---------------------------------------------------------------------------
# No-receipt / signing failure (M-1 vector)
# ---------------------------------------------------------------------------

class TestNoReceiptCase:
    @pytest.fixture
    def decision(self, httpx_mock: HTTPXMock) -> AdapterDecision:
        httpx_mock.add_response(url=API_URL, json=NO_RECEIPT_RESPONSE)
        with _make_adapter() as adapter:
            return adapter.evaluate(TOOL_CALL)

    def test_allowed_still_true(self, decision):
        assert decision.allowed is True

    def test_receipt_is_none(self, decision):
        assert decision.receipt is None

    def test_receipt_verified_is_false(self, decision):
        assert decision.receipt_verified is False

    def test_receipt_alert_is_present(self, decision):
        assert decision.receipt_alert is not None
        assert "RECEIPT_SIGNING_FAILED" in decision.receipt_alert


# ---------------------------------------------------------------------------
# Context-manager protocol
# ---------------------------------------------------------------------------

class TestContextManager:
    def test_context_manager_closes_cleanly(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(url=API_URL, json=ALLOWED_RESPONSE)
        with _make_adapter() as adapter:
            decision = adapter.evaluate(TOOL_CALL)
        assert decision.allowed is True
