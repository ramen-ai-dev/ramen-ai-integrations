# ramen-ai Integrations

<p align="center">
  <img src="assets/ramen-logo.svg" alt="ramen-ai" width="120"/>
</p>

Official SDK clients, middleware plugins, and CI/CD tooling for the
[ramen-ai](https://ramenai.dev) PaaS evaluation API — a semantic compliance
firewall for AI agents, enforced at the tool-call layer with cryptographic
receipts.

---

## Getting Started

To use these integrations, you must mint an API key.

We offer a **Free Starter Tier** (1,000 evaluations/month, BYOK) which includes
full access to our Core IT Security bundle. Mint your key at:

### [https://ramenai.dev/pricing](https://ramenai.dev/pricing)

Once you have a key, set it as an environment variable and pick the integration
that fits your stack:

```bash
export RAMEN_API_KEY=ramen_ak_...
```

---

## Bring Your Own Key (BYOK)

The **Free Starter Tier** and **Professional Tier** are BYOK — ramen-ai uses
your own LLM provider key to run the semantic evaluation, rather than a
platform-managed key. This keeps inference costs transparent and under your
control.

To use these tiers, you need two keys:

| Key | Purpose | Where to get it |
|---|---|---|
| `RAMEN_API_KEY` | Authenticates you to the ramen-ai platform | [ramenai.dev/pricing](https://ramenai.dev/pricing) |
| `OPENAI_API_KEY` (or Anthropic equivalent) | Passed as `X-Provider-Key` so the backend can run LLM inference on your behalf | Your provider's developer portal |

Set both in your environment:

```bash
export RAMEN_API_KEY=ramen_ak_...
export OPENAI_API_KEY=sk-...        # or ANTHROPIC_API_KEY, etc.
```

And pass `providerKey` when constructing any client:

```ts
const client = new RamenClient({
  apiKey: process.env.RAMEN_API_KEY!,
  providerKey: process.env.OPENAI_API_KEY, // forwarded as X-Provider-Key
});
```

**Enterprise tier** users have keys managed server-side — omit `providerKey`
entirely. Without it, the backend will return `402 Payment Required` on
Starter/Professional tiers.

---

## Integrations

### Core Clients

Portable, dependency-free HTTP clients with V5 Ed25519 receipt verification
built in. Use these as the foundation for custom integrations or as a direct
API client in your own tooling.

| Package | Language | Path | Description |
|---|---|---|---|
| `@ramen-ai/node-core` | TypeScript / Node.js ≥18 | [`core-clients/node/`](core-clients/node/) | Agnostic HTTP client with Web Crypto Ed25519 receipt verification. The shared SDK used by all Node-based plugins. |
| `ramen-ai` | Python ≥3.11 | [`core-clients/python/`](core-clients/python/) | Agnostic HTTP client with `cryptography` Ed25519 receipt verification. |

---

### Plugins

Drop-in middleware and CI/CD tooling that embed the compliance firewall into
your existing infrastructure with minimal configuration.

| Plugin | Platform | Path | Description |
|---|---|---|---|
| `agt-typescript` | Microsoft Agent Governance Toolkit | [`plugins/agt-typescript/`](plugins/agt-typescript/) | TypeScript middleware that wires ramen-ai in as an AGT `ExternalPolicyBackend`. Intercepts agent tool calls pre-execution, verifies receipts, and logs to the AGT audit chain. |
| `github-action` | GitHub Actions | [`plugins/github-action/`](plugins/github-action/) | CI/CD action that scans pull request diffs for system-prompt and policy instruction changes and fails the build on a `[BLOCKED]` verdict — posting a cryptographically-receipted comment on the PR. |
| `langchain-python` | LangChain (Python) | [`plugins/langchain-python/`](plugins/langchain-python/) | Python `BaseCallbackHandler` that intercepts LangChain agent tool calls pre-execution and halts the chain on a `[BLOCKED]` verdict. |
| `pydantic-ai` | PydanticAI (Python) | [`plugins/pydantic-ai/`](plugins/pydantic-ai/) | PydanticAI `args_validator` factory that intercepts tool calls after schema validation and halts the agent run on a `[BLOCKED]` verdict. |
| `mcp-proxy` | MCP stdio (universal) | [`plugins/mcp-proxy/`](plugins/mcp-proxy/) | Universal MCP stdio proxy that intercepts `tools/call` JSON-RPC messages at the transport layer and blocks malicious payloads before they reach any downstream MCP server. Works with Claude Desktop and any stdio MCP client. |

---

## How it works

Every evaluation returns a **V5 Ed25519 cryptographic receipt** — a signed,
self-describing record that binds the verdict to a SHA-256 hash of your input.
Receipts are verified locally by each client against the published public key,
so no trust in the API server is required to confirm a verdict is authentic.

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

## Repository structure

```
/
├── core-clients/
│   ├── node/            # @ramen-ai/node-core  — TypeScript SDK
│   └── python/          # ramen-ai             — Python SDK
├── plugins/
│   ├── agt-typescript/  # Microsoft AGT middleware
│   ├── github-action/   # GitHub Actions CI/CD interceptor
│   ├── langchain-python/ # LangChain Python callback handler
│   ├── pydantic-ai/     # PydanticAI args_validator middleware
│   └── mcp-proxy/       # Universal MCP stdio transport interceptor
├── .github/
│   └── workflows/       # Self-testing CI workflow
└── AGENTS.md            # Engineering protocol (local only — git-ignored)
```

---

## Bundles

The Free Starter Tier includes the **Core IT Security** bundle
(`ramen__shield_core_it`). Additional regulatory bundles are available on paid
tiers:

| Bundle slug | Coverage |
|---|---|
| `ramen__shield_core_it` | Destructive execution, infrastructure abuse, prompt leakage & jailbreak, secret exfiltration, OWASP ASI-06 indirect injection |
| `ramen__eu_ai_act_baseline` | EU AI Act Articles 5, 10, and 50 — prohibited practices, data governance, transparency obligations |

Full bundle and policy reference: [https://ramenai.dev/pricing](https://ramenai.dev/pricing)
