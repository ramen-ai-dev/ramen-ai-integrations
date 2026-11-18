"""Typed errors for the evaluation, ledger, bundle and Memory Mesh clients.

Governed generation keeps its own exceptions
(:class:`ramen_ai.GovernedGenerationException`, :class:`ramen_ai.GovernanceDeniedException`).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from .types import ComplianceVerdict


class RamenApiError(httpx.HTTPStatusError):
    """The API answered with a non-success HTTP status.

    Subclasses :class:`httpx.HTTPStatusError`, so code that already catches that
    type keeps working. ``status`` is the HTTP status, ``code`` is the server's
    error code (for example ``AUTHORIZATION_REQUIRED``) or ``HTTP_<status>`` when
    the body carried none, and ``details`` is the server's optional detail
    payload. Transport failures (timeouts, DNS, TLS) are not wrapped: they
    propagate as :class:`httpx.TransportError`.
    """

    def __init__(
        self,
        message: str,
        *,
        request: httpx.Request,
        response: httpx.Response,
        code: str,
        details: Any = None,
    ) -> None:
        super().__init__(message, request=request, response=response)
        self.status: int = response.status_code
        self.code = code
        self.details = details


class ReceiptVerificationError(Exception):
    """``require_verified_receipt`` is on and the receipt did not verify.

    Treat it as a denial. ``verdict`` is the unverified result: never act on
    ``verdict["allowed"]``.
    """

    def __init__(self, reason: str, verdict: ComplianceVerdict) -> None:
        super().__init__(f"Receipt verification failed: {reason}")
        self.reason = reason
        self.verdict = verdict
