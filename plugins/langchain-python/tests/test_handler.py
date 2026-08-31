"""
Unit tests for RamenSafetyCallbackHandler.

Coverage
--------
- ALLOWED verdict: on_tool_start returns without raising.
- BLOCKED verdict: on_tool_start raises RamenSafetyException with correct fields.
- Transport failure: network error is caught and re-raised as RamenSafetyException
  (fail-closed behaviour).
- Unverifiable receipt escalation: ALLOWED verdict + unverified receipt raises
  when require_receipt_verified=True (default), passes when False.
- Constructor guard: ValueError when neither bundle_ids nor policy_ids supplied.
- Payload construction: the JSON body sent to the API contains tool name,
  description, and input_str.
- Context propagation: tool_name and run_id appear in the context dict.

All tests use pytest-httpx to intercept HTTP calls at the transport layer so no
live API key is required.
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import httpx
import pytest
from pytest_httpx import HTTPXMock

from ramen_langchain import RamenSafetyCallbackHandler, RamenSafetyException

# ---------------------------------------------------------------------------
# Shared fixtures & helpers
# ---------------------------------------------------------------------------

API_KEY = "ramen_ak_test"
BUNDLE = ["ramen__shield_core_it"]
RUN_ID = uuid4()

SERIALIZED_TOOL = {
    "name": "drop_database_table",
    "description": "Drop a production database table.",
}
INPUT_STR = "drop users_prod immediately"


def _make_handler(**kwargs) -> RamenSafetyCallbackHandler:
    defaults = dict(api_key=API_KEY, bundle_ids=BUNDLE)
    defaults.update(kwargs)
    return RamenSafetyCallbackHandler(**defaults)


def _evaluate_response(
    *,
    allowed: bool,
    steering: str | None = None,
    receipt: dict | None = None,
    receipt_alert: str | None = None,
    statutory_anchors: list[str] | None = None,
) -> dict:
    """Build a minimal valid /api/v1/paas/evaluate response envelope."""
    return {
        "data": {
            "allowed": allowed,
            "policy_ids": ["6c787849-96db-4c92-8df9-10aa8d035527"],
            "policies_evaluated": 1,
            "policies_passed": 1 if allowed else 0,
            "policies_failed": 0 if allowed else 1,
            "policies_errored": 0,
            "total_violations": (
                []
                if allowed
                else [
                    {
                        "rule_id": "r1",
                        "rule_name": "Destructive Execution",
                        "rule_content": "No destructive DB ops",
                        "enforcement_level": "strict",
                        "recovery_instruction": steering or "Refuse the request.",
                    }
                ]
            ),
            "results": [],
            "execution_time_ms": 42,
            "executed_at": "2026-06-27T12:00:00.000Z",
            "statutory_anchors": statutory_anchors or [],
            "receipt": receipt,
            "receipt_alert": receipt_alert,
        }
    }


# ---------------------------------------------------------------------------
# 1. Constructor validation
# ---------------------------------------------------------------------------


def test_constructor_requires_bundle_or_policy():
    with pytest.raises(ValueError, match="bundle_ids.*policy_ids"):
        RamenSafetyCallbackHandler(api_key=API_KEY)


def test_constructor_accepts_policy_ids_only():
    handler = RamenSafetyCallbackHandler(
        api_key=API_KEY, policy_ids=["6c787849-96db-4c92-8df9-10aa8d035527"]
    )
    assert handler is not None


# ---------------------------------------------------------------------------
# 2. ALLOWED verdict — no exception raised
# ---------------------------------------------------------------------------


def test_allowed_verdict_does_not_raise(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.ramenai.dev/api/v1/paas/evaluate",
        json=_evaluate_response(allowed=True),
    )
    handler = _make_handler()
    # Should return None without raising.
    result = handler.on_tool_start(
        SERIALIZED_TOOL, INPUT_STR, run_id=RUN_ID
    )
    assert result is None


# ---------------------------------------------------------------------------
# 3. BLOCKED verdict — RamenSafetyException raised with correct fields
# ---------------------------------------------------------------------------


def test_blocked_verdict_raises_safety_exception(httpx_mock: HTTPXMock):
    anchors = ["EU AI Act Art. 5(1)(a)"]
    httpx_mock.add_response(
        url="https://api.ramenai.dev/api/v1/paas/evaluate",
        json=_evaluate_response(
            allowed=False,
            steering="Refuse destructive operations.",
            statutory_anchors=anchors,
        ),
    )
    handler = _make_handler()
    with pytest.raises(RamenSafetyException) as exc_info:
        handler.on_tool_start(SERIALIZED_TOOL, INPUT_STR, run_id=RUN_ID)

    exc = exc_info.value
    assert exc.tool_name == "drop_database_table"
    assert exc.steering == "Refuse destructive operations."
    assert exc.statutory_anchors == anchors
    # No receipt in response → receipt_verified is False.
    assert exc.receipt_verified is False


# ---------------------------------------------------------------------------
# 4. Fail-closed: transport error raises RamenSafetyException
# ---------------------------------------------------------------------------


def test_transport_error_raises_fail_closed(httpx_mock: HTTPXMock):
    httpx_mock.add_exception(
        httpx.ConnectError("Connection refused"),
        url="https://api.ramenai.dev/api/v1/paas/evaluate",
    )
    handler = _make_handler()
    with pytest.raises(RamenSafetyException) as exc_info:
        handler.on_tool_start(SERIALIZED_TOOL, INPUT_STR, run_id=RUN_ID)

    exc = exc_info.value
    assert exc.tool_name == "drop_database_table"
    assert "fail-closed" in str(exc).lower() or "could not complete" in str(exc).lower()
    # Original exception chained as __cause__.
    assert exc.__cause__ is not None


def test_http_error_raises_fail_closed(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.ramenai.dev/api/v1/paas/evaluate",
        status_code=502,
    )
    handler = _make_handler()
    with pytest.raises(RamenSafetyException):
        handler.on_tool_start(SERIALIZED_TOOL, INPUT_STR, run_id=RUN_ID)


# ---------------------------------------------------------------------------
# 5. Unverifiable receipt escalation
# ---------------------------------------------------------------------------


def test_allowed_with_unverifiable_receipt_escalates_by_default(httpx_mock: HTTPXMock):
    """
    ALLOWED + receipt present + receipt fails local verification
    → should raise when require_receipt_verified=True (default).

    We trigger this by supplying a receipt with an invalid signature so the
    verifier rejects it, while the API verdict says allowed=True.
    """
    bad_receipt = {
        "id": "11111111-1111-4111-8111-111111111111",
        "schema_version": "5.0",
        "kid": "ramen_pk_v1",
        "signature": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        "canonical_payload": '{"schema_version":"5.0","payload_hash":"fake"}',
    }
    httpx_mock.add_response(
        url="https://api.ramenai.dev/api/v1/paas/evaluate",
        json=_evaluate_response(allowed=True, receipt=bad_receipt),
    )
    handler = _make_handler(require_receipt_verified=True)
    with pytest.raises(RamenSafetyException) as exc_info:
        handler.on_tool_start(SERIALIZED_TOOL, INPUT_STR, run_id=RUN_ID)
    assert exc_info.value.receipt_verified is False


def test_allowed_with_unverifiable_receipt_passes_when_disabled(httpx_mock: HTTPXMock):
    """Same scenario but require_receipt_verified=False → no exception."""
    bad_receipt = {
        "id": "11111111-1111-4111-8111-111111111111",
        "schema_version": "5.0",
        "kid": "ramen_pk_v1",
        "signature": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        "canonical_payload": '{"schema_version":"5.0","payload_hash":"fake"}',
    }
    httpx_mock.add_response(
        url="https://api.ramenai.dev/api/v1/paas/evaluate",
        json=_evaluate_response(allowed=True, receipt=bad_receipt),
    )
    handler = _make_handler(require_receipt_verified=False)
    # Should not raise.
    handler.on_tool_start(SERIALIZED_TOOL, INPUT_STR, run_id=RUN_ID)


# ---------------------------------------------------------------------------
# 6. Payload construction — correct fields sent to the API
# ---------------------------------------------------------------------------


def test_payload_contains_tool_name_description_and_input(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.ramenai.dev/api/v1/paas/evaluate",
        json=_evaluate_response(allowed=True),
    )
    handler = _make_handler()
    handler.on_tool_start(SERIALIZED_TOOL, INPUT_STR, run_id=RUN_ID)

    request = httpx_mock.get_request()
    assert request is not None
    body = json.loads(request.content)

    sent_payload = json.loads(body["input"])
    assert sent_payload["tool"] == "drop_database_table"
    assert sent_payload["description"] == SERIALIZED_TOOL["description"]
    assert sent_payload["input"] == INPUT_STR


def test_bundle_ids_sent_in_request(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.ramenai.dev/api/v1/paas/evaluate",
        json=_evaluate_response(allowed=True),
    )
    handler = _make_handler()
    handler.on_tool_start(SERIALIZED_TOOL, INPUT_STR, run_id=RUN_ID)

    request = httpx_mock.get_request()
    body = json.loads(request.content)
    assert body["bundle_ids"] == BUNDLE


# ---------------------------------------------------------------------------
# 7. Context propagation — tool_name and run_id in context dict
# ---------------------------------------------------------------------------


def test_context_includes_tool_name_and_run_id(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.ramenai.dev/api/v1/paas/evaluate",
        json=_evaluate_response(allowed=True),
    )
    handler = _make_handler(context={"env": "test"})
    handler.on_tool_start(SERIALIZED_TOOL, INPUT_STR, run_id=RUN_ID)

    request = httpx_mock.get_request()
    body = json.loads(request.content)
    ctx = body.get("context", {})
    assert ctx["tool_name"] == "drop_database_table"
    assert ctx["run_id"] == str(RUN_ID)
    assert ctx["env"] == "test"


# ---------------------------------------------------------------------------
# 8. RamenSafetyException string representation
# ---------------------------------------------------------------------------


def test_exception_str_contains_key_fields():
    exc = RamenSafetyException(
        tool_name="my_tool",
        steering="Do not proceed.",
        receipt_verified=True,
        statutory_anchors=["OWASP ASI-06"],
    )
    msg = str(exc)
    assert "my_tool" in msg
    assert "OWASP ASI-06" in msg
    assert "Do not proceed." in msg
    assert "True" in msg


# ---------------------------------------------------------------------------
# 9. Request-scoped provider routing
# ---------------------------------------------------------------------------


def test_byok_headers_are_forwarded(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.ramenai.dev/api/v1/paas/evaluate",
        json=_evaluate_response(allowed=True),
    )
    handler = _make_handler(
        provider_key="provider-test-key",
        provider_name="anthropic",
    )
    handler.on_tool_start(SERIALIZED_TOOL, INPUT_STR, run_id=RUN_ID)

    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["X-Provider-Key"] == "provider-test-key"
    assert request.headers["X-Provider"] == "anthropic"


def test_managed_mode_omits_provider_headers(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.ramenai.dev/api/v1/paas/evaluate",
        json=_evaluate_response(allowed=True),
    )
    handler = _make_handler()
    handler.on_tool_start(SERIALIZED_TOOL, INPUT_STR, run_id=RUN_ID)

    request = httpx_mock.get_request()
    assert request is not None
    assert "X-Provider-Key" not in request.headers
    assert "X-Provider" not in request.headers
