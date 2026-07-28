"""
ramen_mlflow.wrapper — algorithmic governance for MLflow pyfunc models.

:class:`RamenGovernedModel` is an ``mlflow.pyfunc.PythonModel`` that wraps an
existing model and interposes a ramen-ai compliance evaluation between the
inference request and the wrapped model's prediction.

Flow
----
1. ``predict`` receives ``model_input`` (a pandas DataFrame, numpy array, dict,
   or list of records).
2. The active feature values are extracted and serialised to JSON. When SHAP
   values are supplied via ``params["shap_values"]`` — or a ``shap_values``
   column is present — they are included so the evaluator can reason about
   *which* features drove the decision, not just their values.
3. The serialised payload is sent to the ramen-ai evaluation API against the
   configured bundles / policies.
4. On ALLOWED, the wrapped model's prediction is returned unchanged.
   On BLOCKED, :exc:`GovernanceDeniedException` is raised and the wrapped model
   is never invoked.

Credential handling
-------------------
The ramen-ai API key is **never** stored on the instance and never serialised
into the MLflow artifact. It is read from ``RAMEN_API_KEY`` in the serving
environment at call time. The same applies to the BYOK provider key
(``OPENAI_API_KEY``). Pickling a secret into a model artifact registered in a
shared model registry would leak it to anyone with read access to the registry.

Fail-closed
-----------
Any error raised while contacting the firewall (network failure, timeout, HTTP
4xx/5xx, malformed response) is treated as a BLOCK when ``fail_closed=True``
(the default). An unreachable governance boundary must not become an open door.
Set ``fail_closed=False`` only when the deployment explicitly accepts
unevaluated inference during a firewall outage.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import mlflow.pyfunc

from ramen_ai import RamenClient

from .exceptions import GovernanceDeniedException

logger = logging.getLogger(__name__)

_MAX_INPUT_CHARS = 50_000  # ramen-ai API limit for `input`


class RamenGovernedModel(mlflow.pyfunc.PythonModel):
    """
    An MLflow pyfunc wrapper that enforces ramen-ai algorithmic governance on
    every inference request.

    Parameters
    ----------
    bundle_ids:
        Pre-built ramen-ai bundle slugs to evaluate against, e.g.
        ``["ramen__eu_ai_act_baseline"]``. At least one of *bundle_ids* or
        *policy_ids* must be supplied.
    policy_ids:
        Explicit policy UUIDs. May be combined with *bundle_ids*.
    inner_model:
        The model to wrap, for in-process use. Must expose ``predict``. When
        omitted, the wrapped model is loaded in :meth:`load_context` from
        ``context.artifacts["inner_model"]`` via ``mlflow.pyfunc.load_model``.
    feature_names:
        Optional explicit ordering / subset of feature names to submit for
        evaluation. When ``None``, all columns of the input are used.
    provider_name:
        BYOK provider routing hint forwarded as ``X-Provider``. One of
        ``"openai"`` (default), ``"anthropic"``, ``"google"``, ``"synthetic"``,
        ``"hyperbolic"``.
    model_name:
        A label recorded in the ramen-ai audit context, e.g.
        ``"credit-risk-scorer-v3"``. Useful for tracing verdicts back to a
        registered model version.
    base_url:
        Override the ramen-ai API base URL.
    timeout:
        HTTP timeout in seconds for the evaluation call.
    fail_closed:
        Treat firewall errors as a BLOCK. Defaults to ``True``.

    Raises
    ------
    ValueError
        If neither *bundle_ids* nor *policy_ids* is supplied.
    """

    def __init__(
        self,
        *,
        bundle_ids: list[str] | None = None,
        policy_ids: list[str] | None = None,
        inner_model: Any = None,
        feature_names: list[str] | None = None,
        provider_name: str | None = None,
        model_name: str | None = None,
        base_url: str = "https://api.ramenai.dev",
        timeout: float = 30.0,
        fail_closed: bool = True,
    ) -> None:
        if not bundle_ids and not policy_ids:
            raise ValueError(
                "Provide at least one of 'bundle_ids' or 'policy_ids'."
            )
        self.bundle_ids = bundle_ids
        self.policy_ids = policy_ids
        self.feature_names = feature_names
        self.provider_name = provider_name
        self.model_name = model_name
        self.base_url = base_url
        self.timeout = timeout
        self.fail_closed = fail_closed

        # May be None when the model is loaded from artifacts at serve time.
        self._inner_model = inner_model

    # ------------------------------------------------------------------ #
    # MLflow lifecycle                                                     #
    # ------------------------------------------------------------------ #

    def load_context(self, context: mlflow.pyfunc.PythonModelContext) -> None:
        """Load the wrapped model from artifacts when one was not supplied.

        Called once by MLflow before the first ``predict``. If the constructor
        received an ``inner_model`` it is kept; otherwise the artifact under the
        ``inner_model`` key is loaded as a pyfunc model.
        """
        if self._inner_model is not None:
            return
        artifact_uri = (context.artifacts or {}).get("inner_model")
        if artifact_uri is None:
            raise ValueError(
                "No inner_model supplied to the constructor and no "
                "'inner_model' artifact found in the MLflow context. Log the "
                "wrapped model as an artifact under the key 'inner_model'."
            )
        self._inner_model = mlflow.pyfunc.load_model(artifact_uri)

    # NOTE: intentionally un-annotated. MLflow infers a model signature from
    # `predict` type hints and coerces inputs to match. This wrapper is a
    # passthrough that accepts DataFrame / numpy / dict / list and must hand the
    # input to the wrapped model unchanged, so declaring e.g. `list[Any]` would
    # misrepresent it and risk MLflow rewriting the payload. Supply an
    # `input_example` or explicit `signature` to `log_model` for validation.
    def predict(self, context, model_input, params=None):
        """Evaluate the request for compliance, then delegate to the model.

        Args:
            context: MLflow-supplied context (unused beyond ``load_context``).
            model_input: The inference input. pandas DataFrame, numpy array,
                dict, or list of records.
            params: Optional MLflow inference params. A ``shap_values`` entry is
                forwarded to the evaluator as attribution context.

        Returns:
            The wrapped model's prediction, unchanged, when ALLOWED.

        Raises:
            GovernanceDeniedException: on a BLOCKED verdict, or on any firewall
                error when ``fail_closed=True``.
        """
        payload = self._build_payload(model_input, params)
        self._enforce(payload)
        return self._inner_model.predict(model_input)

    # ------------------------------------------------------------------ #
    # Internals                                                            #
    # ------------------------------------------------------------------ #

    def _enforce(self, payload: str) -> None:
        """Call the firewall and raise on a BLOCKED verdict. Fails closed."""
        api_key = os.environ.get("RAMEN_API_KEY", "")
        if not api_key:
            raise GovernanceDeniedException(
                steering=(
                    "RAMEN_API_KEY is not set in the serving environment; "
                    "the governance boundary cannot be evaluated."
                ),
                receipt_verified=False,
                statutory_anchors=[],
            )

        context_meta: dict[str, str] = {"integration": "mlflow"}
        if self.model_name:
            context_meta["model_name"] = self.model_name

        try:
            with RamenClient(
                api_key=api_key, base_url=self.base_url, timeout=self.timeout
            ) as client:
                result = client.evaluate_compliance(
                    input_text=payload,
                    bundle_ids=self.bundle_ids,
                    policy_ids=self.policy_ids,
                    context=context_meta,
                    provider_key=os.environ.get("OPENAI_API_KEY"),
                    provider_name=self.provider_name,
                )
        except Exception as exc:
            if not self.fail_closed:
                logger.warning(
                    "ramen-ai evaluation failed and fail_closed=False; "
                    "allowing inference unevaluated: %s",
                    exc,
                )
                return
            raise GovernanceDeniedException(
                steering=(
                    f"ramen-ai firewall unreachable ({type(exc).__name__}); "
                    f"failing closed."
                ),
                receipt_verified=False,
                statutory_anchors=[],
            ) from exc

        if not result["allowed"]:
            data = result.get("data") or {}
            raise GovernanceDeniedException(
                steering=result.get("steering"),
                receipt_verified=result.get("receipt_verified", False),
                statutory_anchors=data.get("statutory_anchors") or [],
                policy_ids=result.get("policy_ids"),
                receipt=data.get("receipt"),
            )

    def _build_payload(
        self, model_input: Any, params: dict[str, Any] | None
    ) -> str:
        """Serialise the active feature values (and SHAP values) to JSON."""
        features = self._extract_features(model_input)

        body: dict[str, Any] = {"features": features}
        if self.model_name:
            body["model"] = self.model_name

        shap_values = self._extract_shap(model_input, params)
        if shap_values is not None:
            body["shap_values"] = shap_values

        payload = json.dumps(body, sort_keys=True, default=str)

        if len(payload) > _MAX_INPUT_CHARS:
            # The API rejects inputs over 50k chars with a 422. Truncating the
            # record set keeps large batches evaluable rather than erroring.
            body["features"] = features[:1] if isinstance(features, list) else features
            body["_truncated"] = True
            payload = json.dumps(body, sort_keys=True, default=str)
        return payload

    def _extract_features(self, model_input: Any) -> Any:
        """Normalise supported MLflow input types into JSON-safe records."""
        # pandas DataFrame — the standard pyfunc input type
        if hasattr(model_input, "to_dict") and hasattr(model_input, "columns"):
            frame = model_input
            if self.feature_names:
                keep = [c for c in self.feature_names if c in frame.columns]
                frame = frame[keep]
            return frame.to_dict(orient="records")

        # numpy array
        if hasattr(model_input, "tolist"):
            rows = model_input.tolist()
            if self.feature_names:
                return [dict(zip(self.feature_names, row)) for row in rows]
            return rows

        # dict or list of records — already JSON-shaped
        return model_input

    def _extract_shap(
        self, model_input: Any, params: dict[str, Any] | None
    ) -> Any:
        """Pull SHAP values from inference params or an input column."""
        if params and "shap_values" in params:
            shap = params["shap_values"]
            return shap.tolist() if hasattr(shap, "tolist") else shap

        if hasattr(model_input, "columns") and "shap_values" in model_input.columns:
            return model_input["shap_values"].tolist()

        return None
