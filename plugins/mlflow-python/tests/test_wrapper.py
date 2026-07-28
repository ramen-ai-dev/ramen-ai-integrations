"""
Tests for ramen_mlflow.wrapper.RamenGovernedModel.

All HTTP calls are intercepted by pytest-httpx — no network access, no real
credentials. Response fixtures mirror the V5 production envelope shape.

The central assertion is that a BLOCKED verdict halts the inference pipeline:
GovernanceDeniedException is raised and the wrapped model's predict is never
called.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from pytest_httpx import HTTPXMock

from ramen_mlflow import GovernanceDeniedException, RamenGovernedModel

API_URL = "https://api.ramenai.dev/api/v1/paas/evaluate"


# --------------------------------------------------------------------------- #
# Test doubles                                                                  #
# --------------------------------------------------------------------------- #

class SpyModel:
    """Stand-in for a wrapped sklearn model; records whether it ran."""

    def __init__(self) -> None:
        self.called = False
        self.last_input = None

    def predict(self, model_input):
        self.called = True
        self.last_input = model_input
        return [0.87] * len(model_input)


# --------------------------------------------------------------------------- #
# API fixtures                                                                  #
# --------------------------------------------------------------------------- #

ALLOWED_RESPONSE = {
    "success": True,
    "data": {
        "allowed": True,
        "policy_ids": ["f47ac10b-58cc-4372-a567-0e02b2c3d479"],
        "policies_evaluated": 1,
        "policies_passed": 1,
        "policies_failed": 0,
        "policies_errored": 0,
        "total_violations": [],
        "results": [],
        "execution_time_ms": 11,
        "executed_at": "2026-06-20T09:00:00.000Z",
        "statutory_anchors": [],
        "receipt": None,
        "receipt_alert": None,
    },
}

BLOCKED_RESPONSE = {
    "success": True,
    "data": {
        "allowed": False,
        "policy_ids": ["b94f3c1d-e2a6-4c89-8d02-f5a12b3c4d56"],
        "policies_evaluated": 1,
        "policies_passed": 0,
        "policies_failed": 1,
        "policies_errored": 0,
        "total_violations": [
            {
                "rule_id": "c1d2e3f4-a5b6-7890-cdef-012345678901",
                "rule_name": "No Proxy Discrimination",
                "rule_content": "Features must not act as proxies for protected attributes.",
                "enforcement_level": "strict",
                "reasoning": "postcode + income act as a proxy for ethnicity.",
                "recovery_instruction": "Remove the postcode feature and re-train, or document a lawful basis.",
            }
        ],
        "results": [],
        "execution_time_ms": 22,
        "executed_at": "2026-06-20T09:01:00.000Z",
        "statutory_anchors": ["EU AI Act Art. 10", "GDPR Art. 22"],
        "receipt": None,
        "receipt_alert": None,
    },
}


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"income": 42000, "postcode": "SW1A", "age": 31},
            {"income": 88000, "postcode": "N1", "age": 45},
        ]
    )


def _model(**kwargs) -> tuple[RamenGovernedModel, SpyModel]:
    spy = SpyModel()
    governed = RamenGovernedModel(
        bundle_ids=["ramen__eu_ai_act_baseline"],
        inner_model=spy,
        model_name="test-scorer",
        **kwargs,
    )
    return governed, spy


@pytest.fixture(autouse=True)
def _creds(monkeypatch):
    monkeypatch.setenv("RAMEN_API_KEY", "ramen_ak_test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


# --------------------------------------------------------------------------- #
# Constructor                                                                   #
# --------------------------------------------------------------------------- #

class TestConstructor:
    def test_requires_bundle_or_policy_ids(self):
        with pytest.raises(ValueError, match="bundle_ids"):
            RamenGovernedModel(inner_model=SpyModel())

    def test_accepts_policy_ids_alone(self):
        RamenGovernedModel(
            policy_ids=["f47ac10b-58cc-4372-a567-0e02b2c3d479"],
            inner_model=SpyModel(),
        )

    def test_api_key_is_not_stored_on_instance(self):
        """The key must never be serialised into the MLflow artifact."""
        governed, _ = _model()
        assert "ramen_ak_test" not in json.dumps(vars(governed), default=str)


# --------------------------------------------------------------------------- #
# BLOCKED — the pipeline must halt                                              #
# --------------------------------------------------------------------------- #

class TestBlockedHaltsInference:
    def test_raises_governance_denied(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(url=API_URL, json=BLOCKED_RESPONSE)
        governed, spy = _model()
        with pytest.raises(GovernanceDeniedException):
            governed.predict(None, _frame())

    def test_inner_model_never_runs(self, httpx_mock: HTTPXMock):
        """The decisive assertion: the wrapped model is not invoked."""
        httpx_mock.add_response(url=API_URL, json=BLOCKED_RESPONSE)
        governed, spy = _model()
        with pytest.raises(GovernanceDeniedException):
            governed.predict(None, _frame())
        assert spy.called is False
        assert spy.last_input is None

    def test_exception_carries_steering(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(url=API_URL, json=BLOCKED_RESPONSE)
        governed, _ = _model()
        with pytest.raises(GovernanceDeniedException) as exc_info:
            governed.predict(None, _frame())
        assert "Remove the postcode feature" in (exc_info.value.steering or "")

    def test_exception_carries_statutory_anchors(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(url=API_URL, json=BLOCKED_RESPONSE)
        governed, _ = _model()
        with pytest.raises(GovernanceDeniedException) as exc_info:
            governed.predict(None, _frame())
        anchors = exc_info.value.statutory_anchors
        assert "EU AI Act Art. 10" in anchors
        assert "GDPR Art. 22" in anchors

    def test_message_is_prefixed_blocked(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(url=API_URL, json=BLOCKED_RESPONSE)
        governed, _ = _model()
        with pytest.raises(GovernanceDeniedException, match=r"\[BLOCKED\]"):
            governed.predict(None, _frame())


# --------------------------------------------------------------------------- #
# ALLOWED — prediction passes through                                           #
# --------------------------------------------------------------------------- #

class TestAllowedPassesThrough:
    def test_returns_inner_prediction(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(url=API_URL, json=ALLOWED_RESPONSE)
        governed, spy = _model()
        result = governed.predict(None, _frame())
        assert spy.called is True
        assert result == [0.87, 0.87]

    def test_inner_model_receives_original_input(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(url=API_URL, json=ALLOWED_RESPONSE)
        governed, spy = _model()
        frame = _frame()
        governed.predict(None, frame)
        pd.testing.assert_frame_equal(spy.last_input, frame)


# --------------------------------------------------------------------------- #
# Payload construction                                                          #
# --------------------------------------------------------------------------- #

class TestPayload:
    def test_features_are_submitted(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(url=API_URL, json=ALLOWED_RESPONSE)
        governed, _ = _model()
        governed.predict(None, _frame())
        body = json.loads(httpx_mock.get_requests()[0].content)
        submitted = json.loads(body["input"])
        assert submitted["features"][0]["income"] == 42000
        assert submitted["features"][0]["postcode"] == "SW1A"

    def test_model_name_in_payload_and_context(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(url=API_URL, json=ALLOWED_RESPONSE)
        governed, _ = _model()
        governed.predict(None, _frame())
        body = json.loads(httpx_mock.get_requests()[0].content)
        assert json.loads(body["input"])["model"] == "test-scorer"
        assert body["context"]["model_name"] == "test-scorer"
        assert body["context"]["integration"] == "mlflow"

    def test_feature_names_subset_is_respected(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(url=API_URL, json=ALLOWED_RESPONSE)
        governed, _ = _model(feature_names=["income", "age"])
        governed.predict(None, _frame())
        body = json.loads(httpx_mock.get_requests()[0].content)
        record = json.loads(body["input"])["features"][0]
        assert set(record.keys()) == {"income", "age"}

    def test_shap_values_from_params_are_forwarded(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(url=API_URL, json=ALLOWED_RESPONSE)
        governed, _ = _model()
        governed.predict(None, _frame(), params={"shap_values": [[0.4, 0.5, 0.1]]})
        body = json.loads(httpx_mock.get_requests()[0].content)
        assert json.loads(body["input"])["shap_values"] == [[0.4, 0.5, 0.1]]

    def test_numpy_input_is_supported(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(url=API_URL, json=ALLOWED_RESPONSE)
        import numpy as np

        governed, spy = _model(feature_names=["a", "b"])
        governed.predict(None, np.array([[1, 2], [3, 4]]))
        body = json.loads(httpx_mock.get_requests()[0].content)
        assert json.loads(body["input"])["features"][0] == {"a": 1, "b": 2}


# --------------------------------------------------------------------------- #
# Fail-closed behaviour                                                         #
# --------------------------------------------------------------------------- #

class TestFailClosed:
    def test_transport_error_blocks_by_default(self, httpx_mock: HTTPXMock):
        import httpx

        httpx_mock.add_exception(httpx.ConnectError("firewall unreachable"))
        governed, spy = _model()
        with pytest.raises(GovernanceDeniedException, match="failing closed"):
            governed.predict(None, _frame())
        assert spy.called is False

    def test_http_500_blocks_by_default(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(url=API_URL, status_code=500, json={"error": "boom"})
        governed, spy = _model()
        with pytest.raises(GovernanceDeniedException):
            governed.predict(None, _frame())
        assert spy.called is False

    def test_fail_open_allows_when_explicitly_configured(self, httpx_mock: HTTPXMock):
        import httpx

        httpx_mock.add_exception(httpx.ConnectError("firewall unreachable"))
        governed, spy = _model(fail_closed=False)
        result = governed.predict(None, _frame())
        assert spy.called is True
        assert result == [0.87, 0.87]

    def test_missing_api_key_blocks(self, monkeypatch, httpx_mock: HTTPXMock):
        monkeypatch.delenv("RAMEN_API_KEY", raising=False)
        governed, spy = _model()
        with pytest.raises(GovernanceDeniedException, match="RAMEN_API_KEY"):
            governed.predict(None, _frame())
        assert spy.called is False


# --------------------------------------------------------------------------- #
# load_context                                                                  #
# --------------------------------------------------------------------------- #

class TestLoadContext:
    def test_keeps_supplied_inner_model(self):
        governed, spy = _model()
        governed.load_context(None)
        assert governed._inner_model is spy

    def test_raises_without_model_or_artifact(self):
        class Ctx:
            artifacts: dict = {}

        governed = RamenGovernedModel(bundle_ids=["ramen__eu_ai_act_baseline"])
        with pytest.raises(ValueError, match="inner_model"):
            governed.load_context(Ctx())
