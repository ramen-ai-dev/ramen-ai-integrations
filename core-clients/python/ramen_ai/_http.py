"""Shared JSON transport for the ledger, bundle and Memory Mesh clients."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from .errors import RamenApiError


def error_from_response(response: httpx.Response, *, prefix: str | None = None) -> RamenApiError:
    """Build a :class:`RamenApiError` from a non-success response."""
    code = f"HTTP_{response.status_code}"
    message = f"HTTP {response.status_code} {response.reason_phrase}".strip()
    details: Any = None
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        error = body["error"]
        if isinstance(error.get("code"), str) and error["code"]:
            code = error["code"]
        if isinstance(error.get("message"), str) and error["message"]:
            message = error["message"]
        details = error.get("details")
    if prefix:
        message = f"{prefix}: {message}"
    return RamenApiError(
        message,
        request=response.request,
        response=response,
        code=code,
        details=details,
    )


def request_json(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    params: Mapping[str, Any] | None = None,
    json: Any = None,
    headers: Mapping[str, str] | None = None,
) -> Any:
    """Send one request and return the envelope's ``data``.

    Non-success statuses raise :class:`RamenApiError`. A success body that is
    not the ``{"success": true, "data": ...}`` envelope raises it too, with the
    code ``INVALID_RESPONSE``.
    """
    query = {key: value for key, value in (params or {}).items() if value is not None}
    response = client.request(
        method,
        path,
        params=query or None,
        json=json,
        headers=dict(headers) if headers else None,
    )
    if not response.is_success:
        raise error_from_response(response)
    try:
        body = response.json()
    except ValueError as error:
        raise _invalid(response, "Response body was not valid JSON") from error
    if not isinstance(body, dict) or body.get("success") is False or "data" not in body:
        raise _invalid(response, "Response did not use the { success, data } envelope")
    return body["data"]


def _invalid(response: httpx.Response, message: str) -> RamenApiError:
    return RamenApiError(
        message,
        request=response.request,
        response=response,
        code="INVALID_RESPONSE",
    )
