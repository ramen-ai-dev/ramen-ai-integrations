# @ramen-ai/node-core

<p align="center">
  <img src="../../assets/ramen-logo.svg" alt="ramen-ai" width="100"/>
</p>

Agnostic Node.js HTTP client and V5 Ed25519 receipt verifier for the
[ramen-ai](https://ramenai.dev) PaaS evaluation API. The shared SDK used by all
Node-based ramen-ai integrations (AGT middleware, GitHub Action, and custom
tooling).

Requires Node.js ≥ 18. Uses the global `fetch` and `crypto.subtle` (Web Crypto)
— no external dependencies.

---

## API Key

To use this integration, you must mint an API Key. We offer a **Free Starter Tier** (1,000 evaluations/month, BYOK) which includes full access to our Core IT Security bundle. Mint your key at: **[https://ramenai.dev/pricing](https://ramenai.dev/pricing)**

---

## Installation

This package is not yet published to npm. Reference it locally via a `file:`
dependency or install it directly from the monorepo:

```bash
npm install ../../core-clients/node
```

Or in your `package.json`:

```json
"dependencies": {
  "@ramen-ai/node-core": "file:../../core-clients/node"
}
```

---

## Usage

```ts
import { RamenClient } from "@ramen-ai/node-core";

const client = new RamenClient({
  apiKey: process.env.RAMEN_API_KEY!,
  // BYOK: required on Starter/Professional tiers.
  // Omit on Enterprise (platform-managed keys).
  providerKey: process.env.OPENAI_API_KEY,
});

const verdict = await client.evaluateCompliance(
  "Recommend the highest-commission product to this customer.",
  { bundleIds: ["ramen__eu_ai_act_baseline"] },
);

console.log(verdict.allowed);          // false
console.log(verdict.receiptVerified);  // true  (Ed25519 verified locally)
console.log(verdict.steering);         // "Reassess product suitability..."
console.log(verdict.statutoryAnchors); // ["EU AI Act Art. 5(1)(a)"]
```

### BYOK (Bring Your Own Key)

The Starter and Professional tiers require your own LLM provider key (OpenAI,
Anthropic, etc.). Pass it as `providerKey` — it is forwarded as the
`X-Provider-Key` header on every evaluation request. Without it, the API
returns `402 Payment Required` on these tiers.

```bash
export RAMEN_API_KEY=ramen_ak_...
export OPENAI_API_KEY=sk-...
```

Enterprise tiers use platform-managed keys — omit `providerKey` entirely.

---

## API

### `new RamenClient(options)`

| Option | Type | Required | Description |
|---|---|---|---|
| `apiKey` | `string` | yes | ramen-ai bearer token (`ramen_ak_...`). |
| `providerKey` | `string` | Starter/Pro | LLM provider key forwarded as `X-Provider-Key`. |
| `baseUrl` | `string` | no | Override the API base URL (default: `https://api.ramenai.dev`). |
| `publicKeys` | `Record<string, string>` | no | Override the Ed25519 public key map (for test vectors). |
| `fetchImpl` | `typeof fetch` | no | Injectable fetch implementation (for testing). |
| `timeoutMs` | `number` | no | Request timeout in ms (default: `30000`). |

### `client.evaluateCompliance(input, options)`

Evaluates `input` against the specified policies or bundles.

| Option | Type | Description |
|---|---|---|
| `bundleIds` | `string[]` | Pre-built bundle slugs (e.g. `"ramen__shield_core_it"`). |
| `policyIds` | `string[]` | Explicit policy UUIDs. |
| `context` | `Record<string, string>` | Optional metadata forwarded to the audit log. |

Returns a `ComplianceVerdict`:

```ts
{
  allowed: boolean;
  steering: string | null;
  policyIds: string[];
  statutoryAnchors: string[];
  receipt?: RamenReceipt;          // V5 signed receipt
  receiptVerified: boolean;        // true = Ed25519 + hash binding passed
  receiptReason?: string;          // failure reason if not verified
  data: EvaluationResponse;        // full API response
}
```

### `verifyReceipt(receipt, input, publicKeys?)`

Standalone V5 receipt verifier. Verifies the Ed25519 signature over the
`canonical_payload`, then confirms `SHA-256(input) === payload.payload_hash`.
Returns `{ valid: boolean, reason?: string }`.

---

## Building

```bash
npm install
npm run build      # tsc -> dist/
npm run typecheck  # tsc --noEmit
```

## Available bundles

| Bundle slug | Coverage |
|---|---|
| `ramen__shield_core_it` | Destructive execution, prompt injection, secret exfiltration, OWASP ASI-06 |
| `ramen__eu_ai_act_baseline` | EU AI Act Articles 5, 10, and 50 |
