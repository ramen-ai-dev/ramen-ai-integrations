"""Enterprise Memory Mesh client (``/api/v1/memory/*``).

The mesh is tenant-partitioned. Every call except listing and erasing
sub-tenants names a sub-tenant through the ``X-Sub-Tenant-ID`` header, which is
the only way to choose a partition: request bodies never carry ``tenant_id`` or
``sub_tenant_id``, and the server rejects them if they do.

Requires an enterprise-tier key with the ``memory:write`` (trap, fix),
``memory:read`` (recall, lessons) and ``memory:admin`` (review, sub-tenants)
scopes. Lesson text is community-style data: treat it as data, never as
instructions.
"""
from __future__ import annotations

import re
from urllib.parse import quote
from collections.abc import Mapping
from typing import Any, Literal, TypedDict, cast

import httpx

from ._http import request_json

_SUB_TENANT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
_LESSON_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
LESSONS_MAX_LIMIT = 100

MemoryReviewStatus = Literal["pending_triage", "pending_review", "quarantined", "approved", "rejected"]
MemoryReviewDecision = Literal["approve", "reject", "quarantine"]


class MemoryReceipt(TypedDict):
    """The receipt fields the mesh verifies. Pass the receipt from ``evaluate_compliance``."""

    kid: str
    signature: str
    canonical_payload: str


class _MemoryViolationRequired(TypedDict):
    rule_id: str
    rule_name: str


class MemoryViolation(_MemoryViolationRequired, total=False):
    reasoning: str
    recovery_instruction: str


class _TrapRequestRequired(TypedDict):
    domain: str
    tool: str
    task_description: str
    """16 to 1000 characters, at least 3 words."""
    arguments: dict[str, Any]
    evaluated_input: str
    """The exact string that was evaluated and signed (BLOCK receipt)."""
    receipt: MemoryReceipt


class TrapRequest(_TrapRequestRequired, total=False):
    violations: list[MemoryViolation]


class TrapInfo(TypedDict):
    recorded: Literal[True]
    trap_id: str
    opened_at: str
    expires_at: str
    joined: bool


class _TrapResultRequired(TypedDict):
    trap: TrapInfo
    steering_directive: str


class TrapResult(_TrapResultRequired, total=False):
    statutory_anchor: str


class FixRequest(TypedDict):
    trap_id: str
    arguments: dict[str, Any]
    evaluated_input: str
    """The exact string that was evaluated and signed (ALLOW receipt)."""
    receipt: MemoryReceipt


class Pairing(TypedDict):
    paired: Literal[True]
    handle: Literal["matched", "corroborated"]
    trap_id: str
    lesson_id: str
    review_status: MemoryReviewStatus


class FixResult(TypedDict):
    pairing: Pairing
    receipt_verified: Literal[True]


class _RecallRequestRequired(TypedDict):
    domain: str
    tool: str
    task_description: str
    arguments: dict[str, Any]


class RecallRequest(_RecallRequestRequired, total=False):
    include_pending: bool
    """Also match lessons that are still ``pending_review``. Default: approved only."""


class ReceiptRef(TypedDict):
    id: str
    signature: str


class _RecallLessonRequired(TypedDict):
    lesson_id: str
    review_status: str
    domain: str
    tool: str
    steering_directive: str
    compliant_arguments: Any
    changed_paths: Any
    block_receipt: ReceiptRef
    allow_receipt: ReceiptRef


class RecallLesson(_RecallLessonRequired, total=False):
    statutory_anchor: str


class RecallMiss(TypedDict):
    match: Literal[False]


class RecallHit(TypedDict):
    match: Literal[True]
    tier: Literal["exact", "semantic"]
    score: float
    lesson: RecallLesson


RecallResult = RecallHit | RecallMiss


class ReviewQueueLesson(RecallLesson):
    """A lesson in the review queue: the recall fields plus what a reviewer needs."""

    task_description: str
    violation_rule: str | None
    trap_id: str
    review_reason: str | None
    reviewed_at: str | None
    created_at: str


class LessonList(TypedDict):
    lessons: list[ReviewQueueLesson]
    count: int


class ReviewResult(TypedDict):
    lesson_id: str
    review_status: MemoryReviewStatus
    vector_synced: bool


class SubTenant(TypedDict):
    sub_tenant_id: str
    created_at_ms: int
    lesson_count: int


class SubTenantList(TypedDict):
    sub_tenants: list[SubTenant]
    count: int


class EraseResult(TypedDict):
    erased: Literal[True]
    lessons_removed: int


def assert_sub_tenant_id(value: object) -> str:
    """Return *value* if it is a valid sub-tenant id, else raise ``ValueError``."""
    if not isinstance(value, str) or not _SUB_TENANT_ID.fullmatch(value):
        raise ValueError(
            "sub_tenant_id must be 1-128 characters from A-Z a-z 0-9 . _ : @ -, "
            "starting with a letter or digit"
        )
    return value


def _partition(sub_tenant_id: object) -> dict[str, str]:
    return {"X-Sub-Tenant-ID": assert_sub_tenant_id(sub_tenant_id)}


class MemoryMeshApi:
    """``client.memory``: the Enterprise Memory Mesh."""

    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def trap(self, request: TrapRequest | Mapping[str, Any], *, sub_tenant_id: str) -> TrapResult:
        """Record a verified BLOCK. Opens a 24-hour window for the matching fix."""
        return cast(
            "TrapResult",
            request_json(self._http, "POST", "/api/v1/memory/trap", json=dict(request), headers=_partition(sub_tenant_id)),
        )

    def fix(self, request: FixRequest | Mapping[str, Any], *, sub_tenant_id: str) -> FixResult:
        """Record a verified ALLOW for an open trap. Creates a lesson that awaits review."""
        return cast(
            "FixResult",
            request_json(self._http, "POST", "/api/v1/memory/fix", json=dict(request), headers=_partition(sub_tenant_id)),
        )

    def recall(self, request: RecallRequest | Mapping[str, Any], *, sub_tenant_id: str) -> RecallResult:
        """Look up an approved lesson: exact fingerprint first, then semantic."""
        return cast(
            "RecallResult",
            request_json(self._http, "POST", "/api/v1/memory/recall", json=dict(request), headers=_partition(sub_tenant_id)),
        )

    def lessons(
        self,
        *,
        sub_tenant_id: str,
        review_status: MemoryReviewStatus | None = None,
        limit: int | None = None,
        before: int | None = None,
    ) -> LessonList:
        """List lessons in the partition, optionally by review status.

        ``limit`` is 1 to 100 (default 50). ``before`` is a cursor: a positive
        integer timestamp from a previous page.
        """
        headers = _partition(sub_tenant_id)
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= LESSONS_MAX_LIMIT
        ):
            raise ValueError(f"limit must be an integer from 1 to {LESSONS_MAX_LIMIT}")
        if before is not None and (isinstance(before, bool) or not isinstance(before, int) or before < 1):
            raise ValueError("before must be a positive integer")
        return cast(
            "LessonList",
            request_json(
                self._http,
                "GET",
                "/api/v1/memory/lessons",
                params={"review_status": review_status, "limit": limit, "before": before},
                headers=headers,
            ),
        )

    def review_lesson(
        self,
        lesson_id: str,
        decision: MemoryReviewDecision,
        *,
        sub_tenant_id: str,
        reason: str | None = None,
    ) -> ReviewResult:
        """Approve, reject or quarantine a lesson (admin scope)."""
        headers = _partition(sub_tenant_id)
        if not isinstance(lesson_id, str) or not _LESSON_ID.fullmatch(lesson_id):
            raise ValueError("lesson_id must be a lowercase UUID v4")
        body: dict[str, Any] = {"decision": decision}
        if reason is not None:
            body["reason"] = reason
        return cast(
            "ReviewResult",
            request_json(self._http, "PATCH", f"/api/v1/memory/lessons/{lesson_id}", json=body, headers=headers),
        )

    def sub_tenants(self) -> SubTenantList:
        """List the partitions that hold lessons for this tenant (admin scope)."""
        return cast("SubTenantList", request_json(self._http, "GET", "/api/v1/memory/sub-tenants"))

    def erase_sub_tenant(self, sub_tenant_id: str) -> EraseResult:
        """Permanently erase one partition: vectors first, then rows (admin scope)."""
        assert_sub_tenant_id(sub_tenant_id)
        return cast(
            "EraseResult",
            request_json(self._http, "DELETE", f"/api/v1/memory/sub-tenants/{_quote(sub_tenant_id)}"),
        )


def _quote(value: str) -> str:
    """Percent-encode a path segment like ``encodeURIComponent`` does."""
    return quote(value, safe="")


__all__ = [
    "EraseResult",
    "FixRequest",
    "FixResult",
    "LessonList",
    "MemoryMeshApi",
    "MemoryReceipt",
    "MemoryReviewDecision",
    "MemoryReviewStatus",
    "MemoryViolation",
    "RecallLesson",
    "RecallRequest",
    "RecallResult",
    "ReviewQueueLesson",
    "ReviewResult",
    "SubTenant",
    "SubTenantList",
    "TrapRequest",
    "TrapResult",
    "assert_sub_tenant_id",
]
