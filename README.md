# ramen-ai Integrations

<p align="center">
  <img src="assets/ramen-logo.png" alt="ramen-ai" width="120"/>
</p>

<p align="center"><strong>The deterministic execution boundary for AI agents.</strong></p>

<p align="center"><sub>Build governed LangGraph workflows with <a href="https://github.com/ramen-ai-dev/ramen-foundry">ramen-foundry</a>.</sub></p>

---

## The Problem

LLMs cannot police their own tools. If your agent is connected to a database,
a prompt injection hidden in a PDF can drop your tables. If it is connected to
a payment API, a Morse-encoded instruction buried in a retrieved document can
drain a wallet. Standard keyword filters catch basic syntax. They fail against
encoded payloads, corporate jargon, and multi-criterion composite attacks.

**We built the deterministic execution boundary to stop it** — a semantic
firewall that evaluates every tool call against your compliance policies
before execution, signs every verdict with an Ed25519 receipt, and returns a
steering instruction that is auditable, reproducible, and legally defensible.

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
  <a href="https://github.com/ramen-ai-dev/mcp-shield-proxy">
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
the zero-day evasion vectors in our official **[Red Team Guide](RED_TEAM_GUIDE.md)**.

Below is a simulation of the Grok/Bankr heist. We fed the raw adversarial
prompt directly into our sandbox. It uses a social engineering wrapper
(claiming a visual impairment) to smuggle a 3,000,000,000 DRB transfer
instruction encoded in Morse code. The firewall evaluated the underlying
semantic intent, intercepted the unauthorized financial transfer, and blocked
it pre-execution, issuing a verified Ed25519 receipt.

<p align="center">
  <img src="assets/grok-bankr.png" alt="ramen-ai intercepting the Grok/Bankr Morse-code heist pre-execution" width="720"/>
</p>

---

## Getting Started

To use these integrations, you must mint an API Key.

We offer a **Free Starter Tier** (1,000 evaluations/month, BYOK) which includes
full access to our Core IT Security bundle. Mint your key at:

### [https://ramenai.dev/pricing](https://ramenai.dev/pricing)

### BYOK — Bring Your Own Key

The Starter and Professional tiers use your own LLM provider key for inference.
You need two keys:

| Key | Purpose | Where to get it |
|---|---|---|
| `RAMEN_API_KEY` | Authenticates you to the ramen-ai platform | [ramenai.dev/pricing](https://ramenai.dev/pricing) |
| `OPENAI_API_KEY` (or Anthropic equivalent) | Forwarded as `X-Provider-Key` for LLM inference | Your provider's developer portal |

```bash
export RAMEN_API_KEY=ramen_ak_...
export OPENAI_API_KEY=sk-...        # or ANTHROPIC_API_KEY, etc.
```

**Enterprise tier** users have keys managed server-side — omit `providerKey`
entirely.

---

## Integrations

### Core SDKs

Use these as the foundation for custom integrations across any framework,
queue, or gateway not covered by the plugins below.

| Package | Language | Path | Description |
|---|---|---|---|
| `@ramen-ai/node-core` | TypeScript / Node.js ≥ 18 | [`core-clients/node/`](core-clients/node/) | Zero-dependency HTTP client using Web Crypto. Covers `RamenClient`, BYOK, standalone `verifyReceipt`, and injectable `fetchImpl` for testing. **[→ Full SDK docs](core-clients/node/README.md)** |
| `ramen-ai-core` | Python ≥ 3.10 | [`core-clients/python/`](core-clients/python/) | Synchronous `httpx` client with `cryptography` Ed25519 verification. Per-call BYOK, standalone `verify_receipt`, and `pytest-httpx` test patterns. **[→ Full SDK docs](core-clients/python/README.md)** |

### Plugins

| Plugin | Platform | Path | Description |
|---|---|---|---|
| `agt-typescript` | Microsoft AGT | [`plugins/agt-typescript/`](plugins/agt-typescript/) | TypeScript middleware wired as an AGT `ExternalPolicyBackend`. Intercepts tool calls pre-execution, verifies receipts, logs to the AGT audit chain. |
| `github-action` | GitHub Actions | [`plugins/github-action/`](plugins/github-action/) | Scans PR diffs for system-prompt modifications, evaluates against compliance policies, fails CI on `[BLOCKED]` — with a cryptographic receipt comment on the PR. |
| `langchain-python` | LangChain (Python) | [`plugins/langchain-python/`](plugins/langchain-python/) | `BaseCallbackHandler` that intercepts LangChain tool calls pre-execution and halts the chain on `[BLOCKED]`. |
| `pydantic-ai` | PydanticAI (Python) | [`plugins/pydantic-ai/`](plugins/pydantic-ai/) | `args_validator` factory that intercepts tool calls after schema validation and halts the agent run on `[BLOCKED]`. |
| `mcp-proxy` | MCP stdio (universal) | [Standalone repository](https://github.com/ramen-ai-dev/mcp-shield-proxy) | Universal stdio proxy intercepting `tools/call` JSON-RPC at the transport layer. Works with Claude Desktop and any stdio MCP client. |
| `cmcp-python` | cMCP + TRACE | [`plugins/cmcp-python/`](plugins/cmcp-python/) | cMCP tool-call policy adapter, plus a TRACE Trust Record exporter that maps V5 Ed25519 receipts onto the agentrust-io EAT profile. |
| `mlflow-python` | MLflow / Databricks | [`plugins/mlflow-python/`](plugins/mlflow-python/) | `mlflow.pyfunc.PythonModel` wrapper enforcing algorithmic governance on classical ML. Evaluates feature arrays and SHAP attributions for proxy bias pre-inference; halts serving on `[BLOCKED]`. |
| `ramen-data-filter` | Pandas / CSV | [`plugins/ramen-data-filter/`](plugins/ramen-data-filter/) | Dual-mode row filtration for RAG ingestion and MLOps datasets. Strictly excludes blocked records or semantically imputes steering-approved columns. |
| `dsh-ramen-guard` | DeepSeek Harness | [Standalone repository](https://github.com/ramen-ai-dev/dsh-ramen-guard) | Unofficial Cordis guard that, in enforcement mode, blocks policy-violating tool intent before execution and requires a locally verified Ed25519 receipt for allowed calls. |

---

## How it works

Every evaluation returns a **V5 Ed25519 cryptographic receipt** — a signed,
self-describing record binding the verdict to a SHA-256 hash of your input.
Receipts are verified locally against the published public key: no trust in
the API server is required.

```
Your agent  →  ramen-ai middleware  →  POST /api/v1/paas/evaluate
                                              ↓
                                     Verdict + Ed25519 receipt
                                              ↓
                             Local receipt verification (Web Crypto)
                                              ↓
                              ALLOWED → tool executes
                              BLOCKED → thrown / build failed / PR comment
```

---

## Bundles

Use `bundle_ids` for **macro-level Defence-in-Depth aggregation** — a single
slug activates multiple coordinated policies across a threat domain. For
**surgical, single-domain statutory auditing**, pass specific `policy_ids`
directly to route to exactly one policy without other classifiers interfering.

The Free Starter Tier includes the **Core IT Security** bundle:

| Bundle slug | Coverage |
|---|---|
| `ramen__shield_core_it` | Destructive execution, infrastructure abuse, prompt leakage & jailbreak, secret exfiltration, OWASP ASI-06 indirect injection |
| `ramen__eu_ai_act_baseline` | EU AI Act Articles 5, 10, and 50 — prohibited practices, data governance, transparency obligations |

Full bundle and policy reference: [https://ramenai.dev/pricing](https://ramenai.dev/pricing)

---

## Repository structure

```
/
├── assets/                  # Shared brand and visual assets
├── core-clients/
│   ├── node/                # @ramen-ai/node-core  — TypeScript SDK
│   └── python/              # ramen-ai-core        — Python SDK
├── plugins/
│   ├── agt-typescript/      # Microsoft AGT middleware
│   ├── github-action/       # GitHub Actions CI/CD interceptor
│   ├── langchain-python/    # LangChain Python callback handler
│   ├── pydantic-ai/         # PydanticAI args_validator middleware
│   ├── mcp-proxy/           # Universal MCP stdio transport interceptor
│   ├── cmcp-python/         # cMCP policy adapter + TRACE record exporter
│   ├── mlflow-python/       # MLflow pyfunc algorithmic governance wrapper
│   ├── ramen-data-filter/   # Pandas/CSV filtration for RAG and MLOps datasets
├── .github/
│   └── workflows/           # CI workflows
└── RED_TEAM_GUIDE.md        # Zero-day evasion vectors and challenge guide
```

---

## Adding integration logos

When adding a platform integration, update the standard ecosystem row in the
home README, every plugin README, and every translated companion. See
**[Adding Integration Logos](docs/adding-integration-logos.md)** for branding,
internal-link, self-badge, asset, disclosure, and validation requirements.
