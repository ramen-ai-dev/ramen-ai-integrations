"""
Unit and integration tests for ramen_pydantic middleware.

Coverage
--------
Unit (validator function in isolation):
  - ALLOWED verdict: validator returns None without raising.
  - BLOCKED verdict: RamenSafetyException raised with correct fields.
  - Transport failure (ConnectError): fail-closed → RamenSafetyException.
  - HTTP 5xx error: fail-closed → RamenSafetyException.
  - Unverifiable receipt escalated to BLOCK when require_receipt_verified=True.
  - Unverifiable receipt passes when require_receipt_verified=False.
  - Constructor guard: ValueError when neither bundle_ids nor policy_ids.
  - Payload JSON contains tool name and args_dict.
  - Context dict contains tool_name and run_id.

Integration (through PydanticAI TestModel agent.run()):
  - ALLOWED verdict: agent.run() completes, tool executes, result returned.
  - BLOCKED verdict: RamenSafetyException propagates out of agent.run().

All HTTP calls intercepted via unittest.mock so no live API key is required.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.test import TestModel

from ramen_pydantic import RamenSafetyException, ramen_firewall

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

API_KEY = "ramen_ak_test"
BUNDLE = ["ramen__shield_core_it"]
TOOL_NAME = "drop_database_table"


def _make_httpx_response(data: dict, status: int = 200) -> httpx.Response:
    """Build a real httpx.Response with a stub request attached (required by httpx)."""
    request = httpx.Request("POST", "https://api.ramenai.dev/api/v1/paas/evaluate")
    return httpx.Response(status, json=data, request=request)


def _evaluate_body(
    *,
    allowed: bool,
    steering: str | None = None,
    statutory_anchors: list[str] | None = None,
    receipt: dict | None = None,
    receipt_alert: str | None = None,
) -> dict:
    """Minimal valid /api/v1/paas/evaluate response envelope."""
    violations = (
        []
        if allowed
        else [
            {
                "rule_id": "r1",
                "rule_name": "Test Rule",
                "rule_content": "block",
                "enforcement_level": "strict",
                "recovery_instruction": steering or "Refuse the request.",
            }
        ]
    )
    return {
        "data": {
            "allowed": allowed,
            "policy_ids": ["6c787849-96db-4c92-8df9-10aa8d035527"],
            "policies_evaluated": 1,
            "policies_passed": 1 if allowed else 0,
            "policies_failed": 0 if allowed else 1,
            "policies_errored": 0,
            "total_violations": violations,
            "results": [],
            "execution_time_ms": 5,
            "executed_at": "2026-06-27T12:00:00.000Z",
            "statutory_anchors": statutory_anchors or [],
            "receipt": receipt,
            "receipt_alert": receipt_alert,
        }
    }


# ---------------------------------------------------------------------------
# Minimal RunContext mock — only needs .tool_name and .run_id for the validator
# ---------------------------------------------------------------------------

@dataclass
class _MockCtx:
    tool_name: str | None = TOOL_NAME
    run_id: str | None = "test-run-001"


# ---------------------------------------------------------------------------
# Helper: patch httpx.Client.post and invoke the validator directly
# ---------------------------------------------------------------------------

async def _call_validator(
    response_data: dict | None = None,
    raise_exc: Exception | None = None,
    status: int = 200,
    **factory_kwargs: Any,
) -> None:
    """
    Build a firewall validator and invoke it directly against a mock RunContext.

    If *raise_exc* is set it is raised from the patched httpx.Client.post.
    Otherwise *response_data* is returned as the HTTP response.
    """
    if not factory_kwargs.get("bundle_ids") and not factory_kwargs.get("policy_ids"):
        factory_kwargs["bundle_ids"] = BUNDLE

    firewall = ramen_firewall(api_key=API_KEY, **factory_kwargs)
    ctx = _MockCtx()

    def mock_post(self, url, **kw):  # noqa: N802
        if raise_exc:
            raise raise_exc
        return _make_httpx_response(response_data or {}, status=status)

    with patch.object(httpx.Client, "post", mock_post):
        await firewall(ctx, table_name="users_prod")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# 1. Constructor validation
# ---------------------------------------------------------------------------


def test_constructor_requires_bundle_or_policy() -> None:
    with pytest.raises(ValueError, match="bundle_ids.*policy_ids"):
        ramen_firewall(api_key=API_KEY)


def test_constructor_accepts_policy_ids_only() -> None:
    validator = ramen_firewall(
        api_key=API_KEY,
        policy_ids=["6c787849-96db-4c92-8df9-10aa8d035527"],
    )
    assert callable(validator)


# ---------------------------------------------------------------------------
# 2. ALLOWED verdict — no exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_allowed_verdict_does_not_raise() -> None:
    await _call_validator(response_data=_evaluate_body(allowed=True))


# ---------------------------------------------------------------------------
# 3. BLOCKED verdict — correct fields on the exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blocked_verdict_raises_with_correct_fields() -> None:
    anchors = ["EU AI Act Art. 5(1)(a)"]
    with pytest.raises(RamenSafetyException) as exc_info:
        await _call_validator(
            response_data=_evaluate_body(
                allowed=False,
                steering="Refuse destructive operations.",
                statutory_anchors=anchors,
            )
        )

    exc = exc_info.value
    assert exc.tool_name == TOOL_NAME
    assert exc.steering == "Refuse destructive operations."
    assert exc.statutory_anchors == anchors
    assert exc.receipt_verified is False


# ---------------------------------------------------------------------------
# 4. Fail-closed: transport / HTTP errors → RamenSafetyException
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_error_raises_fail_closed() -> None:
    with pytest.raises(RamenSafetyException) as exc_info:
        await _call_validator(raise_exc=httpx.ConnectError("refused"))

    exc = exc_info.value
    assert exc.tool_name == TOOL_NAME
    assert exc.__cause__ is not None  # original exception chained
    assert "fail-closed" in str(exc).lower() or "could not complete" in str(exc).lower()


@pytest.mark.asyncio
async def test_http_502_raises_fail_closed() -> None:
    # httpx raises HTTPStatusError on raise_for_status() for 5xx.
    request = httpx.Request("POST", "https://api.ramenai.dev/api/v1/paas/evaluate")
    error_response = httpx.Response(502, request=request)

    with pytest.raises(RamenSafetyException):
        await _call_validator(
            raise_exc=httpx.HTTPStatusError("bad gateway", request=request, response=error_response)
        )


# ---------------------------------------------------------------------------
# 5. Unverifiable receipt escalation
# ---------------------------------------------------------------------------

_BAD_RECEIPT = {
    "id": "11111111-1111-4111-8111-111111111111",
    "schema_version": "5.0",
    "kid": "ramen_pk_v1",
    "signature": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "canonical_payload": '{"schema_version":"5.0","payload_hash":"fake"}',
}


@pytest.mark.asyncio
async def test_allowed_unverifiable_receipt_escalates_by_default() -> None:
    """ALLOWED + bad receipt + require_receipt_verified=True → BLOCK."""
    with pytest.raises(RamenSafetyException) as exc_info:
        await _call_validator(
            response_data=_evaluate_body(allowed=True, receipt=_BAD_RECEIPT),
            require_receipt_verified=True,
        )
    assert exc_info.value.receipt_verified is False


@pytest.mark.asyncio
async def test_allowed_unverifiable_receipt_passes_when_disabled() -> None:
    """ALLOWED + bad receipt + require_receipt_verified=False → no exception."""
    await _call_validator(
        response_data=_evaluate_body(allowed=True, receipt=_BAD_RECEIPT),
        require_receipt_verified=False,
    )


# ---------------------------------------------------------------------------
# 6. Payload construction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_payload_contains_tool_name_and_args() -> None:
    captured: list[dict] = []

    def mock_post(self, url, **kw):  # noqa: N802
        captured.append(json.loads(kw["json"]["input"]))
        return _make_httpx_response(_evaluate_body(allowed=True))

    firewall = ramen_firewall(api_key=API_KEY, bundle_ids=BUNDLE)
    ctx = _MockCtx(tool_name="my_tool")

    with patch.object(httpx.Client, "post", mock_post):
        await firewall(ctx, param_a="hello", param_b=42)  # type: ignore[call-arg]

    assert len(captured) == 1
    payload = captured[0]
    assert payload["tool"] == "my_tool"
    assert payload["args"] == {"param_a": "hello", "param_b": 42}


@pytest.mark.asyncio
async def test_bundle_ids_sent_in_request_body() -> None:
    captured: list[dict] = []

    def mock_post(self, url, **kw):  # noqa: N802
        captured.append(kw["json"])
        return _make_httpx_response(_evaluate_body(allowed=True))

    firewall = ramen_firewall(api_key=API_KEY, bundle_ids=["ramen__shield_core_it"])
    ctx = _MockCtx()

    with patch.object(httpx.Client, "post", mock_post):
        await firewall(ctx)  # type: ignore[call-arg]

    assert captured[0]["bundle_ids"] == ["ramen__shield_core_it"]


# ---------------------------------------------------------------------------
# 7. Context propagation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_includes_tool_name_and_run_id() -> None:
    captured: list[dict] = []

    def mock_post(self, url, **kw):  # noqa: N802
        captured.append(kw["json"])
        return _make_httpx_response(_evaluate_body(allowed=True))

    firewall = ramen_firewall(
        api_key=API_KEY,
        bundle_ids=BUNDLE,
        context={"env": "test"},
    )
    ctx = _MockCtx(tool_name="my_tool", run_id="run-xyz")

    with patch.object(httpx.Client, "post", mock_post):
        await firewall(ctx)  # type: ignore[call-arg]

    ctx_sent = captured[0]["context"]
    assert ctx_sent["tool_name"] == "my_tool"
    assert ctx_sent["run_id"] == "run-xyz"
    assert ctx_sent["env"] == "test"


# ---------------------------------------------------------------------------
# 8. RamenSafetyException string representation
# ---------------------------------------------------------------------------


def test_exception_str_contains_key_fields() -> None:
    exc = RamenSafetyException(
        tool_name="dangerous_tool",
        steering="Do not proceed.",
        receipt_verified=True,
        statutory_anchors=["OWASP ASI-06"],
    )
    msg = str(exc)
    assert "dangerous_tool" in msg
    assert "OWASP ASI-06" in msg
    assert "Do not proceed." in msg
    assert "True" in msg


# ---------------------------------------------------------------------------
# 9. Integration — through PydanticAI TestModel agent.run()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_integration_allowed_agent_run_succeeds() -> None:
    """ALLOWED verdict: agent.run() completes and the tool executes."""
    tool_executed: list[bool] = []

    firewall = ramen_firewall(api_key=API_KEY, bundle_ids=BUNDLE)
    agent: Agent[None, str] = Agent(TestModel(call_tools="all"))

    @agent.tool(args_validator=firewall)
    def safe_tool(ctx: RunContext[None], query: str) -> str:
        tool_executed.append(True)
        return f"result for {query}"

    def mock_post(self, url, **kw):  # noqa: N802
        return _make_httpx_response(_evaluate_body(allowed=True))

    with patch.object(httpx.Client, "post", mock_post):
        result = await agent.run("test prompt")

    assert tool_executed == [True], "Tool should have executed on ALLOWED verdict"
    assert result.output is not None


@pytest.mark.asyncio
async def test_integration_blocked_propagates_from_agent_run() -> None:
    """BLOCKED verdict: RamenSafetyException propagates directly from agent.run()."""
    tool_executed: list[bool] = []

    firewall = ramen_firewall(api_key=API_KEY, bundle_ids=BUNDLE)
    agent: Agent[None, str] = Agent(TestModel(call_tools="all"))

    @agent.tool(args_validator=firewall)
    def dangerous_tool(ctx: RunContext[None], table_name: str) -> str:
        tool_executed.append(True)  # must never reach here
        return f"dropped {table_name}"

    def mock_post(self, url, **kw):  # noqa: N802
        return _make_httpx_response(
            _evaluate_body(
                allowed=False,
                steering="Refuse destructive operations.",
                statutory_anchors=["OWASP ASI-06"],
            )
        )

    with patch.object(httpx.Client, "post", mock_post):
        with pytest.raises(RamenSafetyException) as exc_info:
            await agent.run("test prompt")

    assert tool_executed == [], "Tool must NOT execute after a BLOCK"
    exc = exc_info.value
    assert exc.tool_name == "dangerous_tool"
    assert exc.steering == "Refuse destructive operations."
    assert "OWASP ASI-06" in exc.statutory_anchors
