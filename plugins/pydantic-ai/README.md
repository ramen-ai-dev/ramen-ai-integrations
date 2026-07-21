# ramen-ai PydanticAI Integration

<p align="center">
  <img src="../../assets/ramen-logo.png" alt="ramen-ai" width="100"/>
</p>


An L2 Semantic Firewall middleware for [PydanticAI](https://ai.pydantic.dev/).
Intercepts agent tool calls pre-execution via PydanticAI's native
`args_validator` hook, evaluates the tool name and resolved arguments against
the ramen-ai PaaS evaluation API, and halts the agent run by raising
`RamenSafetyException` on a `[BLOCKED]` verdict. Every evaluation is backed by
a locally-verified V5 Ed25519 cryptographic receipt.

Requires Python ≥ 3.10 and `pydantic-ai ≥ 0.0.14`.

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
pip install -e plugins/pydantic-ai
```

---

## Quickstart

```python
import asyncio
import os
from pydantic_ai import Agent, RunContext
from ramen_pydantic import ramen_firewall, RamenSafetyException

# Build a shared firewall validator.
firewall = ramen_firewall(
    api_key=os.environ["RAMEN_API_KEY"],
    bundle_ids=["ramen__shield_core_it"],
    # BYOK: required on Starter/Professional tiers. Omit on Enterprise.
    provider_key=os.environ.get("OPENAI_API_KEY"),
)

agent = Agent("openai:gpt-4o-mini")

# Attach the firewall to any tool via args_validator.
@agent.tool(args_validator=firewall)
def fetch_compliance_guidelines(ctx: RunContext[None], query: str) -> str:
    """Retrieve compliance guidelines for AI systems."""
    return f"Guidelines for: {query}"

async def main():
    try:
        result = await agent.run("What are the EU AI Act requirements?")
        print(result.output)
    except RamenSafetyException as exc:
        print(f"Blocked: {exc.steering}")
        print(f"Anchors: {exc.statutory_anchors}")

asyncio.run(main())
```

### BYOK (Bring Your Own Key)

The Starter and Professional tiers require your own LLM provider key (OpenAI,
Anthropic, etc.). Pass it as `provider_key` — forwarded as the
`X-Provider-Key` header on every evaluation request. Without it the API returns
`402 Payment Required` on these tiers.

```bash
export RAMEN_API_KEY=ramen_ak_...
export OPENAI_API_KEY=sk-...
```

Enterprise tiers use platform-managed keys — omit `provider_key` entirely.

---

## How it works

### Why `args_validator` and not `prepare`

PydanticAI exposes two tool-level hooks:

- **`prepare`** fires before each agent step to decide whether to *offer* a
  tool to the model. It receives `(ctx, tool_def)` — no call arguments. It
  cannot inspect what the model actually wants to do with the tool.
- **`args_validator`** fires after the LLM has chosen a tool and PydanticAI
  has schema-validated the arguments, but *before* the tool function is called.
  It receives `(ctx, **args_dict)` with the real typed arguments.

`args_validator` is the correct interception point for a security firewall.

```
PydanticAI Agent
  │
  ├── LLM chooses a tool and produces arguments
  ├── PydanticAI schema-validates the arguments
  │
  ▼
args_validator(ctx, **args_dict)              ← ramen_firewall() hook
  │
  ├── Build payload: {tool_name, args_dict}
  ├── POST /api/v1/paas/evaluate  →  ramen-ai firewall
  ├── Verify V5 Ed25519 receipt locally
  │
  ├── ALLOWED  →  return None (tool._run() proceeds)
  └── BLOCKED  →  raise RamenSafetyException (tool._run() never called)
```

**Fail-closed:** any exception during the evaluation request (network error,
timeout, `5xx`) is caught and re-raised as `RamenSafetyException` with the
original as `__cause__`. An unreachable firewall never silently allows a call.

---

## API

### `ramen_firewall(**kwargs)`

Factory function. Returns an `args_validator` callable compatible with
PydanticAI's `ArgsValidatorFunc` type alias.

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

Raised on a BLOCKED verdict. Inherits from `RuntimeError` — propagates
directly out of `agent.run()` without wrapping.

| Attribute | Type | Description |
|---|---|---|
| `tool_name` | `str` | The name of the blocked tool. |
| `steering` | `str \| None` | Deterministic recovery instruction for the host agent. |
| `receipt_verified` | `bool` | Whether the V5 Ed25519 receipt was locally verified. |
| `statutory_anchors` | `list[str]` | Regulatory provisions that grounded the block. |

---

## Running the example

```bash
cd plugins/pydantic-ai
pip install -e ".[dev]"
export RAMEN_API_KEY=ramen_ak_...
export OPENAI_API_KEY=sk-...
python examples/test_agent.py
```

The default prompt is benign and produces an `ALLOWED` verdict. To see the
firewall block a destructive command, follow the swap instructions in the
example file.

## Running the tests

```bash
cd plugins/pydantic-ai
pip install -e ".[dev]"
pytest -v
```

14 tests covering: ALLOWED/BLOCKED verdicts, fail-closed transport and HTTP
errors, unverifiable receipt escalation, payload and context construction, and
two end-to-end integration tests through a real PydanticAI `TestModel` agent run.

---

## Available bundles

| Bundle slug | Coverage |
|---|---|
| `ramen__shield_core_it` | Destructive execution, prompt injection, secret exfiltration, OWASP ASI-06 |
| `ramen__eu_ai_act_baseline` | EU AI Act Articles 5, 10, and 50 |
