"""RemoteForgeMemoryStore (ramen forge) and verify_allow_receipt_signature."""
from __future__ import annotations

import hashlib
import logging

import httpx
import pytest

from ramen_ai import (
    FORGE_DEFAULT_BASE_URL,
    ForgeWriteError,
    RemoteForgeMemoryStore,
    build_provenance,
    verify_allow_receipt_signature,
)
from tests.helpers import Recorder, Signer

signer = Signer()
TASK = "Dispatch a wire to a new payee account"
FINGERPRINT = hashlib.sha256(TASK.encode()).hexdigest()


def served(**overrides: object) -> dict:
    record = {
        "exemplar_id": "1c639e7b-f999-431d-b162-071301cdb623",
        "domain": "fintech",
        "task_description": TASK,
        "task_fingerprint": FINGERPRINT,
        "tool_name": "dispatch_wire",
        "failed_arguments": {},
        "violation_reason": "Dual control missing",
        "primary_statutory_anchor": "UCC 4A",
        "steering_directive": "Add a second approver",
        "repaired_arguments": {"approvers": 2},
        "receipt_id": None,
        "created_at": "2026-11-01T00:00:00.000Z",
    }
    record.update(overrides)
    return record


def store(handler, **options) -> tuple[RemoteForgeMemoryStore, Recorder]:
    recorder = Recorder(handler)
    http = httpx.Client(transport=httpx.MockTransport(recorder))
    return RemoteForgeMemoryStore(http_client=http, domain="fintech", public_keys=signer.keys, **options), recorder


def contribution(**overrides: object) -> dict:
    payload = {
        "exemplar_id": "ex-1",
        "task_description": TASK,
        "tool_name": "dispatch_wire",
        "failed_arguments": {"approvers": 1},
        "violation_reason": "Dual control missing",
        "primary_statutory_anchor": "UCC 4A",
        "steering_directive": "Add a second approver",
        "repaired_arguments": {"approvers": 2},
        "created_at": "2026-11-01T00:00:00.000Z",
        "receipt": signer.receipt("repaired call", verdict=1),
    }
    payload.update(overrides)
    return payload


def test_the_default_base_url_is_the_canonical_forge_host() -> None:
    assert FORGE_DEFAULT_BASE_URL == "https://forge.ramenai.dev"
    assert RemoteForgeMemoryStore().base_url == "https://forge.ramenai.dev"


def test_construction_validates_scheme_domain_and_timeout() -> None:
    with pytest.raises(ValueError, match="https"):
        RemoteForgeMemoryStore(base_url="http://forge.example.com")
    RemoteForgeMemoryStore(base_url="http://localhost:8787")
    with pytest.raises(ValueError, match="slug"):
        RemoteForgeMemoryStore(domain="Not A Slug")
    with pytest.raises(ValueError, match="timeout"):
        RemoteForgeMemoryStore(timeout=0)


def test_repr_never_includes_the_write_token() -> None:
    forge = RemoteForgeMemoryStore(write_token="super-secret-token")
    assert "super-secret-token" not in repr(forge)
    assert forge.writable is True


def test_retrieve_sends_filters_and_returns_matching_exemplars() -> None:
    forge, recorder = store(lambda _r: httpx.Response(200, json={"success": True, "exemplars": [served()]}))
    result = forge.retrieve_relevant_exemplars(tool_name="dispatch_wire", query="wire dual control", limit=5)
    assert [e["exemplar_id"] for e in result] == ["1c639e7b-f999-431d-b162-071301cdb623"]
    assert dict(recorder.last.url.params) == {"domain": "fintech", "limit": "5", "tool_name": "dispatch_wire", "q": "wire dual control"}
    assert "Authorization" not in recorder.last.headers


@pytest.mark.parametrize(
    "kwargs",
    [{"limit": 0}, {"limit": 51}, {"query": "  "}, {"query": "x" * 101}, {"task_fingerprint": "ABC"}, {"tool_name": " "}, {"domain": "BAD DOMAIN"}],
)
def test_invalid_retrieval_options_raise_before_any_request(kwargs: dict) -> None:
    forge, recorder = store(lambda _r: httpx.Response(200, json={"exemplars": []}))
    with pytest.raises(ValueError):
        forge.retrieve_relevant_exemplars(**kwargs)
    assert recorder.requests == []


def test_retrieval_fails_open_on_http_errors_transport_errors_and_bad_bodies(caplog: pytest.LogCaptureFixture) -> None:
    def refuse(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    cases = [
        (lambda _r: httpx.Response(503, text="busy"), "HTTP 503"),
        (refuse, "down"),
        (lambda _r: httpx.Response(200, text="not json"), ""),
        (lambda _r: httpx.Response(200, json={"exemplars": "nope"}), "unexpected response shape"),
    ]
    for handler, _expect in cases:
        forge, _ = store(handler)
        with caplog.at_level(logging.WARNING, logger="ramen_ai.forge"):
            assert forge.retrieve_relevant_exemplars() == []
    assert any("continuing without exemplars" in r.message for r in caplog.records)


def test_retrieval_skips_invalid_and_off_domain_records() -> None:
    records = [served(), {"exemplar_id": "broken"}, served(domain="hrtech", exemplar_id="other-domain"), served(tool_name="other_tool", exemplar_id="other-tool")]
    forge, _ = store(lambda _r: httpx.Response(200, json={"exemplars": records}))
    result = forge.retrieve_relevant_exemplars(tool_name="dispatch_wire")
    assert [e["exemplar_id"] for e in result] == ["1c639e7b-f999-431d-b162-071301cdb623"]


def test_a_contribution_without_a_receipt_is_skipped_without_a_request() -> None:
    forge, recorder = store(lambda _r: httpx.Response(201, json={}), write_token="t")
    result = forge.record_correction(contribution(receipt=None))
    assert result["status"] == "skipped"
    assert recorder.requests == []


def test_a_read_only_store_refuses_to_write() -> None:
    forge, recorder = store(lambda _r: httpx.Response(201, json={}))
    with pytest.raises(ForgeWriteError, match="read-only"):
        forge.record_correction(contribution())
    assert recorder.requests == []


def test_only_a_signed_allow_receipt_is_accepted() -> None:
    forge, recorder = store(lambda _r: httpx.Response(201, json={}), write_token="t")
    with pytest.raises(ForgeWriteError, match="not a verified ALLOW receipt"):
        forge.record_correction(contribution(receipt=signer.receipt("blocked call", verdict=0)))
    with pytest.raises(ForgeWriteError, match="not a verified ALLOW receipt"):
        forge.record_correction(contribution(receipt={**signer.receipt("x", verdict=1), "signature": "AAAA"}))
    assert recorder.requests == []


def test_a_contribution_posts_only_accepted_keys_with_a_bearer_token() -> None:
    forge, recorder = store(lambda _r: httpx.Response(201, json={"success": True, "exemplar_id": "ex-1"}), write_token="tok")
    result = forge.record_correction(contribution(extra_unknown_key="dropped"))
    assert result == {"status": "created", "exemplar_id": "ex-1"}
    body = recorder.body()
    assert recorder.last.headers["Authorization"] == "Bearer tok"
    assert "extra_unknown_key" not in body
    assert body["task_fingerprint"] == FINGERPRINT
    assert body["receipt_id"] == body["receipt"]["id"]
    assert body["domain"] == "fintech"


def test_mismatched_fingerprint_or_receipt_id_is_rejected_before_any_request() -> None:
    forge, recorder = store(lambda _r: httpx.Response(201, json={}), write_token="t")
    with pytest.raises(ForgeWriteError, match="task_fingerprint"):
        forge.record_correction(contribution(task_fingerprint="0" * 64))
    with pytest.raises(ForgeWriteError, match="receipt_id"):
        forge.record_correction(contribution(receipt_id="someone-else"))
    with pytest.raises(ForgeWriteError, match="task_description"):
        forge.record_correction(contribution(task_description="  "))
    assert recorder.requests == []


def test_duplicate_refreshed_and_rejected_responses_are_distinguished() -> None:
    forge, _ = store(lambda _r: httpx.Response(409, json={}), write_token="t")
    assert forge.record_correction(contribution())["status"] == "duplicate"
    forge, _ = store(lambda _r: httpx.Response(200, json={"refreshed": True, "exemplar_id": "kept-id"}), write_token="t")
    assert forge.record_correction(contribution()) == {"status": "refreshed", "exemplar_id": "kept-id"}
    body = {"error": {"code": "VALIDATION", "message": "bad shape"}, "details": ["a", "b"]}
    forge, _ = store(lambda _r: httpx.Response(422, json=body), write_token="t")
    with pytest.raises(ForgeWriteError, match="HTTP 422.*VALIDATION: bad shape: a; b") as raised:
        forge.record_correction(contribution())
    assert raised.value.status == 422


def test_a_transport_failure_on_write_raises() -> None:
    def refuse(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    forge, _ = store(refuse, write_token="t")
    with pytest.raises(ForgeWriteError, match="write failed"):
        forge.record_correction(contribution())


def test_audit_uri_and_provenance_envelope() -> None:
    forge, _ = store(lambda _r: httpx.Response(200, json={}))
    exemplar = served()
    assert forge.audit_uri(exemplar).startswith("https://forge.ramenai.dev/api/v1/exemplars?domain=fintech&tool_name=dispatch_wire")
    envelope = build_provenance(domain="fintech", tool_name="dispatch_wire", receipt_id="r1", exemplar=exemplar, store=forge)
    assert envelope["source"] == "ramen-forge" and envelope["version"] == "1.0"
    assert envelope["exemplar_id"] == exemplar["exemplar_id"] and envelope["audit_uri"] == forge.audit_uri(exemplar)
    local = build_provenance(domain="fintech", tool_name="dispatch_wire")
    assert local["source"] == "ramen-local" and local["audit_uri"] is None and local["exemplar_id"] is None


def test_verify_allow_receipt_signature() -> None:
    ok_receipt = signer.receipt("anything", verdict=1)
    assert verify_allow_receipt_signature(ok_receipt, public_keys=signer.keys) == (True, None)
    valid, reason = verify_allow_receipt_signature(signer.receipt("anything", verdict=0), public_keys=signer.keys)
    assert valid is False and "not 1" in reason
    valid, reason = verify_allow_receipt_signature({**ok_receipt, "id": "swapped"}, public_keys=signer.keys)
    assert valid is False and "Signed id" in reason
    assert verify_allow_receipt_signature(None, public_keys=signer.keys)[0] is False
