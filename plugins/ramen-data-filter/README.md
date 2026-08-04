# ramen-ai Data Filter

<p align="center">
  <img src="../../assets/ramen-logo.png" alt="ramen-ai" width="100"/>
</p>

Dual-mode Pandas and CSV filtration for RAG ingestion scrubbing and MLOps
dataset sanitization. Every row is evaluated through the ramen-ai semantic
firewall before it can enter a retrieval corpus, training set, analytics store,
or downstream data pipeline.

Use **Strict Exclusion** to remove blocked rows, or **Semantic Imputation** to
preserve row count while replacing only explicitly allowlisted columns named by
ramen-ai steering. Typical policies can detect PII, data-exfiltration vectors,
poisoned retrieval context, prompt injection, and other unsafe dataset content.

Requires **Python ≥ 3.10**.

---

## Supported Ecosystems

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
  &nbsp;
  <a href="https://github.com/ramen-ai-dev/ramen-ai-integrations/tree/master/plugins/ramen-data-filter">
    <img src="https://img.shields.io/badge/ramen%20data%20filter-D97706?style=flat&logo=pandas&logoColor=white" alt="ramen data filter"/>
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

## Installation

From PyPI after release:

```bash
pip install ramen-data-filter
```

From this monorepo:

```bash
pip install -e plugins/ramen-data-filter
pip install -e "plugins/ramen-data-filter[dev]"  # include pytest
```

---

## Configuration / BYOK

```bash
export RAMEN_API_KEY=ramen_ak_...   # required
export OPENAI_API_KEY=sk-...        # Starter/Professional BYOK
```

`RAMEN_API_KEY` authenticates the evaluation request. The Starter and
Professional tiers also require an LLM provider key. The plugin reads
`OPENAI_API_KEY` at evaluation time and `ramen-ai-core` forwards it as the
`X-Provider-Key` header. Without a provider key, those tiers return
`402 Payment Required`.

Pass `provider_name="anthropic"`, `"google"`, `"synthetic"`, or
`"hyperbolic"` with the corresponding `provider_key` when OpenAI is not the
provider. Enterprise tiers use platform-managed provider keys and do not need
`OPENAI_API_KEY`.

Credentials are read from environment variables or passed at runtime. Never
store them in source code, notebooks, CSV files, or committed configuration.

---

## Usage

### Strict Exclusion

Strict exclusion evaluates each row and returns a new DataFrame containing only
`[ALLOWED]` rows. The returned index is reset; the source DataFrame is not
modified.

```python
import pandas as pd
from ramen_data_filter import FiltrationMode, filter_dataframe

records = pd.DataFrame(
    [
        {"document_id": "doc-1", "content": "Approved public documentation"},
        {"document_id": "doc-2", "content": "Retrieved untrusted context"},
    ]
)

result = filter_dataframe(
    records,
    mode=FiltrationMode.STRICT_EXCLUSION,
    bundle_ids=["ramen__shield_core_it"],
)

clean_records = result.dataframe
print(result.audit_log[["row_index", "verdict", "receipt_verified"]])
```

### Semantic Imputation

Semantic imputation preserves every row. A blocked row may change only a column
that is both listed in `remediable_columns` and named in the ramen-ai steering
instruction. Numeric columns receive the allowed-reference mean (rounded for
integer data); non-numeric columns use deterministic hot-deck values from
allowed rows. All other values remain unchanged.

```python
result = filter_dataframe(
    records,
    mode=FiltrationMode.SEMANTIC_IMPUTATION,
    policy_ids=["<POLICY_UUID>"],
    remediable_columns=["content"],
)

sanitized_records = result.dataframe
print(result.imputation_log)
```

### CSV pipeline

```python
from ramen_data_filter import FiltrationMode, filter_csv

result = filter_csv(
    "rag-ingestion.csv",
    "rag-ingestion-sanitized.csv",
    mode=FiltrationMode.STRICT_EXCLUSION,
    bundle_ids=["ramen__shield_core_it"],
)
```

The destination is written only after every row has been evaluated and the
transformation succeeds. Existing destination files are replaced by Pandas.

---

## How it works

1. Serializes each row as stable, key-sorted JSON.
2. Calls `RamenClient.evaluate_compliance` with configured bundles or policies.
3. Records the verdict, steering, resolved policy IDs, receipt verification
   state, and complete SDK response in `audit_log`.
4. Applies the selected mode only after all rows have been evaluated.
5. Returns a new DataFrame and transformation metadata; CSV usage writes that
   DataFrame with `index=False`.

The pipeline is fail-closed. Missing credentials, transport failures, malformed
responses, unsafe imputation steering, and unusable reference values raise
`FiltrationError`; partial filtered output is never returned or written.

---

## API reference

### `filter_dataframe(dataframe, *, mode, ...) -> FiltrationResult`

| Parameter | Type | Description |
|---|---|---|
| `dataframe` | `pandas.DataFrame` | Source records. The input is not modified. |
| `mode` | `FiltrationMode \| str` | `strict_exclusion` or `semantic_imputation`. |
| `bundle_ids` | `Sequence[str]` | ramen-ai bundle slugs. At least one bundle or policy is required. |
| `policy_ids` | `Sequence[str]` | Explicit policy UUIDs. May be combined with bundles. |
| `remediable_columns` | `Sequence[str]` | Columns eligible for steering-constrained replacement. Required for semantic imputation. |
| `client` | `RamenClient` | Optional injected client, primarily for controlled runtimes and tests. |
| `api_key` | `str` | Runtime override; defaults to `RAMEN_API_KEY`. |
| `provider_key` | `str` | BYOK override; defaults to `OPENAI_API_KEY`. |
| `provider_name` | `str` | Optional BYOK provider routing hint. |
| `context` | `dict[str, str]` | Additional audit metadata. |
| `base_url` | `str` | ramen-ai API base URL. |
| `timeout` | `float` | HTTP timeout in seconds. |

### `filter_csv(source_path, destination_path, **kwargs) -> FiltrationResult`

Reads the source with `pandas.read_csv`, applies `filter_dataframe`, and writes
the resulting DataFrame with `index=False`.

### `FiltrationResult`

| Attribute | Description |
|---|---|
| `dataframe` | Filtered or imputed DataFrame. |
| `audit_log` | One row per evaluation with verdict and SDK response metadata. |
| `imputation_log` | One row per transformed record; empty in strict mode. |

Public exports: `FiltrationError`, `FiltrationMode`, `FiltrationResult`,
`filter_dataframe`, and `filter_csv`.

---

## Running the tests

```bash
PYTHONPATH="core-clients/python:plugins/ramen-data-filter/src" \
  python -m pytest plugins/ramen-data-filter/tests -v
```

The isolated tests use a mocked `RamenClient`; they make no network calls and
require no credentials. They prove blocked-row exclusion and constrained
semantic imputation on a dummy DataFrame.

---

## Available bundles

| Bundle slug | Useful dataset coverage |
|---|---|
| `ramen__shield_core_it` | Secret exfiltration, prompt leakage, jailbreaks, destructive instructions, and indirect prompt injection. |
| `ramen__eu_ai_act_baseline` | EU AI Act data-governance, prohibited-practice, and transparency controls. |

Pass explicit `policy_ids` for custom PII, ingestion, data-quality, or internal
MLOps controls. Bundle and policy details are available at
[ramenai.dev/pricing](https://ramenai.dev/pricing).

---

## Limitations

- Evaluation adds one API request per row. Large datasets should be processed in
  controlled batches with rate limits and resumability at the orchestration
  layer.
- Semantic imputation creates synthetic values; it does not recover original
  truth or establish legal compliance, statistical fairness, or model quality.
- Imputed rows are not automatically re-evaluated. Validate and, where required,
  re-evaluate transformed output before production ingestion or training.
- Non-numeric hot-deck replacement is deterministic and may alter dataset
  distributions. Preserve source data and review `audit_log` and
  `imputation_log` in an access-controlled audit store.
