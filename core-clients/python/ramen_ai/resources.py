"""Read-only resource clients: the global bundle catalogue and the receipt ledger."""
from __future__ import annotations

import builtins
from typing import Any, TypedDict, cast

import httpx

from ._http import request_json

RECEIPTS_MAX_LIMIT = 200


class BundleSummary(TypedDict):
    """A global bundle as listed by ``GET /api/v1/safety/bundles``."""

    id: str
    """The slug to pass as ``bundle_ids``, for example ``ramen__shield_core_it``."""
    name: str
    description: str | None
    policy_ids: list[str]
    policy_count: int


class ReceiptLedgerEntry(TypedDict):
    """One row of the receipt ledger.

    The ledger does not store ``canonical_payload``, so a row cannot be
    re-verified. Verify the receipt returned by ``evaluate_compliance`` instead.
    """

    id: str
    timestamp: str
    policy_ids: list[str]
    verdict: int
    """1 = ALLOW, 0 = BLOCK."""
    reasoning: str
    steering: str
    statutory_anchors: list[str]
    signature: str
    payload_hash: str


class ReceiptLedgerPagination(TypedDict):
    limit: int
    offset: int
    count: int


class ReceiptLedgerPage(TypedDict):
    receipts: list[ReceiptLedgerEntry]
    pagination: ReceiptLedgerPagination


class BundlesApi:
    """``client.bundles``: the active global bundle catalogue."""

    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def list(self) -> builtins.list[BundleSummary]:
        """List the active global bundles available to the authenticated key."""
        return cast("builtins.list[BundleSummary]", request_json(self._http, "GET", "/api/v1/safety/bundles"))


class ReceiptsApi:
    """``client.receipts``: the caller's signed receipt ledger."""

    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def list(self, *, limit: int | None = None, offset: int | None = None) -> ReceiptLedgerPage:
        """List signed evaluation receipts, newest first.

        ``limit`` is 1 to 200 (default 50). The server caps larger values
        silently, so they are rejected here with ``ValueError``.
        """
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= RECEIPTS_MAX_LIMIT
        ):
            raise ValueError(f"limit must be an integer from 1 to {RECEIPTS_MAX_LIMIT}")
        if offset is not None and (isinstance(offset, bool) or not isinstance(offset, int) or offset < 0):
            raise ValueError("offset must be a non-negative integer")
        data: Any = request_json(
            self._http,
            "GET",
            "/api/v1/paas/receipts",
            params={"limit": limit, "offset": offset},
        )
        return cast("ReceiptLedgerPage", data)
