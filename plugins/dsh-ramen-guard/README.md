# dsh-ramen-guard

English | [中文](README.zh.md)

> [!IMPORTANT]
> **Unofficial community integration.** This project is independently developed
> and maintained by the ramen-ai community. It is not reviewed, endorsed, or
> supported by DeepSeek. Evaluate third-party plugins before using them. See the
> [DeepSeek Harness plugin category guidelines](https://github.com/deepseek-ai/deepseek-harness/discussions/2004).

<p align="center">
  <img src="../../assets/ramen-logo.png" alt="ramen-ai" width="100"/>
</p>

<p align="center"><strong>Secure DeepSeek Harness at the moment intent becomes action.</strong></p>

`dsh-ramen-guard` is a fail-closed
[Cordis](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/cordis-primer.md)
plugin that evaluates DeepSeek Harness tool calls against the ramen-ai semantic
firewall before execution. It intercepts the official `tools/pre-execute`
waterfall, submits the resolved tool name and arguments through
`@ramen-ai/node-core`, and permits execution only after an allowed verdict with
a locally verified Ed25519 receipt.

DeepSeek Harness can give autonomous agents real shell, code, data, and API
capabilities. This plugin adds an independent semantic policy gate outside the
model's own reasoning. In the default enforcement mode, policy-violating calls
are stopped before side effects, while an approved call continues through the
remaining Cordis guard chain only with a locally verified receipt bound to the
evaluated tool intent. Audit mode is explicitly non-blocking.

Requires **Node.js 24 or newer** and is tested against DeepSeek Harness
`@deepseek-ai/cordis@4.0.1` and `@deepseek-ai/dsh-tools@0.1.1-rc.2`.

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
  <img src="https://img.shields.io/badge/DeepSeek%20Harness-4D6BFE?style=flat&logo=deepseek&logoColor=white" alt="DeepSeek Harness"/>
</p>

---

## Why it matters

A capable agent can turn one manipulated instruction into a shell command,
database mutation, cloud change, or payment request. Once the tool runs, a log
entry is too late. `dsh-ramen-guard` moves the decision to the last responsible
moment: after DeepSeek Harness resolves the tool call, but before the tool body
can create side effects.

- **Block before execution.** Enforce policy on the resolved `{ tool,
  arguments }` intent rather than trying to repair damage afterward.
- **Apply semantic policy, not just string matching.** Configured ramen-ai
  policies can identify encoded payloads, euphemisms, or indirect wording when
  those risks are covered by the selected policy or bundle scope.
- **Fail closed when the boundary is unavailable.** In enforcement mode, a
  timeout, malformed response, cancellation, or unverifiable receipt cannot
  silently authorize the action.
- **Require cryptographic evidence for execution.** An allow response cannot
  reach the tool unless it includes an Ed25519 receipt verified locally against
  the evaluated intent; boundary failures deny with the fixed unavailable
  reason.
- **Preserve defence in depth.** Allowed calls continue with `next()`, so the
  guard complements rather than bypasses downstream Cordis policies.

### Core IT interception

This illustrative terminal view shows `dsh-ramen-guard` denying a log-derived
credential-exfiltration attempt before downstream dispatch.

<p align="center">
  <img src="assets/core-it-interception.png" alt="Illustrative dsh-ramen-guard Core IT interception of a log-derived credential-exfiltration attempt" width="840"/>
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

To use this integration, obtain a ramen-ai API key for a **managed-inference
Enterprise account** at:
**[https://ramenai.dev/pricing](https://ramenai.dev/pricing)**

This release does not expose the provider-key configuration required by the
Free Starter and Professional BYOK tiers. Using a BYOK-only account can produce
`402 Payment Required`, which enforcement mode denies.

Store the ramen-ai key in the environment and resolve it through Cordis
configuration. Never place a real key directly in `cordis.patch.yml` or source
control.

```bash
export RAMEN_API_KEY=ramen_ak_...
```

The plugin does not read environment variables implicitly. The configuration
example below uses the official Cordis `!!js` loader expression to pass the
value into `apiKey` at load time.

---

## Installation

### From npm after release

DeepSeek Harness forwards `dsh plugin` package operations to the selected
profile's package manager:

```bash
dsh plugin --profile web add @ramen-ai/dsh-ramen-guard@0.1.0
```

### From this repository

```bash
cd plugins/dsh-ramen-guard
npm install
npm run build
npm pack

dsh plugin --profile web add /absolute/path/to/ramen-ai-dsh-ramen-guard-0.1.0.tgz
```

Use the profile you actually run instead of `web` where appropriate.

---

## Configuration

Add the plugin to the selected profile's `cordis.patch.yml`, normally under
`${DSH_HOME:-$HOME/.dsh}/profiles/<profile>/cordis.patch.yml`:

```yaml
- insert:
    - id: dsh-ramen-guard
      name: '@ramen-ai/dsh-ramen-guard'
      config:
        apiKey: !!js process.env.RAMEN_API_KEY
        bundleIds: ['ramen__shield_core_it']
        mode: enforce
```

At least one non-empty `bundleIds` or `policyIds` array is required. Both may be
provided. Invalid or incomplete configuration fails plugin activation rather
than starting an unprotected boundary.

### Enforcement mode

`mode: enforce` is the default and the production safety boundary. It denies a
tool call when:

- ramen-ai returns a blocked verdict;
- the evaluation request fails, times out, or is cancelled;
- the response is malformed; or
- the cryptographic receipt is missing or cannot be verified locally.

Infrastructure and receipt failures deterministically return:

```text
ramen ai execution boundary unavailable
```

There is no fail-open configuration.

### Audit mode

Use `mode: audit` only when deliberately observing policy outcomes without
making ramen-ai an enforcement gate:

```yaml
- insert:
    - id: dsh-ramen-guard-audit
      name: '@ramen-ai/dsh-ramen-guard'
      config:
        apiKey: !!js process.env.RAMEN_API_KEY
        policyIds: ['<POLICY_UUID>']
        mode: audit
```

Audit mode logs allowed, denied, unavailable, and unverified outcomes, then
delegates to the remaining Cordis tool policy chain. Other Harness guards may
still deny the call.

### BYOK account compatibility

The current plugin config exposes the ramen-ai `apiKey` but does not expose a
provider key. Accounts whose ramen-ai tier requires a BYOK provider key may
receive `402 Payment Required`; enforcement mode treats that response as a
denial. Use a managed-inference Enterprise account for this release. Do not put
provider credentials into tool arguments or source-controlled configuration.

---

## Quickstart

1. Export `RAMEN_API_KEY`.
2. Install the package into the DeepSeek Harness profile.
3. Add the `dsh-ramen-guard` insert shown above.
4. Restart the profile and inspect the composed configuration if needed:

```bash
dsh --profile web --dump-config
dsh web
```

After activation, every tool call that reaches the official
`tools/pre-execute` waterfall is evaluated before the tool body runs.

---

## Example use cases

### Secure coding and operations agents

Place a policy boundary in front of shell, filesystem, database, Kubernetes,
cloud, or deployment tools. For example, deny destructive commands, unsafe
production changes, or privilege escalation before the underlying tool runs.

### Prevent secret and data exfiltration

Evaluate the destination and payload already resolved into a tool call. Policies
can deny attempts to send API keys, credentials, source code, customer records,
or other sensitive data to an unapproved endpoint.

### Guard financial and administrative workflows

Require an allowed ramen-ai verdict before transfer, payment, account-management,
or access-control tools execute. This is useful when an agent can take actions
with real monetary or permission consequences.

### Add verifiable controls to high-risk workflows

Apply a standard ramen-ai bundle or explicit policy IDs to each privileged tool
call. An allow response can reach the tool only when its receipt verifies
locally against the evaluated tool intent.

### Roll out policy without blocking on day one

Start with `mode: audit` to observe verdicts and tune policies while every call
continues through the Cordis chain. Switch explicitly to `mode: enforce` when
you are ready for a fail-closed boundary. Audit mode itself never blocks.

> [!NOTE]
> The plugin evaluates the resolved tool name and arguments for calls that reach
> `tools/pre-execute`. It does not scan source documents or prompts directly,
> and it cannot govern actions performed outside the Harness tool pipeline.

---

## How it works

```text
DeepSeek model proposes a tool call
                |
                v
      tools/pre-execute waterfall
                |
                v
 JSON { tool, arguments } intent payload
                |
                v
 @ramen-ai/node-core evaluateCompliance()
                |
                v
 ramen-ai verdict + local Ed25519 verification
        |                         |
 verified allow             block / unavailable /
        |                    missing receipt
        v                         |
     next()                       v
 remaining Cordis policy      { kind: 'deny', reason }
        |
        v
 tool body may execute
```

The listener delegates verified allowed calls with `next()`, preserving every
downstream Harness policy. A verified blocked verdict returns the evaluator's
steering rationale. Evaluation and receipt failures never reach the tool body
in enforcement mode.

---

## API reference

### Cordis exports

| Export | Description |
|---|---|
| `name` | Stable plugin display name: `dsh-ramen-guard`. |
| `inject` | Requires the Harness `tools` service. |
| `Config` | Schemastery validator consumed by the Cordis loader. |
| `apply(ctx, config)` | Registers the `tools/pre-execute` listener and creates the `RamenClient`. |
| `BOUNDARY_UNAVAILABLE_REASON` | Stable enforcement denial reason for unavailable or unverifiable evaluations. |

### Configuration

| Field | Required | Default | Description |
|---|---|---|---|
| `apiKey` | yes | — | ramen-ai API key. Resolve from `RAMEN_API_KEY` with `!!js`. |
| `bundleIds` | one of | `[]` | Bundle slugs evaluated for every tool call. |
| `policyIds` | one of | `[]` | Explicit policy UUIDs; may be combined with bundles. |
| `mode` | no | `enforce` | `enforce` or explicit non-blocking `audit`. |
| `baseUrl` | no | SDK default | ramen-ai API base URL override. |

The intent sent to the SDK is:

```json
{
  "tool": "shell",
  "arguments": { "command": "rm -rf /" }
}
```

The SDK also receives `context.tool_name` for policy/audit context.

---

## Running the tests

```bash
cd plugins/dsh-ramen-guard
npm install
npm run typecheck
npm test
npm run build
```

The isolated Vitest suite uses a mock Cordis context and mocked
`RamenClient`. It makes no network calls and needs no credentials. Coverage
includes configuration validation, verified allow/deny decisions, steering,
transport failures, cancellation, missing and invalid receipts, payload shape,
and audit delegation.

---

## Available bundles

| Bundle slug | Coverage |
|---|---|
| `ramen__shield_core_it` | Destructive execution, infrastructure abuse, prompt leakage, jailbreaks, secret exfiltration, and indirect prompt injection. |
| `ramen__eu_ai_act_baseline` | EU AI Act prohibited-practice, data-governance, and transparency controls. |

Pass explicit `policyIds` for custom policies. Bundle and policy details are
available at [ramenai.dev/pricing](https://ramenai.dev/pricing).

---

## Limitations

- DeepSeek Harness is in developer preview and may introduce breaking plugin
  API changes. The tested peer versions are pinned in `package.json`.
- Evaluation adds one network round-trip before each tool execution.
- Audit mode is observability, not an execution boundary.
- The current release does not expose ramen-ai BYOK provider-key configuration.
- This plugin governs calls that reach the Harness tool pipeline; it does not
  govern actions performed outside that pipeline or by unrelated processes.
- This is an unofficial community integration. DeepSeek does not review or
  endorse its policy behavior, security guarantees, or release process.
