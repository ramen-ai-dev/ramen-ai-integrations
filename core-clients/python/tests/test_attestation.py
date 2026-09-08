"""Additive attestation request tests for the synchronous client."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from ramen_ai import AttestationPayload, RamenClient

POLICY_ID = "1006492f-db62-4f46-8775-48b966c5c956"


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> RamenClient:
    ramen = RamenClient(api_key="ramen_ak_test", base_url="https://example.test")
    ramen._http.close()
    ramen._http = httpx.Client(
        base_url="https://example.test",
        headers={
            "Authorization": "Bearer ramen_ak_test",
            "Content-Type": "application/json",
        },
        transport=httpx.MockTransport(handler),
        timeout=30.0,
    )
    return ramen


def _response() -> dict[str, Any]:
    return {
        "data": {
            "allowed": True,
            "policy_ids": [POLICY_ID],
            "policies_evaluated": 1,
            "policies_passed": 1,
            "policies_failed": 0,
            "policies_errored": 0,
            "total_violations": [],
            "results": [],
            "execution_time_ms": 1,
            "executed_at": "2026-08-12T00:00:00Z",
        }
    }


def test_evaluate_compliance_omits_attestation_by_default() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == {
            "input": "evaluate me",
            "policy_ids": [POLICY_ID],
        }
        return httpx.Response(200, json=_response())

    with _client(handler) as client:
        result = client.evaluate_compliance(
            "evaluate me",
            policy_ids=[POLICY_ID],
        )

    assert result["allowed"] is True


def test_evaluate_compliance_forwards_attestation() -> None:
    attestation: AttestationPayload = {
        "vendor": "mock",
        "evidence": "signed-evidence",
        "challenge": "challenge-digest",
        "metadata": {"tee": "test"},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == {
            "input": "evaluate me",
            "policy_ids": [POLICY_ID],
            "attestation": attestation,
        }
        return httpx.Response(200, json=_response())

    with _client(handler) as client:
        result = client.evaluate_compliance(
            "evaluate me",
            policy_ids=[POLICY_ID],
            attestation=attestation,
        )

    assert result["allowed"] is True
