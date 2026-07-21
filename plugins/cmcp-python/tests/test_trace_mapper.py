"""Tests for ramen_cmcp.trace_mapper and ramen_cmcp._receipt_verify.

Fixtures are the mathematically-verified V5 test vectors from
v5-conformance.md §5. The ephemeral public key (ramen_pk_ephemeral_test)
is embedded in _receipt_verify._AUDIT_PUBLIC_KEYS, so no network access or
real credentials are needed to run these tests.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ramen_cmcp.trace_mapper import build_trace_record, _validate_receipt
from ramen_cmcp._receipt_verify import verify_v5_receipt

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "fixtures"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _dummy_jwk() -> dict:
    return {"kty": "OKP", "crv": "Ed25519", "x": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="}


# ---------------------------------------------------------------------------
# verify_v5_receipt — conformance vectors
# ---------------------------------------------------------------------------

class TestVerifyV5Receipt:
    def test_vector1_allowed_valid(self):
        f = _load("vector1_allowed.json")
        valid, reason = verify_v5_receipt(f["receipt"], f["input"])
        assert valid is True
        assert reason is None

    def test_vector1_verdict_is_1(self):
        f = _load("vector1_allowed.json")
        payload = json.loads(f["receipt"]["canonical_payload"])
        assert payload["verdict"] == 1

    def test_vector1_reasoning_empty(self):
        f = _load("vector1_allowed.json")
        payload = json.loads(f["receipt"]["canonical_payload"])
        assert payload["reasoning"] == ""

    def test_vector1_steering_empty(self):
        f = _load("vector1_allowed.json")
        payload = json.loads(f["receipt"]["canonical_payload"])
        assert payload["steering"] == ""

    def test_vector2_blocked_valid(self):
        f = _load("vector2_blocked.json")
        valid, reason = verify_v5_receipt(f["receipt"], f["input"])
        assert valid is True
        assert reason is None

    def test_vector2_verdict_is_0(self):
        f = _load("vector2_blocked.json")
        payload = json.loads(f["receipt"]["canonical_payload"])
        assert payload["verdict"] == 0

    def test_vector2_reasoning_nonempty(self):
        f = _load("vector2_blocked.json")
        payload = json.loads(f["receipt"]["canonical_payload"])
        assert payload["reasoning"] != ""

    def test_vector2_steering_equals_expected(self):
        f = _load("vector2_blocked.json")
        payload = json.loads(f["receipt"]["canonical_payload"])
        assert payload["steering"] == f["expected"]["steering"]

    def test_vector1_payload_hash_matches_sha256_of_input(self):
        f = _load("vector1_allowed.json")
        expected = hashlib.sha256(f["input"].encode("utf-8")).hexdigest()
        payload = json.loads(f["receipt"]["canonical_payload"])
        assert payload["payload_hash"] == expected

    def test_vector2_payload_hash_matches_sha256_of_input(self):
        f = _load("vector2_blocked.json")
        expected = hashlib.sha256(f["input"].encode("utf-8")).hexdigest()
        payload = json.loads(f["receipt"]["canonical_payload"])
        assert payload["payload_hash"] == expected

    # ── negative vectors ────────────────────────────────────────────────────

    def test_n1_tampered_signature_fails(self):
        """N1: flipped final base64url char — signature verification must fail."""
        f = _load("vector_n1_bad_sig.json")
        valid, reason = verify_v5_receipt(f["receipt"], f["input"])
        assert valid is False
        assert reason is not None
        assert "Signature" in reason or "signature" in reason

    def test_n2_wrong_input_fails_binding(self):
        """N2: authentic receipt, different input — payload_hash binding must fail."""
        f = _load("vector1_allowed.json")
        tampered_input = f["input"] + " "  # trailing space changes SHA-256
        valid, reason = verify_v5_receipt(f["receipt"], tampered_input)
        assert valid is False
        assert reason is not None
        assert "payload_hash" in reason

    def test_n2_original_input_still_passes(self):
        """Control: the same receipt with the original input must still pass."""
        f = _load("vector1_allowed.json")
        valid, reason = verify_v5_receipt(f["receipt"], f["input"])
        assert valid is True
        assert reason is None

    def test_unknown_kid_fails(self):
        f = _load("vector1_allowed.json")
        bad_receipt = dict(f["receipt"], kid="ramen_pk_unknown_xyz")
        valid, reason = verify_v5_receipt(bad_receipt, f["input"])
        assert valid is False
        assert "Unknown kid" in (reason or "")


# ---------------------------------------------------------------------------
# build_trace_record — field mapping
# ---------------------------------------------------------------------------

class TestBuildTraceRecord:
    @pytest.fixture(scope="class")
    @classmethod
    def v1_record(cls):
        f = _load("vector1_allowed.json")
        return build_trace_record(f["receipt"], iat=1_800_000_000, jwk=_dummy_jwk())

    @pytest.fixture(scope="class")
    @classmethod
    def v2_record(cls):
        f = _load("vector2_blocked.json")
        return build_trace_record(f["receipt"], iat=1_800_000_001, jwk=_dummy_jwk())

    # ── structural ──────────────────────────────────────────────────────────

    def test_eat_profile(self, v1_record):
        assert v1_record["eat_profile"] == "tag:agentrust.io,2026:trace-v0.1"

    def test_iat_is_passed_through(self, v1_record):
        assert v1_record["iat"] == 1_800_000_000

    def test_cnf_jwk_is_embedded(self, v1_record):
        assert v1_record["cnf"]["jwk"] == _dummy_jwk()

    def test_transparency_is_pending(self, v1_record):
        assert v1_record["transparency"] == "pending"

    def test_runtime_platform_software_only(self, v1_record):
        assert v1_record["runtime"]["platform"] == "software-only"

    def test_tool_transcript_call_count_is_1(self, v1_record):
        assert v1_record["tool_transcript"]["call_count"] == 1

    def test_no_cmcp_envelope_markers(self, v1_record):
        """trace-tests 0.1.0 rejects plain records with these top-level keys."""
        assert not {"signature", "trace", "gateway"} & v1_record.keys()

    # ── field mapping — allowed receipt ─────────────────────────────────────

    def test_subject_encodes_kid_and_receipt_id(self, v1_record):
        f = _load("vector1_allowed.json")
        receipt = f["receipt"]
        assert v1_record["subject"] == (
            f"spiffe://ramenai.dev/evaluation/{receipt['id']}"
        )

    def test_policy_bundle_hash_is_prefixed_payload_hash(self, v1_record):
        f = _load("vector1_allowed.json")
        payload = json.loads(f["receipt"]["canonical_payload"])
        assert v1_record["policy"]["bundle_hash"] == f"sha256:{payload['payload_hash']}"

    def test_policy_version_is_schema_version(self, v1_record):
        assert v1_record["policy"]["version"] == "5.0"

    def test_policy_enforcement_mode_is_enforce(self, v1_record):
        assert v1_record["policy"]["enforcement_mode"] == "enforce"

    def test_runtime_measurement_is_receipt_id(self, v1_record):
        f = _load("vector1_allowed.json")
        assert v1_record["runtime"]["measurement"] == f["receipt"]["id"]

    def test_tool_transcript_hash_is_prefixed_payload_hash(self, v1_record):
        f = _load("vector1_allowed.json")
        payload = json.loads(f["receipt"]["canonical_payload"])
        assert v1_record["tool_transcript"]["hash"] == f"sha256:{payload['payload_hash']}"

    def test_transcript_uri_encodes_receipt_id(self, v1_record):
        f = _load("vector1_allowed.json")
        assert v1_record["tool_transcript"]["transcript_uri"] == (
            f"urn:ramen-ai:evaluation:{f['receipt']['id']}"
        )

    def test_appraisal_policy_ref_contains_policy_id(self, v1_record):
        assert "f47ac10b-58cc-4372-a567-0e02b2c3d479" in v1_record["appraisal"]["policy_ref"]

    def test_appraisal_status_affirming_for_allowed(self, v1_record):
        assert v1_record["appraisal"]["status"] == "affirming"

    def test_appraisal_statutory_anchors_populated(self, v1_record):
        assert "FCA COBS 4.2.1" in v1_record["appraisal"]["statutory_anchors"]

    def test_steering_omitted_when_empty(self, v1_record):
        """Vector 1 has empty steering — must not appear in the record."""
        assert "steering" not in v1_record["appraisal"]

    # ── field mapping — blocked receipt ─────────────────────────────────────

    def test_appraisal_status_denying_for_blocked(self, v2_record):
        assert v2_record["appraisal"]["status"] == "denying"

    def test_appraisal_statutory_anchors_for_blocked(self, v2_record):
        anchors = v2_record["appraisal"]["statutory_anchors"]
        assert "FCA PRIN 2A.2.8" in anchors
        assert "MiFID II Art. 25" in anchors

    def test_steering_present_when_nonempty(self, v2_record):
        """Vector 2 has non-empty steering — must appear in appraisal."""
        assert "steering" in v2_record["appraisal"]
        assert v2_record["appraisal"]["steering"] != ""

    # ── _validate_receipt guards ─────────────────────────────────────────────

    def test_missing_field_raises(self):
        with pytest.raises(ValueError, match="missing required fields"):
            _validate_receipt({"id": "x", "schema_version": "5.0", "kid": "k"})

    def test_wrong_schema_version_raises(self):
        f = _load("vector1_allowed.json")
        bad = dict(f["receipt"], schema_version="4.0")
        with pytest.raises(ValueError, match="schema_version"):
            _validate_receipt(bad)

    def test_invalid_canonical_payload_json_raises(self):
        f = _load("vector1_allowed.json")
        bad = dict(f["receipt"], canonical_payload="{not json}")
        with pytest.raises(ValueError, match="canonical_payload"):
            _validate_receipt(bad)

    # ── tamper probe ─────────────────────────────────────────────────────────

    def test_tampered_policy_hash_changes_record(self):
        """Mutating the fixture canonical_payload must change bundle_hash."""
        f = _load("vector1_allowed.json")
        original_record = build_trace_record(
            f["receipt"], iat=1_800_000_000, jwk=_dummy_jwk()
        )
        # Build a tampered receipt with a different payload_hash
        payload = json.loads(f["receipt"]["canonical_payload"])
        payload["payload_hash"] = "a" * 64
        tampered_receipt = dict(
            f["receipt"],
            canonical_payload=json.dumps(payload, separators=(",", ":")),
        )
        # _validate_receipt won't fail (structure is valid) but the mapping
        # must reflect the tampered hash — and the original hash must differ.
        tampered_record = build_trace_record(
            tampered_receipt, iat=1_800_000_000, jwk=_dummy_jwk()
        )
        assert tampered_record["policy"]["bundle_hash"] == f"sha256:{'a' * 64}"
        assert original_record["policy"]["bundle_hash"] != tampered_record["policy"]["bundle_hash"]
