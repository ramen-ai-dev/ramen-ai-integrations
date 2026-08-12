"""Isolated JSON and SSE transport for governed generation."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Literal, cast

import httpx

from .governed_errors import (
    GovernanceDeniedException,
    GovernedGenerationException,
)
from .governed_types import (
    GovernedAccounting,
    GovernedAttemptMetadata,
    GovernedBlockedData,
    GovernedCompleteData,
    GovernedCompleteEnvelope,
    GovernedCompleteEvent,
    GovernedEvaluationSummary,
    GovernedGenerationOptions,
    GovernedHeartbeatData,
    GovernedHeartbeatEvent,
    GovernedProviderName,
    GovernedStatusData,
    GovernedStatusEvent,
    GovernedStatusStage,
    GovernedStreamEvent,
    GovernedTokenUsage,
)

_GOVERNED_PATH = "/api/v1/generate/governed"
_STATUS_STAGES = {"accepted", "generating", "evaluating", "regenerating"}


def generate_governed(
    client: httpx.Client,
    prompt: str,
    *,
    policy_ids: Sequence[str] | None = None,
    bundle_ids: Sequence[str] | None = None,
    max_retries: Literal[0, 1] = 1,
    generation: GovernedGenerationOptions | None = None,
    provider_key: str | None = None,
    provider_name: GovernedProviderName | None = None,
) -> GovernedCompleteData:
    """Execute a governed generation request and return released content."""

    body = _build_body(prompt, policy_ids, bundle_ids, max_retries, generation)
    headers = _provider_headers(provider_key, provider_name)
    try:
        response = client.post(
            _GOVERNED_PATH,
            json=body,
            headers=headers or None,
        )
    except httpx.TimeoutException as error:
        raise GovernedGenerationException(
            None, "TRANSPORT_TIMEOUT", "Governed generation timed out"
        ) from error
    except httpx.HTTPError as error:
        raise GovernedGenerationException(
            None, "TRANSPORT_ERROR", "Governed generation request failed"
        ) from error

    payload = _decode_response_json(response)
    if not response.is_success or payload.get("success") is not True:
        _raise_api_error(response.status_code, payload)
    return _parse_complete_data(payload.get("data"), response.status_code)


def generate_governed_stream(
    client: httpx.Client,
    prompt: str,
    *,
    policy_ids: Sequence[str] | None = None,
    bundle_ids: Sequence[str] | None = None,
    max_retries: Literal[0, 1] = 1,
    generation: GovernedGenerationOptions | None = None,
    provider_key: str | None = None,
    provider_name: GovernedProviderName | None = None,
) -> Iterator[GovernedStreamEvent]:
    """Yield governed status events and the successful terminal event."""

    body = _build_body(prompt, policy_ids, bundle_ids, max_retries, generation)
    headers = {
        "Accept": "text/event-stream",
        **_provider_headers(provider_key, provider_name),
    }

    try:
        with client.stream(
            "POST",
            _GOVERNED_PATH,
            json=body,
            headers=headers,
        ) as response:
            if not response.is_success:
                response.read()
                payload = _decode_response_json(response)
                _raise_api_error(response.status_code, payload)

            content_type = response.headers.get("Content-Type", "").lower()
            if not content_type.startswith("text/event-stream"):
                raise GovernedGenerationException(
                    response.status_code,
                    "STREAM_PROTOCOL_ERROR",
                    "Governed generation did not return an SSE stream",
                )

            event_name: str | None = None
            data_lines: list[str] = []
            terminal_seen = False

            for line in response.iter_lines():
                if line == "":
                    parsed = _dispatch_sse_event(
                        event_name, data_lines, response.status_code
                    )
                    event_name = None
                    data_lines = []
                    if parsed is None:
                        continue
                    yield parsed
                    if parsed.event == "complete":
                        terminal_seen = True
                        return
                    continue

                if line.startswith(":"):
                    continue
                field, separator, value = line.partition(":")
                if not separator:
                    value = ""
                elif value.startswith(" "):
                    value = value[1:]
                if field == "event":
                    event_name = value
                elif field == "data":
                    data_lines.append(value)

            if event_name is not None or data_lines:
                parsed = _dispatch_sse_event(
                    event_name, data_lines, response.status_code
                )
                if parsed is not None:
                    yield parsed
                    if parsed.event == "complete":
                        terminal_seen = True
                        return

            if not terminal_seen:
                raise GovernedGenerationException(
                    response.status_code,
                    "STREAM_TERMINATED",
                    "Governed generation stream ended without a terminal event",
                )
    except GovernedGenerationException:
        raise
    except httpx.TimeoutException as error:
        raise GovernedGenerationException(
            None, "TRANSPORT_TIMEOUT", "Governed generation stream timed out"
        ) from error
    except httpx.HTTPError as error:
        raise GovernedGenerationException(
            None, "TRANSPORT_ERROR", "Governed generation stream failed"
        ) from error


def _build_body(
    prompt: str,
    policy_ids: Sequence[str] | None,
    bundle_ids: Sequence[str] | None,
    max_retries: Literal[0, 1],
    generation: GovernedGenerationOptions | None,
) -> dict[str, Any]:
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 10_000:
        raise ValueError("prompt must be a non-blank string of at most 10,000 characters")
    if not policy_ids and not bundle_ids:
        raise ValueError("Provide at least one of 'bundle_ids' or 'policy_ids'.")
    if max_retries not in (0, 1):
        raise ValueError("max_retries must be 0 or 1")

    body: dict[str, Any] = {"prompt": prompt, "max_retries": max_retries}
    if policy_ids:
        body["policy_ids"] = list(policy_ids)
    if bundle_ids:
        body["bundle_ids"] = list(bundle_ids)
    if generation is not None:
        generation_body: dict[str, int | float] = {}
        if generation.temperature is not None:
            if not 0 <= generation.temperature <= 2:
                raise ValueError("generation.temperature must be between 0 and 2")
            generation_body["temperature"] = generation.temperature
        if generation.max_tokens is not None:
            if not 1 <= generation.max_tokens <= 4096:
                raise ValueError("generation.max_tokens must be between 1 and 4096")
            generation_body["max_tokens"] = generation.max_tokens
        body["generation"] = generation_body
    return body


def _provider_headers(
    provider_key: str | None,
    provider_name: GovernedProviderName | None,
) -> dict[str, str]:
    if not provider_key:
        return {}
    headers = {"X-Provider-Key": provider_key}
    if provider_name:
        headers["X-Provider"] = provider_name
    return headers


def _decode_response_json(response: httpx.Response) -> Mapping[str, Any]:
    try:
        payload = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
        raise GovernedGenerationException(
            response.status_code,
            "PARSE_ERROR",
            "Failed to parse governed generation response",
        ) from error
    if not isinstance(payload, Mapping):
        raise GovernedGenerationException(
            response.status_code,
            "PARSE_ERROR",
            "Governed generation response must be a JSON object",
        )
    return cast(Mapping[str, Any], payload)


def _raise_api_error(status: int, payload: Mapping[str, Any]) -> None:
    error_value = payload.get("error")
    error = error_value if isinstance(error_value, Mapping) else {}
    code = error.get("code") if isinstance(error.get("code"), str) else "UNKNOWN_ERROR"
    message = (
        error.get("message")
        if isinstance(error.get("message"), str)
        else f"Governed generation failed with HTTP {status}"
    )
    details = error.get("details", payload.get("data"))
    if status == 422 and code == "GOVERNED_OUTPUT_BLOCKED":
        data = _parse_blocked_data(payload.get("data"), status)
        raise GovernanceDeniedException(message, data)
    raise GovernedGenerationException(status, code, message, details)


def _dispatch_sse_event(
    event_name: str | None,
    data_lines: list[str],
    status: int,
) -> GovernedStreamEvent | None:
    if event_name not in {"status", "heartbeat", "complete", "blocked", "error"}:
        return None
    if not data_lines:
        raise GovernedGenerationException(
            status, "STREAM_PARSE_ERROR", f"SSE event {event_name} has no data"
        )
    try:
        payload = json.loads("\n".join(data_lines))
    except json.JSONDecodeError as error:
        raise GovernedGenerationException(
            status,
            "STREAM_PARSE_ERROR",
            f"Failed to parse governed generation SSE event: {event_name}",
        ) from error
    if not isinstance(payload, Mapping):
        raise GovernedGenerationException(
            status,
            "STREAM_PARSE_ERROR",
            f"Governed generation SSE event {event_name} must contain an object",
        )

    try:
        if event_name == "status":
            stage_value = _required(payload, "stage", str)
            if stage_value not in _STATUS_STAGES:
                raise ValueError("invalid status stage")
            violations_value = payload.get("violations")
            violations = (
                _expect_int(violations_value, "violations")
                if violations_value is not None
                else None
            )
            return GovernedStatusEvent(
                event="status",
                data=GovernedStatusData(
                    stage=cast(GovernedStatusStage, stage_value),
                    attempt=_required_int(payload, "attempt"),
                    violations=violations,
                ),
            )
        if event_name == "heartbeat":
            return GovernedHeartbeatEvent(
                event="heartbeat",
                data=GovernedHeartbeatData(
                    timestamp=_required(payload, "timestamp", str)
                ),
            )
        if event_name == "complete":
            if payload.get("success") is not True:
                raise ValueError("invalid complete terminal event")
            return GovernedCompleteEvent(
                event="complete",
                data=GovernedCompleteEnvelope(
                    success=True,
                    data=_parse_complete_data(payload.get("data"), status),
                ),
            )

        error_value = payload.get("error")
        error = _expect_mapping(error_value, "error")
        code = _required(error, "code", str)
        message = _required(error, "message", str)
        logical_status = _required_int(error, "http_status")
        if event_name == "blocked":
            if code != "GOVERNED_OUTPUT_BLOCKED" or logical_status != 422:
                raise ValueError("invalid blocked terminal event")
            raise GovernanceDeniedException(
                message, _parse_blocked_data(payload.get("data"), logical_status)
            )
        raise GovernedGenerationException(
            logical_status, code, message, payload.get("data")
        )
    except GovernedGenerationException:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise GovernedGenerationException(
            status,
            "STREAM_PARSE_ERROR",
            f"Invalid governed generation SSE event: {event_name}",
        ) from error


def _parse_complete_data(value: Any, status: int) -> GovernedCompleteData:
    try:
        data = _expect_mapping(value, "data")
        usage_value = data.get("usage")
        return GovernedCompleteData(
            content=_required(data, "content", str),
            provider=_required(data, "provider", str),
            model=_required(data, "model", str),
            attempts=_required_int(data, "attempts"),
            attempt_metadata=_parse_attempt_metadata(data.get("attempt_metadata")),
            evaluation=_parse_evaluation(data.get("evaluation")),
            accounting=_parse_accounting(data.get("accounting")),
            total_duration_ms=_required_int(data, "total_duration_ms"),
            usage=_parse_usage(usage_value) if usage_value is not None else None,
        )
    except GovernedGenerationException:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise GovernedGenerationException(
            status, "PARSE_ERROR", "Invalid governed generation completion payload"
        ) from error


def _parse_blocked_data(value: Any, status: int) -> GovernedBlockedData:
    try:
        data = _expect_mapping(value, "data")
        return GovernedBlockedData(
            attempts=_required_int(data, "attempts"),
            attempt_metadata=_parse_attempt_metadata(data.get("attempt_metadata")),
            evaluation=_parse_evaluation(data.get("evaluation")),
            accounting=_parse_accounting(data.get("accounting")),
            total_duration_ms=_required_int(data, "total_duration_ms"),
        )
    except GovernedGenerationException:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise GovernedGenerationException(
            status, "PARSE_ERROR", "Invalid governed generation blocked payload"
        ) from error


def _parse_usage(value: Any) -> GovernedTokenUsage:
    data = _expect_mapping(value, "usage")
    return GovernedTokenUsage(
        prompt_tokens=_required_int(data, "prompt_tokens"),
        completion_tokens=_required_int(data, "completion_tokens"),
        total_tokens=_required_int(data, "total_tokens"),
    )


def _parse_attempt_metadata(value: Any) -> tuple[GovernedAttemptMetadata, ...]:
    items = _expect_list(value, "attempt_metadata")
    parsed: list[GovernedAttemptMetadata] = []
    for item in items:
        data = _expect_mapping(item, "attempt_metadata item")
        usage_value = data.get("usage")
        parsed.append(
            GovernedAttemptMetadata(
                attempt=_required_int(data, "attempt"),
                provider=_required(data, "provider", str),
                model=_required(data, "model", str),
                generation_duration_ms=_required_int(
                    data, "generation_duration_ms"
                ),
                evaluation_duration_ms=_required_int(
                    data, "evaluation_duration_ms"
                ),
                policies_evaluated=_required_int(data, "policies_evaluated"),
                allowed=_required_bool(data, "allowed"),
                usage=_parse_usage(usage_value) if usage_value is not None else None,
            )
        )
    return tuple(parsed)


def _parse_accounting(value: Any) -> GovernedAccounting:
    data = _expect_mapping(value, "accounting")
    return GovernedAccounting(
        generation_attempts=_required_int(data, "generation_attempts"),
        evaluation_batches=_required_int(data, "evaluation_batches"),
        policy_evaluations=_required_int(data, "policy_evaluations"),
    )


def _parse_evaluation(value: Any) -> GovernedEvaluationSummary:
    data = _expect_mapping(value, "evaluation")
    receipt_id = data.get("receipt_id")
    if receipt_id is not None and not isinstance(receipt_id, str):
        raise TypeError("evaluation.receipt_id must be a string")
    return GovernedEvaluationSummary(
        allowed=_required_bool(data, "allowed"),
        policy_ids=tuple(_expect_string_list(data.get("policy_ids"), "policy_ids")),
        policies_evaluated=_required_int(data, "policies_evaluated"),
        policies_passed=_required_int(data, "policies_passed"),
        policies_failed=_required_int(data, "policies_failed"),
        policies_errored=_required_int(data, "policies_errored"),
        violation_count=_required_int(data, "violation_count"),
        statutory_anchors=tuple(
            _expect_string_list(data.get("statutory_anchors"), "statutory_anchors")
        ),
        receipt_id=receipt_id,
    )


def _expect_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be an object")
    return cast(Mapping[str, Any], value)


def _expect_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError(f"{name} must be an array")
    return value


def _expect_string_list(value: Any, name: str) -> list[str]:
    items = _expect_list(value, name)
    if any(not isinstance(item, str) for item in items):
        raise TypeError(f"{name} must contain strings")
    return cast(list[str], items)


def _required(mapping: Mapping[str, Any], key: str, expected: type[Any]) -> Any:
    value = mapping[key]
    if not isinstance(value, expected):
        raise TypeError(f"{key} has an invalid type")
    return value


def _expect_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    return value


def _required_int(mapping: Mapping[str, Any], key: str) -> int:
    return _expect_int(mapping[key], key)


def _required_bool(mapping: Mapping[str, Any], key: str) -> bool:
    value = mapping[key]
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be a boolean")
    return value
