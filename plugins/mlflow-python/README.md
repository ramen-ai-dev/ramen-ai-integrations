# ramen-ai MLflow Integration

<p align="center">
  <img src="../../assets/ramen-logo.png" alt="ramen-ai" width="100"/>
</p>

Algorithmic governance for classical ML models served via
[MLflow](https://mlflow.org/), Databricks, or MLflow Model Serving.

`RamenGovernedModel` is an `mlflow.pyfunc.PythonModel` that wraps an existing
model and interposes a ramen-ai compliance evaluation between the inference
request and the model's prediction. Feature values — and SHAP attributions where
available — are serialised and evaluated for proxy bias and regulatory
compliance. A `[BLOCKED]` verdict raises `GovernanceDeniedException` and the
wrapped model is **never invoked**.

Requires **Python ≥ 3.10** and **MLflow ≥ 2.9**.

---

<p align="center">
  <a href="https://github.com/ramen-ai-dev/ramen-ai-integrations/tree/master/plugins/langchain-python">
    <img src="https://img.shields.io/badge/LangChain-1C3C3C?style=flat&logo=langchain&logoColor=white" alt="LangChain"/>
  </a>
  &nbsp;
  <a href="https://github.com/ramen-ai-dev/ramen-ai-integrations/tree/master/plugins/pydantic-ai">
    <img src="https://img.shields.io/badge/PydanticAI-E92063?style=flat&logo=pydantic&logoColor=white" alt="PydanticAI"/>
  </a>
  &nbsp;
  <a href="https://github.com/ramen-ai-dev/ramen-ai-integrations/tree/master/plugins/mcp-proxy">
    <img src="https://img.shields.io/badge/MCP-6B21A8?style=flat&logo=anthropic&logoColor=white" alt="MCP"/>
  </a>
  &nbsp;
  <a href="https://github.com/ramen-ai-dev/ramen-ai-integrations/tree/master/plugins/agt-typescript">
    <img src="https://img.shields.io/badge/Microsoft%20AGT-0078D4?style=flat&logo=microsoft&logoColor=white" alt="Microsoft AGT"/>
  </a>
  &nbsp;
  <a href="https://github.com/ramen-ai-dev/ramen-ai-integrations/tree/master/plugins/github-action">
    <img src="https://img.shields.io/badge/GitHub%20Actions-2088FF?style=flat&logo=githubactions&logoColor=white" alt="GitHub Actions"/>
  </a>
  &nbsp;
  <a href="https://github.com/ramen-ai-dev/ramen-ai-integrations/tree/master/plugins/cmcp-python">
    <img src="https://img.shields.io/badge/cMCP-00A67E?style=flat&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PHBhdGggZmlsbD0id2hpdGUiIGQ9Ik0xMiAyTDIgN2wxMCA1IDEwLTV6TTIgMTdsOCA0VjExbC04LTR6TTE0IDIxbDgtNFYxMWwtOCA0eiIvPjwvc3ZnPg==&logoColor=white" alt="cMCP"/>
  </a>
  &nbsp;
  <a href="https://github.com/ramen-ai-dev/ramen-ai-integrations/tree/master/plugins/mlflow-python">
    <img src="https://img.shields.io/badge/MLflow-0194E2?style=flat&logo=mlflow&logoColor=white" alt="MLflow"/>
  </a>
</p>

---

## Can you bypass it?

Standard safety filters catch basic syntax. They fail against encoded payloads
and corporate jargon. We challenge you to bypass our semantic firewall using
the zero-day evasion vectors in our official **[Red Team Guide](../../RED_TEAM_GUIDE.md)**.

Below is a simulation of the Grok/Bankr heist. We fed the raw adversarial
prompt directly into our sandbox. It uses a social engineering wrapper
(claiming a visual impairment) to smuggle a 3,000,000,000 DRB transfer
instruction encoded in Morse code. The firewall evaluated the underlying
semantic intent, intercepted the unauthorized financial transfer, and blocked
it pre-execution, issuing a verified Ed25519 receipt.

<p align="center">
  <img src="../../assets/grok-bankr.png" alt="ramen-ai intercepting the Grok/Bankr Morse-code heist pre-execution" width="720"/>
</p>

---

## API Key

To use this integration, you must mint an API Key. We offer a **Free Starter
Tier** (1,000 evaluations/month, BYOK) which includes full access to our Core
IT Security bundle. Mint your key at:
**[https://ramenai.dev/pricing](https://ramenai.dev/pricing)**

---

## Why wrap the model rather than filter the input

A feature array is not text, so a keyword filter cannot evaluate it. Whether
`postcode` combined with `income` acts as an unlawful proxy for a protected
attribute is a semantic question about the *combination* of features, not any
single value. Evaluating it at the pyfunc boundary means the check runs inside
the serving process — the same place the prediction happens — so it cannot be
bypassed by calling the model directly.

---

## Installation

```bash
pip install -e plugins/mlflow-python          # from the monorepo
pip install -e "plugins/mlflow-python[dev]"   # with test dependencies
```

---

## Configuration

```bash
export RAMEN_API_KEY=ramen_ak_...   # required in the serving environment
export OPENAI_API_KEY=sk-...        # required on Starter/Professional (BYOK)
```

**The API key is never serialised into the model artifact.** It is read from the
environment at call time. Pickling a credential into a model registered in a
shared registry would expose it to everyone with read access — so the wrapper
reads it at predict time instead. There is a test asserting the key does not
appear in the instance state.

### BYOK (Bring Your Own Key)

The Starter and Professional tiers require your own LLM provider key (OpenAI,
Anthropic, etc.). `RamenGovernedModel` reads it from `OPENAI_API_KEY` and
forwards it as the `X-Provider-Key` header on every evaluation request.
Without it the API returns `402 Payment Required` on these tiers.

Set `provider_name` on the constructor to route to a non-default provider
(forwarded as `X-Provider`; accepted values: `"openai"` (default),
`"anthropic"`, `"google"`, `"synthetic"`, `"hyperbolic"`).

Enterprise tiers use platform-managed keys — the serving environment does not
need `OPENAI_API_KEY` set at all.

---

## Wrapping a scikit-learn model

```python
import mlflow
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from ramen_mlflow import RamenGovernedModel

# 1. Train as normal
clf = GradientBoostingClassifier().fit(X_train, y_train)

# 2. Wrap it
governed = RamenGovernedModel(
    bundle_ids=["ramen__eu_ai_act_baseline"],
    inner_model=clf,
    model_name="credit-risk-scorer-v3",   # recorded in the audit log
    feature_names=["income", "age", "employment_years"],  # optional subset
)

# 3. Log the governed model to the registry
with mlflow.start_run():
    info = mlflow.pyfunc.log_model(
        name="credit-risk-governed",
        python_model=governed,
        input_example=X_train.head(),
    )

# 4. Serve it — governance travels with the model
loaded = mlflow.pyfunc.load_model(info.model_uri)
predictions = loaded.predict(X_test)   # raises on a BLOCKED verdict
```

Register the logged model and every deployment of that version carries the
governance boundary with it. There is no separate gateway to configure and no
way to call the model without passing the check.

---

## Handling a block

```python
from ramen_mlflow import GovernanceDeniedException

try:
    predictions = loaded.predict(X_test)
except GovernanceDeniedException as exc:
    print(exc.steering)             # "Remove the postcode feature and re-train..."
    print(exc.statutory_anchors)    # ["EU AI Act Art. 10", "GDPR Art. 22"]
    print(exc.receipt_verified)     # True — Ed25519 receipt verified locally
    print(exc.policy_ids)           # resolved policy UUIDs
    print(exc.receipt)              # raw V5 receipt for the audit trail
```

Under MLflow Model Serving the exception surfaces as a 500 with the message.
That is intentional: a governance block is a hard stop, not a recoverable
prediction failure.

---

## Passing SHAP values

Supplying attributions lets the evaluator reason about *which* features drove the
decision, not just their values:

```python
import shap

explainer = shap.TreeExplainer(clf)
shap_values = explainer.shap_values(X_test)

loaded.predict(X_test, params={"shap_values": shap_values.tolist()})
```

A `shap_values` column on the input DataFrame is picked up automatically.

---

## Loading the wrapped model from artifacts

For deployments where the inner model is logged separately, omit `inner_model`
and provide it as an artifact under the key `inner_model`:

```python
mlflow.pyfunc.log_model(
    name="governed",
    python_model=RamenGovernedModel(bundle_ids=["ramen__eu_ai_act_baseline"]),
    artifacts={"inner_model": "runs:/<run_id>/sklearn-model"},
)
```

`load_context` resolves the artifact with `mlflow.pyfunc.load_model` on first use.

---

## API reference

### `RamenGovernedModel(...)`

| Parameter | Type | Description |
|---|---|---|
| `bundle_ids` | `list[str]` | Bundle slugs to evaluate against. One of `bundle_ids` / `policy_ids` required. |
| `policy_ids` | `list[str]` | Explicit policy UUIDs. May be combined with bundles. |
| `inner_model` | `Any` | Model to wrap; must expose `predict`. Omit to load from artifacts. |
| `feature_names` | `list[str]` | Explicit ordering / subset of features to submit. Defaults to all columns. |
| `provider_name` | `str` | BYOK routing hint (`openai` default, `anthropic`, `google`, `synthetic`, `hyperbolic`). |
| `model_name` | `str` | Label recorded in the ramen-ai audit context. |
| `base_url` | `str` | Override the API base URL. Default `https://api.ramenai.dev`. |
| `timeout` | `float` | HTTP timeout in seconds. Default `30.0`. |
| `fail_closed` | `bool` | Treat firewall errors as a BLOCK. Default `True`. |

### Supported input types

pandas DataFrame, numpy array, dict, or list of records. The input is handed to
the wrapped model **unchanged** — the wrapper never rewrites the payload.

---

## Fail-closed behaviour

Any error contacting the firewall (network failure, timeout, HTTP 4xx/5xx,
malformed response) is treated as a BLOCK by default. A missing `RAMEN_API_KEY`
also blocks. Set `fail_closed=False` only when the deployment explicitly accepts
unevaluated inference during a firewall outage:

```python
RamenGovernedModel(..., fail_closed=False)   # logs a warning, allows inference
```

---

## Running the tests

```bash
pip install -e "plugins/mlflow-python[dev]"
pytest plugins/mlflow-python/tests -v
```

21 tests, no network access and no credentials required — HTTP calls are
intercepted by `pytest-httpx`. Coverage includes: a blocked prediction halting
the pipeline (asserting the wrapped model is never called), payload
construction, SHAP forwarding, numpy input, all four fail-closed paths, and
`load_context` resolution.

---

## Limitations

- The evaluation adds one API round-trip per `predict` call. For high-throughput
  batch scoring, evaluate a representative sample offline rather than wrapping
  the serving path.
- Inputs are truncated when the serialised payload exceeds the API's 50,000
  character limit; a `_truncated` flag is set on the submitted payload.
- The wrapper evaluates features and attributions. It does not inspect model
  weights, training data, or the model's internal structure.
