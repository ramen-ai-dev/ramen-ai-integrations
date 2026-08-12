"""JSON and SSE contract tests for governed generation."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

from ramen_ai import (
    GovernanceDeniedException,
    GovernedCompleteEvent,
    GovernedGenerationException,
    GovernedGenerationOptions,
    GovernedHeartbeatEvent,
    GovernedStatusEvent,
    RamenClient,
)

POLICY_ID = "1006492f-db62-4f46-8775-48b966c5c956"


def _evaluation(*, allowed: bool = True) -> dict[str, Any]:
    return {
        "allowed": allowed,
        "policy_ids": [POLICY_ID],
        "policies_evaluated": 1,
        "policies_passed": 1 if allowed else 0,
        "policies_failed": 0 if allowed else 1,
        "policies_errored": 0,
        "violation_count": 0 if allowed else 1,
        "statutory_anchors": ["FCA PRIN 2A.2.8"],
        "receipt_id": "receipt-1",
    }


def _attempt(*, allowed: bool = True) -> dict[str, Any]:
    return {
        "attempt": 1,
        "provider": "openai",
        "model": "gpt-test",
        "generation_duration_ms": 12,
        "evaluation_duration_ms": 8,
        "policies_evaluated": 1,
        "allowed": allowed,
        "usage": {
            "prompt_tokens": 4,
            "completion_tokens": 3,
            "total_tokens": 7,
        },
    }


def _accounting() -> dict[str, int]:
    return {
        "generation_attempts": 1,
        "evaluation_batches": 1,
        "policy_evaluations": 1,
    }


def _complete_data() -> dict[str, Any]:
    return {
        "content": "approved output",
        "provider": "openai",
        "model": "gpt-test",
        "usage": {
            "prompt_tokens": 4,
            "completion_tokens": 3,
            "total_tokens": 7,
        },
        "attempts": 1,
        "attempt_metadata": [_attempt()],
        "evaluation": _evaluation(),
        "accounting": _accounting(),
        "total_duration_ms": 20,
    }


def _blocked_data() -> dict[str, Any]:
    return {
        "attempts": 1,
        "attempt_metadata": [_attempt(allowed=False)],
        "evaluation": _evaluation(allowed=False),
        "accounting": _accounting(),
        "total_duration_ms": 20,
    }


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


class _TrackingStream(httpx.SyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self.closed = False

    def __iter__(self) -> Iterator[bytes]:
        yield from self._chunks

    def close(self) -> None:
        self.closed = True


def test_generate_governed_maps_request_headers_and_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/generate/governed"
        assert request.headers["Authorization"] == "Bearer ramen_ak_test"
        assert request.headers["X-Provider-Key"] == "provider-secret"
        assert request.headers["X-Provider"] == "openai"
        assert request.headers.get("Accept") != "text/event-stream"
        assert json.loads(request.content) == {
            "prompt": "Write a compliant answer",
            "policy_ids": [POLICY_ID],
            "bundle_ids": ["ramen__baseline"],
            "max_retries": 0,
            "generation": {"temperature": 0.2, "max_tokens": 256},
        }
        return httpx.Response(
            200, json={"success": True, "data": _complete_data()}
        )

    with _client(handler) as client:
        result = client.generate_governed(
            "Write a compliant answer",
            policy_ids=[POLICY_ID],
            bundle_ids=["ramen__baseline"],
            max_retries=0,
            generation=GovernedGenerationOptions(temperature=0.2, max_tokens=256),
            provider_key="provider-secret",
            provider_name="openai",
        )

    assert result.content == "approved output"
    assert result.usage is not None
    assert result.usage.total_tokens == 7
    assert result.evaluation.receipt_id == "receipt-1"


def test_provider_name_is_not_sent_without_provider_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "X-Provider-Key" not in request.headers
        assert "X-Provider" not in request.headers
        return httpx.Response(
            200, json={"success": True, "data": _complete_data()}
        )

    with _client(handler) as client:
        client.generate_governed(
            "prompt", bundle_ids=["ramen__baseline"], provider_name="anthropic"
        )


def test_json_blocked_raises_governance_denied_exception() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "success": False,
                "error": {
                    "code": "GOVERNED_OUTPUT_BLOCKED",
                    "message": "No compliant output was produced within the retry limit",
                    "http_status": 422,
                },
                "data": _blocked_data(),
            },
        )

    with _client(handler) as client, pytest.raises(
        GovernanceDeniedException
    ) as captured:
        client.generate_governed("prompt", policy_ids=[POLICY_ID])

    assert captured.value.status == 422
    assert captured.value.code == "GOVERNED_OUTPUT_BLOCKED"
    assert captured.value.data.evaluation.allowed is False


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 429, 502, 503])
def test_json_api_errors_are_structured(status: int) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={
                "success": False,
                "error": {
                    "code": f"ERROR_{status}",
                    "message": "request failed",
                    "details": {"status": status},
                },
            },
        )

    with _client(handler) as client, pytest.raises(
        GovernedGenerationException
    ) as captured:
        client.generate_governed("prompt", policy_ids=[POLICY_ID])

    assert captured.value.status == status
    assert captured.value.code == f"ERROR_{status}"
    assert captured.value.details == {"status": status}


def test_stream_yields_status_heartbeat_and_complete_across_chunk_boundaries() -> None:
    complete = json.dumps({"success": True, "data": _complete_data()})
    chunks = [
        b"event: status\r\ndata: {\"stage\":\r\n",
        b"data: \"accepted\",\"attempt\":0}\r\n\r\nevent: heartbeat\r\n",
        b'data: {"timestamp":"2026-08-12T12:00:00.000Z"}\r\n\r\n',
        f"event: complete\r\ndata: {complete}\r\n\r\n".encode(),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Accept"] == "text/event-stream"
        assert request.headers["X-Provider-Key"] == "provider-secret"
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream; charset=utf-8"},
            stream=_TrackingStream(chunks),
        )

    with _client(handler) as client:
        events = list(
            client.generate_governed_stream(
                "prompt", policy_ids=[POLICY_ID], provider_key="provider-secret"
            )
        )

    assert isinstance(events[0], GovernedStatusEvent)
    assert events[0].data.stage == "accepted"
    assert isinstance(events[1], GovernedHeartbeatEvent)
    assert isinstance(events[2], GovernedCompleteEvent)
    assert events[2].data.success is True
    assert events[2].data.data.content == "approved output"


def test_stream_blocked_throws_and_never_yields_terminal_event() -> None:
    blocked = json.dumps(
        {
            "success": False,
            "error": {
                "code": "GOVERNED_OUTPUT_BLOCKED",
                "message": "blocked",
                "http_status": 422,
            },
            "data": _blocked_data(),
        }
    )
    body = (
        'event: status\ndata: {"stage":"accepted","attempt":0}\n\n'
        f"event: blocked\ndata: {blocked}\n\n"
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content=body,
        )

    with _client(handler) as client:
        stream = client.generate_governed_stream("prompt", policy_ids=[POLICY_ID])
        first = next(stream)
        assert isinstance(first, GovernedStatusEvent)
        with pytest.raises(GovernanceDeniedException) as captured:
            next(stream)

    assert captured.value.data.attempts == 1


def test_stream_error_terminal_raises_structured_exception() -> None:
    error = json.dumps(
        {
            "success": False,
            "error": {
                "code": "GOVERNANCE_UNAVAILABLE",
                "message": "unavailable",
                "http_status": 503,
            },
            "data": {"accounting": _accounting(), "attempts": 1, "total_duration_ms": 20},
        }
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content=f"event: error\ndata: {error}\n\n",
        )

    with _client(handler) as client, pytest.raises(
        GovernedGenerationException
    ) as captured:
        list(client.generate_governed_stream("prompt", policy_ids=[POLICY_ID]))

    assert captured.value.status == 503
    assert captured.value.code == "GOVERNANCE_UNAVAILABLE"


def test_stream_preflight_http_error_is_parsed_as_json() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "success": False,
                "error": {"code": "UNAUTHORIZED", "message": "bad key"},
            },
        )

    with _client(handler) as client, pytest.raises(
        GovernedGenerationException
    ) as captured:
        list(client.generate_governed_stream("prompt", policy_ids=[POLICY_ID]))

    assert captured.value.status == 401
    assert captured.value.code == "UNAUTHORIZED"


def test_stream_rejects_wrong_content_type() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "application/json"}, json={})

    with _client(handler) as client, pytest.raises(
        GovernedGenerationException
    ) as captured:
        list(client.generate_governed_stream("prompt", policy_ids=[POLICY_ID]))

    assert captured.value.code == "STREAM_PROTOCOL_ERROR"


def test_stream_rejects_malformed_known_event() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content="event: status\ndata: {not-json}\n\n",
        )

    with _client(handler) as client, pytest.raises(
        GovernedGenerationException
    ) as captured:
        list(client.generate_governed_stream("prompt", policy_ids=[POLICY_ID]))

    assert captured.value.code == "STREAM_PARSE_ERROR"


def test_stream_ignores_unknown_events_then_completes() -> None:
    complete = json.dumps({"success": True, "data": _complete_data()})
    body = (
        'event: future-event\ndata: {"ignored":true}\n\n'
        f"event: complete\ndata: {complete}"
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content=body,
        )

    with _client(handler) as client:
        events = list(
            client.generate_governed_stream("prompt", policy_ids=[POLICY_ID])
        )

    assert len(events) == 1
    assert isinstance(events[0], GovernedCompleteEvent)


def test_stream_raises_when_eof_has_no_terminal_event() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content='event: status\ndata: {"stage":"accepted","attempt":0}\n\n',
        )

    with _client(handler) as client, pytest.raises(
        GovernedGenerationException
    ) as captured:
        list(client.generate_governed_stream("prompt", policy_ids=[POLICY_ID]))

    assert captured.value.code == "STREAM_TERMINATED"


def test_closing_stream_iterator_closes_http_response() -> None:
    stream_body = _TrackingStream(
        [b'event: status\ndata: {"stage":"accepted","attempt":0}\n\n']
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=stream_body,
        )

    with _client(handler) as client:
        iterator = client.generate_governed_stream("prompt", policy_ids=[POLICY_ID])
        assert isinstance(next(iterator), GovernedStatusEvent)
        iterator.close()  # type: ignore[attr-defined]

    assert stream_body.closed is True


def test_transport_timeout_is_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with _client(handler) as client, pytest.raises(
        GovernedGenerationException
    ) as captured:
        client.generate_governed("prompt", policy_ids=[POLICY_ID])

    assert captured.value.status is None
    assert captured.value.code == "TRANSPORT_TIMEOUT"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({}, "at least one"),
        ({"policy_ids": [POLICY_ID], "max_retries": 2}, "max_retries"),
        (
            {
                "policy_ids": [POLICY_ID],
                "generation": GovernedGenerationOptions(temperature=2.1),
            },
            "temperature",
        ),
    ],
)
def test_request_validation(kwargs: dict[str, Any], message: str) -> None:
    with _client(lambda _: httpx.Response(500)) as client, pytest.raises(
        ValueError, match=message
    ):
        client.generate_governed("prompt", **kwargs)


@pytest.mark.parametrize("success", [False, None])
def test_stream_rejects_complete_without_true_success(success: bool | None) -> None:
    payload: dict[str, Any] = {"data": _complete_data()}
    if success is not None:
        payload["success"] = success

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content=f"event: complete\ndata: {json.dumps(payload)}\n\n",
        )

    with _client(handler) as client, pytest.raises(
        GovernedGenerationException
    ) as captured:
        list(client.generate_governed_stream("prompt", policy_ids=[POLICY_ID]))

    assert captured.value.code == "STREAM_PARSE_ERROR"
