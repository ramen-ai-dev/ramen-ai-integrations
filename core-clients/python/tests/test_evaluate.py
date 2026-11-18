"""Strict receipt binding, require_verified_receipt, BYOK headers and error mapping."""
from __future__ import annotations

import httpx
import pytest

from ramen_ai import RamenApiError, ReceiptVerificationError, signed_verdict_problem
from tests.helpers import POLICY_ID, Signer, evaluation_data, make_client, ok

INPUT = "Wire 40,000 USD to account 12-34-56"
signer = Signer()
POLICY = {"policy_ids": [POLICY_ID]}


def evaluate(data: dict, **options):
    client, recorder = make_client(ok(data), public_keys=signer.keys, **options)
    with client:
        return client.evaluate_compliance(INPUT, **POLICY), recorder


# --- strict signed-verdict binding ---------------------------------------------


def test_authentic_block_receipt_verifies_when_the_response_says_blocked() -> None:
    verdict, _ = evaluate(evaluation_data(False, signer.receipt(INPUT, verdict=0)))
    assert verdict["allowed"] is False
    assert verdict["receipt_verified"] is True
    assert verdict["receipt_reason"] is None


def test_authentic_allow_receipt_verifies_when_the_response_says_allowed() -> None:
    verdict, _ = evaluate(evaluation_data(True, signer.receipt(INPUT, verdict=1)))
    assert verdict["receipt_verified"] is True


def test_genuine_block_receipt_wrapped_in_allowed_true_is_not_verified() -> None:
    verdict, _ = evaluate(evaluation_data(True, signer.receipt(INPUT, verdict=0)))
    assert verdict["receipt_verified"] is False
    assert "Verdict mismatch: payload contains 0" in verdict["receipt_reason"]


def test_genuine_allow_receipt_wrapped_in_allowed_false_is_not_verified() -> None:
    verdict, _ = evaluate(evaluation_data(False, signer.receipt(INPUT, verdict=1)))
    assert verdict["receipt_verified"] is False
    assert "Verdict mismatch: payload contains 1" in verdict["receipt_reason"]


def test_a_swapped_receipt_id_is_rejected() -> None:
    receipt = signer.receipt(INPUT, verdict=0, receipt={"id": "99999999-9999-4999-8999-999999999999"})
    verdict, _ = evaluate(evaluation_data(False, receipt))
    assert verdict["receipt_verified"] is False
    assert "Signed id does not match" in verdict["receipt_reason"]


def test_a_receipt_kid_that_differs_from_the_signed_kid_is_rejected() -> None:
    keys = {**signer.keys, "ramen_pk_other": signer.keys["ramen_pk_v1"]}
    receipt = signer.receipt(INPUT, verdict=0, receipt={"kid": "ramen_pk_other"})
    problem = signed_verdict_problem(receipt, INPUT, 0, public_keys=keys)
    assert problem is not None and "Signed kid does not match" in problem


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"executed_at": "2030-01-01T00:00:00.000Z"}, "Timestamp mismatch"),
        ({"policy_ids": ["2d2f2c8e-1111-4222-8333-444455556666"]}, "policy_ids mismatch"),
        ({"statutory_anchors": ["MiFID II Art. 25"]}, "statutory_anchors mismatch"),
        ({"statutory_anchors": []}, "statutory_anchors mismatch"),
    ],
)
def test_signed_timestamp_policy_ids_and_anchors_must_match_the_response(override: dict, fragment: str) -> None:
    receipt = signer.receipt(INPUT, verdict=0)
    verdict, _ = evaluate(evaluation_data(False, receipt, **override))
    assert verdict["receipt_verified"] is False
    assert fragment in verdict["receipt_reason"]


def test_the_evaluated_input_must_be_the_one_that_was_signed() -> None:
    client, _ = make_client(ok(evaluation_data(False, signer.receipt(INPUT, verdict=0))), public_keys=signer.keys)
    with client:
        verdict = client.evaluate_compliance(INPUT + " ", **POLICY)
    assert verdict["receipt_verified"] is False
    assert "payload_hash" in verdict["receipt_reason"]


@pytest.mark.parametrize("kid", ["ramen_pk_v999", "__proto__", "constructor", ""])
def test_unknown_kids_are_rejected(kid: str) -> None:
    receipt = signer.receipt(INPUT, verdict=0)
    problem = signed_verdict_problem({**receipt, "kid": kid}, INPUT, 0, public_keys=signer.keys)
    assert problem is not None and ("Unknown kid" in problem or "missing 'kid'" in problem)


def test_malformed_receipts_are_reported_not_raised() -> None:
    receipt = signer.receipt(INPUT, verdict=0)
    flipped = {**receipt, "signature": receipt["signature"][:-2] + "AA"}
    assert "Signature does not verify" in str(signed_verdict_problem(flipped, INPUT, 0, public_keys=signer.keys))
    assert "missing 'id'" in str(signed_verdict_problem({**receipt, "id": ""}, INPUT, 0, public_keys=signer.keys))
    assert "No Schema V5 receipt" in str(signed_verdict_problem(None, INPUT, 0, public_keys=signer.keys))
    assert "No Schema V5 receipt" in str(signed_verdict_problem("not a receipt", INPUT, 0, public_keys=signer.keys))
    assert signed_verdict_problem(receipt, INPUT, 0, public_keys=signer.keys) is None


def test_a_bool_or_out_of_range_expected_verdict_is_a_caller_bug() -> None:
    receipt = signer.receipt(INPUT, verdict=1)
    for bad in (True, 2, -1, "1"):
        with pytest.raises(ValueError):
            signed_verdict_problem(receipt, INPUT, bad, public_keys=signer.keys)  # type: ignore[arg-type]


def test_a_boolean_signed_verdict_never_counts_as_one() -> None:
    receipt = signer.receipt(INPUT, verdict=True)  # type: ignore[arg-type]
    problem = signed_verdict_problem(receipt, INPUT, 1, public_keys=signer.keys)
    assert problem is not None and "Verdict mismatch" in problem


# --- require_verified_receipt ----------------------------------------------------


def test_require_verified_receipt_passes_an_authentic_response_through() -> None:
    verdict, _ = evaluate(evaluation_data(True, signer.receipt(INPUT, verdict=1)), require_verified_receipt=True)
    assert verdict["allowed"] is True


def test_require_verified_receipt_raises_on_a_tampered_response_and_carries_the_verdict() -> None:
    client, _ = make_client(
        ok(evaluation_data(True, signer.receipt(INPUT, verdict=0))),
        public_keys=signer.keys,
        require_verified_receipt=True,
    )
    with client, pytest.raises(ReceiptVerificationError) as raised:
        client.evaluate_compliance(INPUT, **POLICY)
    assert "Verdict mismatch" in raised.value.reason
    assert raised.value.verdict["receipt_verified"] is False


def test_require_verified_receipt_raises_when_no_receipt_is_returned_and_reports_the_alert() -> None:
    data = evaluation_data(True, None, receipt_alert="RECEIPT_SIGNING_FAILED")
    client, _ = make_client(ok(data), public_keys=signer.keys, require_verified_receipt=True)
    with client, pytest.raises(ReceiptVerificationError) as raised:
        client.evaluate_compliance(INPUT, **POLICY)
    assert raised.value.reason == "RECEIPT_SIGNING_FAILED"


def test_without_require_verified_receipt_a_missing_receipt_is_reported_not_raised() -> None:
    verdict, _ = evaluate(evaluation_data(True, None))
    assert verdict["receipt_verified"] is False
    assert verdict["receipt_valid"] is None


# --- BYOK headers ---------------------------------------------------------------


def test_provider_key_and_name_are_forwarded_together() -> None:
    client, recorder = make_client(ok(evaluation_data(True)), public_keys=signer.keys)
    with client:
        client.evaluate_compliance(INPUT, provider_key="sk-provider-test", provider_name="anthropic", **POLICY)
    assert recorder.last.headers["X-Provider-Key"] == "sk-provider-test"
    assert recorder.last.headers["X-Provider"] == "anthropic"


def test_managed_mode_omits_both_provider_headers() -> None:
    client, recorder = make_client(ok(evaluation_data(True)), public_keys=signer.keys)
    with client:
        client.evaluate_compliance(INPUT, **POLICY)
    assert "X-Provider-Key" not in recorder.last.headers
    assert "X-Provider" not in recorder.last.headers


def test_a_provider_name_without_a_key_is_never_sent() -> None:
    client, recorder = make_client(ok(evaluation_data(True)), public_keys=signer.keys)
    with client:
        client.evaluate_compliance(INPUT, provider_name="anthropic", **POLICY)
    assert "X-Provider" not in recorder.last.headers


def test_one_callers_provider_key_does_not_bleed_into_the_next_request() -> None:
    client, recorder = make_client(ok(evaluation_data(True)), public_keys=signer.keys)
    with client:
        client.evaluate_compliance(INPUT, provider_key="sk-first", **POLICY)
        client.evaluate_compliance(INPUT, **POLICY)
    assert recorder.requests[0].headers["X-Provider-Key"] == "sk-first"
    assert "X-Provider-Key" not in recorder.requests[1].headers


# --- error mapping ----------------------------------------------------------------


def test_an_http_error_becomes_a_ramen_api_error_with_the_server_code_and_details() -> None:
    body = {"success": False, "error": {"code": "AUTHORIZATION_REQUIRED", "message": "Authorization required", "details": {"hint": "x"}}}
    client, _ = make_client(lambda _r: httpx.Response(401, json=body), public_keys=signer.keys)
    with client, pytest.raises(RamenApiError) as raised:
        client.evaluate_compliance(INPUT, **POLICY)
    error = raised.value
    assert error.status == 401
    assert error.code == "AUTHORIZATION_REQUIRED"
    assert error.details == {"hint": "x"}
    assert str(error).startswith("evaluate failed: Authorization required")
    assert isinstance(error, httpx.HTTPStatusError)  # existing `except httpx.HTTPStatusError` keeps working


def test_a_non_json_error_body_keeps_an_http_derived_code() -> None:
    client, _ = make_client(lambda _r: httpx.Response(502, text="<html>bad gateway</html>"), public_keys=signer.keys)
    with client, pytest.raises(RamenApiError) as raised:
        client.evaluate_compliance(INPUT, **POLICY)
    assert raised.value.status == 502
    assert raised.value.code == "HTTP_502"


def test_transport_failures_propagate_unwrapped() -> None:
    def boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client, _ = make_client(boom, public_keys=signer.keys)
    with client, pytest.raises(httpx.ConnectError):
        client.evaluate_compliance(INPUT, **POLICY)


def test_a_200_with_a_non_json_body_is_invalid_response() -> None:
    client, _ = make_client(lambda _r: httpx.Response(200, text="not json"), public_keys=signer.keys)
    with client, pytest.raises(RamenApiError) as raised:
        client.evaluate_compliance(INPUT, **POLICY)
    assert raised.value.code == "INVALID_RESPONSE"


def test_a_missing_data_envelope_fails_closed() -> None:
    client, _ = make_client(lambda _r: httpx.Response(200, json={"success": True}), public_keys=signer.keys)
    with client:
        verdict = client.evaluate_compliance(INPUT, **POLICY)
    assert verdict["allowed"] is False


def test_evaluate_compliance_still_requires_a_bundle_or_policy_id() -> None:
    client, recorder = make_client(ok(evaluation_data(True)), public_keys=signer.keys)
    with client, pytest.raises(ValueError, match="at least one of"):
        client.evaluate_compliance(INPUT)
    assert recorder.requests == []
