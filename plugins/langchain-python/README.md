# ramen-ai LangChain Integration

<p align="center">
  <img src="../../assets/ramen-logo.svg" alt="ramen-ai" width="100"/>
</p>

An L2 Semantic Firewall callback handler for [LangChain](https://python.langchain.com/).
Intercepts agent tool calls pre-execution, evaluates the serialized tool
definition and input against the ramen-ai PaaS evaluation API, and halts
the LangChain execution chain by raising `RamenSafetyException` on a
`[BLOCKED]` verdict. Every evaluation is backed by a locally-verified V5
Ed25519 cryptographic receipt.

Requires Python ≥ 3.10 and `langchain-core ≥ 0.2`.

---

## API Key

To use this integration, you must mint an API Key. We offer a **Free Starter
Tier** (1,000 evaluations/month, BYOK) which includes full access to our Core
IT Security bundle. Mint your key at:
**[https://ramenai.dev/pricing](https://ramenai.dev/pricing)**

---

## Installation

```bash
pip install -e ".[dev]"
# or from the monorepo root:
pip install -e plugins/langchain-python
```

---

## Quickstart

```python
import os
from langchain.agents import AgentExecutor
from ramen_langchain import RamenSafetyCallbackHandler, RamenSafetyException

handler = RamenSafetyCallbackHandler(
    api_key=os.environ["RAMEN_API_KEY"],
    bundle_ids=["ramen__shield_core_it"],
    # BYOK: required on Starter/Professional tiers. Omit on Enterprise.
    provider_key=os.environ.get("OPENAI_API_KEY"),
)

try:
    result = agent_executor.invoke(
        {"input": user_prompt},
        config={"callbacks": [handler]},
    )
    print(result["output"])

except RamenSafetyException as exc:
    # Tool call was halted pre-execution.
    print(f"Blocked: {exc.steering}")
    print(f"Anchors: {exc.statutory_anchors}")
    print(f"Receipt verified: {exc.receipt_verified}")
```

### BYOK (Bring Your Own Key)

The Starter and Professional tiers require your own LLM provider key (OpenAI,
Anthropic, etc.). Pass it as `provider_key` — forwarded as the
`X-Provider-Key` header on every evaluation request. Without it, the API
returns `402 Payment Required` on these tiers.

```bash
export RAMEN_API_KEY=ramen_ak_...
export OPENAI_API_KEY=sk-...
```

Enterprise tiers use platform-managed keys — omit `provider_key` entirely.

---

## How it works

```
LangChain Agent
  │
  ├── LLM decides to call a tool
  │
  ▼
on_tool_start(serialized, input_str)          ← RamenSafetyCallbackHandler
  │
  ├── Construct payload: {tool, description, input}
  ├── POST /api/v1/paas/evaluate  →  ramen-ai firewall
  ├── Verify V5 Ed25519 receipt locally
  │
  ├── ALLOWED  →  return (tool._run() proceeds normally)
  └── BLOCKED  →  raise RamenSafetyException (tool._run() never called)
```

The handler sits in LangChain's callback pipeline and fires **before** the
tool's `_run` / `_arun` method is invoked. Raising an exception from
`on_tool_start` propagates up through the `AgentExecutor` and halts the
chain. The tool call is never executed.

**Fail-closed:** Any exception during the evaluation request (network error,
timeout, `5xx`) is treated as a BLOCK and raises `RamenSafetyException`. An
unreachable firewall never becomes an open door.

---

## API

### `RamenSafetyCallbackHandler`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `api_key` | `str` | yes | ramen-ai bearer token (`ramen_ak_...`). |
| `bundle_ids` | `list[str]` | one of | Bundle slugs to evaluate against. |
| `policy_ids` | `list[str]` | one of | Explicit policy UUIDs. |
| `provider_key` | `str` | Starter/Pro | LLM provider key forwarded as `X-Provider-Key`. |
| `base_url` | `str` | no | Override the API base URL. |
| `timeout` | `float` | no | Request timeout in seconds (default `30.0`). |
| `require_receipt_verified` | `bool` | no | When `True` (default), an ALLOWED verdict with an unverifiable receipt is escalated to a BLOCK. |
| `context` | `dict[str, str]` | no | Metadata forwarded to the audit log on every request. |

### `RamenSafetyException`

Raised on a BLOCKED verdict. Attributes:

| Attribute | Type | Description |
|---|---|---|
| `tool_name` | `str` | The name of the blocked tool. |
| `steering` | `str \| None` | Deterministic recovery instruction for the host agent. |
| `receipt_verified` | `bool` | Whether the Ed25519 V5 receipt was locally verified. |
| `statutory_anchors` | `list[str]` | Regulatory provisions that grounded the block. |

---

## Running the example

```bash
cd plugins/langchain-python
pip install -e ".[dev]"
export RAMEN_API_KEY=ramen_ak_...
export OPENAI_API_KEY=sk-...
python examples/test_agent.py
```

The default prompt is benign and produces an `ALLOWED` verdict. To see the
firewall block a destructive command, follow the swap instructions in the
example file.

---

## Available bundles

| Bundle slug | Coverage |
|---|---|
| `ramen__shield_core_it` | Destructive execution, prompt injection, secret exfiltration, OWASP ASI-06 |
| `ramen__eu_ai_act_baseline` | EU AI Act Articles 5, 10, and 50 |
