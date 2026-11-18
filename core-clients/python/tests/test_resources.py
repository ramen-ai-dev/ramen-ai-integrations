"""Bundle catalogue and receipt ledger clients."""
from __future__ import annotations

import httpx
import pytest

from ramen_ai import RamenApiError
from ramen_ai.resources import RECEIPTS_MAX_LIMIT
from tests.helpers import make_client, ok

BUNDLE = {
    "id": "ramen__shield_core_it",
    "name": "Core IT Security",
    "description": None,
    "policy_ids": ["1006492f-db62-4f46-8775-48b966c5c956"],
    "policy_count": 1,
}


def test_bundles_list_issues_an_authenticated_get_and_returns_the_catalogue() -> None:
    client, recorder = make_client(ok([BUNDLE]))
    with client:
        assert client.bundles.list() == [BUNDLE]
    assert recorder.last.method == "GET"
    assert str(recorder.last.url) == "https://api.ramenai.dev/api/v1/safety/bundles"
    assert recorder.last.headers["Authorization"] == "Bearer ramen_ak_test"


def test_receipts_list_sends_limit_and_offset_and_returns_the_page() -> None:
    page = {"receipts": [], "pagination": {"limit": 25, "offset": 50, "count": 0}}
    client, recorder = make_client(ok(page))
    with client:
        assert client.receipts.list(limit=25, offset=50) == page
    assert str(recorder.last.url) == "https://api.ramenai.dev/api/v1/paas/receipts?limit=25&offset=50"


def test_receipts_list_without_options_sends_no_query_string() -> None:
    client, recorder = make_client(ok({"receipts": [], "pagination": {}}))
    with client:
        client.receipts.list()
    assert str(recorder.last.url) == "https://api.ramenai.dev/api/v1/paas/receipts"


@pytest.mark.parametrize(
    "kwargs",
    [{"limit": 0}, {"limit": RECEIPTS_MAX_LIMIT + 1}, {"limit": True}, {"limit": "5"}, {"offset": -1}, {"offset": 0.5}, {"offset": True}],
)
def test_receipts_list_rejects_out_of_range_pagination_before_any_request(kwargs: dict) -> None:
    client, recorder = make_client(ok({}))
    with client, pytest.raises(ValueError):
        client.receipts.list(**kwargs)
    assert recorder.requests == []


def test_resource_errors_are_ramen_api_errors_with_the_server_code() -> None:
    body = {"success": False, "error": {"code": "AUTHORIZATION_REQUIRED", "message": "Authorization header required"}}
    client, _ = make_client(lambda _r: httpx.Response(401, json=body))
    with client:
        for call in (client.bundles.list, client.receipts.list):
            with pytest.raises(RamenApiError) as raised:
                call()
            assert raised.value.status == 401
            assert raised.value.code == "AUTHORIZATION_REQUIRED"
            assert str(raised.value) == "Authorization header required"


@pytest.mark.parametrize("body", [[BUNDLE], {"success": False, "data": [BUNDLE]}, {"success": True}])
def test_a_success_body_that_is_not_the_envelope_is_invalid_response(body: object) -> None:
    client, _ = make_client(lambda _r: httpx.Response(200, json=body))
    with client, pytest.raises(RamenApiError) as raised:
        client.bundles.list()
    assert raised.value.code == "INVALID_RESPONSE"
