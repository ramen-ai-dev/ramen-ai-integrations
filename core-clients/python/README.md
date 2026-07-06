# ramen-ai-core (Python)

Agnostic Python HTTP client and V5 Ed25519 receipt verifier for the
[ramen-ai](https://ramenai.dev) PaaS evaluation API.

Requires Python ≥ 3.10. Dependencies: [`httpx`](https://www.python-httpx.org/)
and [`cryptography`](https://cryptography.io/).

---

## API Key

To use this integration, you must mint an API Key. We offer a **Free Starter Tier** (1,000 evaluations/month, BYOK) which includes full access to our Core IT Security bundle. Mint your key at: **[https://ramenai.dev/pricing](https://ramenai.dev/pricing)**

---

## Installation

```bash
pip install -e ".[dev]"
# or, from the monorepo root:
pip install -e core-clients/python
```

---

## Usage

```python
import os
from ramen_ai import RamenClient

with RamenClient(api_key=os.environ["RAMEN_API_KEY"]) as client:
    result = client.evaluate_compliance(
        input_text="Recommend the highest-commission product to this customer.",
        bundle_ids=["ramen__eu_ai_act_baseline"],
    )

print(result["allowed"])          # False
print(result["receipt_verified"]) # True  (Ed25519 + hash binding verified)
print(result["steering"])         # "Reassess product suitability..."
```

### BYOK (Bring Your Own Key)

The Starter and Professional tiers require your own LLM provider key. Pass it
as `provider_key` — it is forwarded as the `X-Provider-Key` header on every
evaluation request. Without it, the API returns `402 Payment Required` on these
tiers.

```python
client = RamenClient(
    api_key=os.environ["RAMEN_API_KEY"],
    provider_key=os.environ.get("OPENAI_API_KEY"),  # BYOK: Starter/Pro tiers
)
```

Enterprise tiers use platform-managed keys — omit `provider_key` entirely.

---

## API

### `RamenClient(api_key, *, base_url?, provider_key?, timeout?)`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `api_key` | `str` | yes | ramen-ai bearer token (`ramen_ak_...`). |
| `provider_key` | `str` | Starter/Pro | LLM provider key forwarded as `X-Provider-Key`. |
| `base_url` | `str` | no | Override the API base URL (default: `https://api.ramenai.dev`). |
| `timeout` | `float` | no | Request timeout in seconds (default: `30.0`). |

Supports use as a context manager (`with RamenClient(...) as client:`).

### `client.evaluate_compliance(input_text, *, bundle_ids?, policy_ids?, context?)`

Evaluates `input_text` against the specified policies or bundles. At least one
of `bundle_ids` or `policy_ids` must be supplied.

Returns a `dict` with the following keys:

| Key | Type | Description |
|---|---|---|
| `allowed` | `bool` | Compliance verdict. |
| `receipt_verified` | `bool` | `True` if the V5 Ed25519 receipt is present and both verification steps passed. |
| `receipt_valid` | `bool \| None` | Raw verification result; `None` if no receipt was present. |
| `receipt_reason` | `str \| None` | Failure reason if not verified. |
| `receipt_alert` | `str \| None` | Populated if the API could not sign the receipt. |
| `steering` | `str \| None` | Pipe-joined recovery instructions for the host agent; `None` on allow. |
| `policy_ids` | `list[str]` | Resolved policy UUIDs that were evaluated and signed. |
| `data` | `dict` | Full `EvaluationResponse` payload. |

---

## Testing

```bash
pytest
```

## Available bundles

| Bundle slug | Coverage |
|---|---|
| `ramen__shield_core_it` | Destructive execution, prompt injection, secret exfiltration, OWASP ASI-06 |
| `ramen__eu_ai_act_baseline` | EU AI Act Articles 5, 10, and 50 |
