"""Enterprise Memory Mesh client."""
from __future__ import annotations

import httpx
import pytest

from ramen_ai import RamenApiError
from ramen_ai.memory_mesh import assert_sub_tenant_id
from tests.helpers import make_client, ok

SUB = "customer-42"
LESSON_ID = "5f0c1d2e-3a4b-4c5d-8e6f-7a8b9c0d1e2f"
RECEIPT = {"kid": "ramen_pk_v1", "signature": "c2ln", "canonical_payload": '{"schema_version":"5.0"}'}
TRAP = {
    "domain": "fintech",
    "tool": "dispatch_wire",
    "task_description": "Dispatch a wire to a new payee account",
    "arguments": {"amount_usd": 40000},
    "evaluated_input": "dispatch_wire {...}",
    "receipt": RECEIPT,
}


def test_trap_posts_the_body_and_names_the_partition_in_the_header() -> None:
    result = {"trap": {"recorded": True, "trap_id": "t1", "opened_at": "a", "expires_at": "b", "joined": False}, "steering_directive": "Use dual control"}
    client, recorder = make_client(ok(result, 201))
    with client:
        assert client.memory.trap(TRAP, sub_tenant_id=SUB) == result
    assert recorder.last.method == "POST"
    assert str(recorder.last.url) == "https://api.ramenai.dev/api/v1/memory/trap"
    assert recorder.last.headers["X-Sub-Tenant-ID"] == SUB
    assert recorder.last.headers["Authorization"] == "Bearer ramen_ak_test"
    assert recorder.body() == TRAP
    assert "sub_tenant_id" not in recorder.body() and "tenant_id" not in recorder.body()


def test_fix_and_recall_use_their_routes_and_the_partition_header() -> None:
    client, recorder = make_client(ok({}))
    with client:
        client.memory.fix({"trap_id": "t1", "arguments": {}, "evaluated_input": "x", "receipt": RECEIPT}, sub_tenant_id=SUB)
        client.memory.recall(
            {"domain": "fintech", "tool": "dispatch_wire", "task_description": "Dispatch a wire to a new payee", "arguments": {}, "include_pending": True},
            sub_tenant_id=SUB,
        )
    assert [r.url.path for r in recorder.requests] == ["/api/v1/memory/fix", "/api/v1/memory/recall"]
    assert all(r.headers["X-Sub-Tenant-ID"] == SUB for r in recorder.requests)
    assert recorder.body()["include_pending"] is True


@pytest.mark.parametrize("bad", ["", "__reserved", "has space", "a" * 129, "ok\nX-Evil: 1", None, 7])
def test_every_lesson_call_refuses_a_malformed_sub_tenant_before_any_request(bad: object) -> None:
    client, recorder = make_client(ok({}))
    with client:
        with pytest.raises(ValueError):
            client.memory.trap(TRAP, sub_tenant_id=bad)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            client.memory.recall(TRAP, sub_tenant_id=bad)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            client.memory.lessons(sub_tenant_id=bad)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            client.memory.review_lesson(LESSON_ID, "approve", sub_tenant_id=bad)  # type: ignore[arg-type]
    assert recorder.requests == []


@pytest.mark.parametrize("good", ["a", "customer-42", "org:team@example.com", "A.b_c-d", "9" * 128])
def test_assert_sub_tenant_id_accepts_the_documented_alphabet(good: str) -> None:
    assert assert_sub_tenant_id(good) == good


def test_lessons_sends_review_status_limit_and_before_as_a_query_string() -> None:
    client, recorder = make_client(ok({"lessons": [], "count": 0}))
    with client:
        client.memory.lessons(sub_tenant_id=SUB, review_status="pending_review", limit=20, before=1760000000000)
    assert recorder.last.method == "GET"
    assert dict(recorder.last.url.params) == {"review_status": "pending_review", "limit": "20", "before": "1760000000000"}
    assert recorder.last.headers["X-Sub-Tenant-ID"] == SUB


@pytest.mark.parametrize("kwargs", [{"limit": 0}, {"limit": 101}, {"limit": True}, {"before": 0}, {"before": -5}])
def test_lessons_validates_paging_before_any_request(kwargs: dict) -> None:
    client, recorder = make_client(ok({}))
    with client, pytest.raises(ValueError):
        client.memory.lessons(sub_tenant_id=SUB, **kwargs)
    assert recorder.requests == []


def test_review_lesson_patches_the_lesson_with_the_decision_and_optional_reason() -> None:
    client, recorder = make_client(ok({"lesson_id": LESSON_ID, "review_status": "approved", "vector_synced": True}))
    with client:
        client.memory.review_lesson(LESSON_ID, "approve", sub_tenant_id=SUB)
        client.memory.review_lesson(LESSON_ID, "quarantine", sub_tenant_id=SUB, reason="needs a second look")
    assert recorder.requests[0].method == "PATCH"
    assert recorder.requests[0].url.path == f"/api/v1/memory/lessons/{LESSON_ID}"
    assert recorder.body(0) == {"decision": "approve"}
    assert recorder.body(1) == {"decision": "quarantine", "reason": "needs a second look"}


@pytest.mark.parametrize("bad", ["../sub-tenants", "not-a-uuid", f"{LESSON_ID}/x", LESSON_ID.upper()])
def test_review_lesson_rejects_an_id_that_could_escape_the_path(bad: str) -> None:
    client, recorder = make_client(ok({}))
    with client, pytest.raises(ValueError):
        client.memory.review_lesson(bad, "approve", sub_tenant_id=SUB)
    assert recorder.requests == []


def test_sub_tenants_lists_without_a_partition_header() -> None:
    data = {"sub_tenants": [{"sub_tenant_id": SUB, "created_at_ms": 1, "lesson_count": 3}], "count": 1}
    client, recorder = make_client(ok(data))
    with client:
        assert client.memory.sub_tenants() == data
    assert recorder.last.url.path == "/api/v1/memory/sub-tenants"
    assert "X-Sub-Tenant-ID" not in recorder.last.headers


def test_erase_sub_tenant_deletes_the_encoded_partition_and_validates_the_id() -> None:
    client, recorder = make_client(ok({"erased": True, "lessons_removed": 3}))
    with client:
        assert client.memory.erase_sub_tenant("org:team@example.com") == {"erased": True, "lessons_removed": 3}
        with pytest.raises(ValueError):
            client.memory.erase_sub_tenant("../lessons")
    assert recorder.last.method == "DELETE"
    assert recorder.last.url.raw_path == b"/api/v1/memory/sub-tenants/org%3Ateam%40example.com"
    assert len(recorder.requests) == 1


def test_mesh_errors_surface_the_server_code_status_and_details() -> None:
    body = {"success": False, "error": {"code": "TIER_REQUIRED", "message": "Memory Mesh needs the enterprise tier", "details": {"required": "enterprise"}}}
    client, _ = make_client(lambda _r: httpx.Response(403, json=body))
    with client, pytest.raises(RamenApiError) as raised:
        client.memory.recall(TRAP, sub_tenant_id=SUB)
    assert raised.value.status == 403
    assert raised.value.code == "TIER_REQUIRED"
    assert raised.value.details == {"required": "enterprise"}


def test_a_recall_that_finds_nothing_returns_match_false() -> None:
    client, _ = make_client(ok({"match": False}))
    with client:
        assert client.memory.recall(TRAP, sub_tenant_id=SUB) == {"match": False}
