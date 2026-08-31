# ramen-ai LangChain Integration

<p align="center">
  <img src="../../assets/ramen-logo.png" alt="ramen-ai" width="100"/>
</p>


An L2 Semantic Firewall callback handler for [LangChain](https://python.langchain.com/).
Intercepts agent tool calls pre-execution, evaluates the serialized tool
definition and input against the ramen-ai PaaS evaluation API, and halts
the LangChain execution chain by raising `RamenSafetyException` on a
`[BLOCKED]` verdict. Every evaluation is backed by a locally-verified V5
Ed25519 cryptographic receipt.

Requires Python ≥ 3.10 and `langchain-core ≥ 0.2`.

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
  &nbsp;
  <a href="https://github.com/ramen-ai-dev/ramen-ai-integrations/tree/master/plugins/ramen-data-filter">
    <img src="https://img.shields.io/badge/ramen%20data%20filter-D97706?style=flat&logo=pandas&logoColor=white" alt="ramen data filter"/>
  </a>
  &nbsp;
  <a href="https://github.com/ramen-ai-dev/dsh-ramen-guard">
    <img src="https://img.shields.io/badge/DeepSeek%20Harness-4D6BFE?style=flat&logo=deepseek&logoColor=white" alt="DeepSeek Harness"/>
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
    # BYOK: required on Starter/Professional tiers. Omit both on Enterprise.
    provider_key=os.environ.get("OPENAI_API_KEY"),
    provider_name="openai" if os.environ.get("OPENAI_API_KEY") else None,
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
Anthropic, etc.). Pass it as `provider_key` and identify its provider with
`provider_name`; the pair is forwarded as the `X-Provider-Key` and
`X-Provider` headers on every evaluation request. Without a provider key,
the API returns `402 Payment Required` on these tiers.

```bash
export RAMEN_API_KEY=ramen_ak_...
export OPENAI_API_KEY=sk-...
```

```python
handler = RamenSafetyCallbackHandler(
    api_key=os.environ["RAMEN_API_KEY"],
    bundle_ids=["ramen__shield_core_it"],
    provider_key=os.environ["OPENAI_API_KEY"],
    provider_name="openai",
)
```

Enterprise tiers use platform-managed keys — omit both `provider_key` and
`provider_name`.

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
| `provider_name` | `str` | with BYOK | Provider identifier (for example, `openai` or `anthropic`) forwarded as `X-Provider`. |
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
