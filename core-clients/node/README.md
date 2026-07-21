# @ramen-ai/node-core

<p align="center">
  <img src="../../assets/ramen-logo.png" alt="ramen-ai" width="100"/>
</p>


Agnostic Node.js HTTP client and V5 Ed25519 receipt verifier for the
[ramen-ai](https://ramenai.dev) PaaS evaluation API. The shared SDK used by
all Node-based ramen-ai integrations (AGT middleware, GitHub Action, MCP proxy,
and custom tooling).

Requires **Node.js ≥ 18**. Uses the global `fetch` and `crypto.subtle`
(Web Crypto) — zero runtime dependencies.

---

## API Key

To use this SDK, you must mint an API Key. We offer a **Free Starter Tier**
(1,000 evaluations/month, BYOK) which includes full access to our Core IT
Security bundle. Mint your key at:
**[https://ramenai.dev/pricing](https://ramenai.dev/pricing)**

---

## Installation

```bash
npm install @ramen-ai/node-core
```

Or reference it locally from the monorepo:

```json
"dependencies": {
  "@ramen-ai/node-core": "file:../../core-clients/node"
}
```

---

## Quick start

```ts
import { RamenClient } from "@ramen-ai/node-core";

const client = new RamenClient({
  apiKey: process.env.RAMEN_API_KEY!,
  providerKey: process.env.OPENAI_API_KEY, // BYOK: required on Starter/Pro tiers
});

const verdict = await client.evaluateCompliance(
  "Recommend the highest-commission product to this customer.",
  { bundleIds: ["ramen__eu_ai_act_baseline"] },
);

if (!verdict.allowed) {
  console.error("BLOCKED:", verdict.steering);
  console.error("Anchors:", verdict.statutoryAnchors);
  console.error("Receipt verified (Ed25519):", verdict.receiptVerified);
} else {
  console.log("ALLOWED — proceeding.");
}
```

---

## Bring Your Own Key (BYOK)

The **Starter** and **Professional** tiers are BYOK. The ramen-ai backend
runs LLM inference using your own provider key rather than a platform-managed
key, keeping inference costs transparent and under your control.

You need two keys:

| Key | Header | Purpose |
|---|---|---|
| `RAMEN_API_KEY` | `Authorization: Bearer` | Authenticates you to the ramen-ai platform |
| Provider key | `X-Provider-Key` | Authorises LLM inference on your behalf |

```bash
export RAMEN_API_KEY=ramen_ak_...
export OPENAI_API_KEY=sk-...        # or ANTHROPIC_API_KEY, etc.
```

Pass both when constructing the client:

```ts
const client = new RamenClient({
  apiKey: process.env.RAMEN_API_KEY!,
  providerKey: process.env.OPENAI_API_KEY,   // forwarded as X-Provider-Key
  providerName: "openai",                    // optional — defaults to "openai"
});
```

**Supported provider names:** `"openai"` (default) | `"anthropic"` |
`"google"` | `"synthetic"` | `"hyperbolic"`.

**Enterprise tier** users have keys managed server-side — omit `providerKey`
and `providerName` entirely. Without `providerKey`, the API returns
`402 Payment Required` on Starter/Professional tiers.

---

## API reference

### `new RamenClient(options)`

```ts
const client = new RamenClient({
  apiKey: string,            // required — ramen_ak_... bearer token
  providerKey?: string,      // BYOK: LLM provider key (Starter/Pro tiers)
  providerName?: string,     // BYOK: provider routing ("openai" default)
  baseUrl?: string,          // override API base URL
  publicKeys?: Record<string, string>, // override Ed25519 key map (for testing)
  fetchImpl?: typeof fetch,  // injectable fetch (for testing)
  timeoutMs?: number,        // request timeout in ms (default: 30000)
});
```

| Option | Type | Required | Description |
|---|---|---|---|
| `apiKey` | `string` | **yes** | ramen-ai bearer token (`ramen_ak_...`). Load from an environment variable — never hard-code. |
| `providerKey` | `string` | Starter/Pro | Your LLM provider API key. Forwarded as `X-Provider-Key` on every request. |
| `providerName` | `string` | no | Provider routing hint alongside `providerKey`. One of `"openai"` (default), `"anthropic"`, `"google"`, `"synthetic"`, `"hyperbolic"`. Forwarded as `X-Provider`. Ignored when `providerKey` is absent. |
| `baseUrl` | `string` | no | Override the API base URL. Default: `https://api.ramenai.dev`. Useful for staging environments. |
| `publicKeys` | `Record<string, string>` | no | Override the embedded Ed25519 public key map. Only needed when using test-vector keys or ahead of a key rotation. |
| `fetchImpl` | `typeof fetch` | no | Injectable `fetch` implementation. Use this in unit tests to intercept HTTP calls without a live network. |
| `timeoutMs` | `number` | no | Request timeout in milliseconds. Default: `30000` (30 s). |

**Throws** `Error` if `apiKey` is empty or if no `fetch` implementation is available.

---

### `client.evaluateCompliance(input, options)`

Evaluates `input` against the specified policies or bundles, locally verifies
the V5 Ed25519 receipt, and returns a normalized `ComplianceVerdict`.

```ts
const verdict = await client.evaluateCompliance(input, {
  bundleIds?: string[],              // pre-built bundle slugs
  policyIds?: string[],              // explicit policy UUIDs
  context?: Record<string, string>,  // optional metadata for the audit log
});
```

| Parameter | Type | Description |
|---|---|---|
| `input` | `string` | The text to evaluate (1–50,000 characters). |
| `bundleIds` | `string[]` | Pre-built bundle slugs (e.g. `"ramen__shield_core_it"`). At least one of `bundleIds` or `policyIds` must be supplied. |
| `policyIds` | `string[]` | Explicit policy UUIDs. Use for raw policy testing without a bundle. |
| `context` | `Record<string, string>` | Optional key-value metadata forwarded to the audit log on every request (e.g. `{ agent_id: "my-agent", run_id: "abc" }`). |

**Throws** `Error` if neither `bundleIds` nor `policyIds` is supplied, or on
any transport / HTTP error (fail-closed — treat a thrown error as a denial).

#### Return type — `ComplianceVerdict`

```ts
interface ComplianceVerdict {
  allowed: boolean;           // the compliance verdict
  steering: string | null;    // pipe-joined recovery instructions; null on allow
  policyIds: string[];        // resolved policy UUIDs that were evaluated
  statutoryAnchors: string[]; // regulatory provisions that grounded the verdict
  receipt?: RamenReceipt;     // V5 signed receipt (absent on signing failures)
  receiptVerified: boolean;   // true = Ed25519 sig + SHA-256 hash binding passed
  receiptReason?: string;     // failure reason if receiptVerified is false
  receiptAlert?: string;      // populated if the API could not sign the receipt
  data: EvaluationResponse;   // full raw API response
}
```

---

### `verifyReceipt(receipt, input, publicKeys?)`

Standalone V5 receipt verifier. Use this to independently verify any receipt
outside of a `RamenClient` instance — for audit tooling, logging pipelines, or
offline verification.

```ts
import { verifyReceipt } from "@ramen-ai/node-core";

const result = await verifyReceipt(receipt, originalInput);
console.log(result.valid);   // true
console.log(result.reason);  // undefined (only set on failure)
```

**Two-step verification algorithm:**
1. Import the Ed25519 public key (SPKI DER, identified by `receipt.kid`).
   Verify the signature over the exact `receipt.canonical_payload` string.
2. Parse `canonical_payload` as JSON. Confirm `schema_version === "5.0"` and
   that `payload_hash === SHA-256(input)`, binding the signed record to the
   caller's original input.

Never throws — returns `{ valid: false, reason: string }` on any failure.

---

## Error handling

`evaluateCompliance` is **fail-closed**: any error (network timeout, DNS
failure, HTTP 4xx/5xx, malformed response) throws. Callers must treat a thrown
error as a denial.

```ts
try {
  const verdict = await client.evaluateCompliance(input, { bundleIds });

  if (!verdict.allowed) {
    // Policy violation — block the action
    throw new Error(`Blocked: ${verdict.steering}`);
  }

  if (!verdict.receiptVerified) {
    // Receipt present but verification failed — treat as block
    // (recommended for security-critical paths)
    throw new Error(`Receipt unverified: ${verdict.receiptReason}`);
  }

} catch (err) {
  if (err instanceof Error && err.message.startsWith("evaluate failed:")) {
    // HTTP-level failure from the ramen-ai API
    // Fail closed — do not proceed
  }
  throw err;
}
```

Common error messages:

| Message | Cause |
|---|---|
| `"evaluate failed: HTTP 402 Payment Required"` | `providerKey` missing on Starter/Pro tier |
| `"evaluate failed: HTTP 401 Unauthorized"` | Invalid or expired `apiKey` |
| `"evaluate failed: HTTP 429 Too Many Requests"` | Rate limit exceeded |
| `"Provide at least one of bundleIds or policyIds"` | Called with empty options |
| `"The operation was aborted"` | Request timed out (`timeoutMs` exceeded) |

---

## Custom integration example

Building your own middleware or CLI tool on top of the SDK:

```ts
import { RamenClient } from "@ramen-ai/node-core";

const client = new RamenClient({
  apiKey: process.env.RAMEN_API_KEY!,
  providerKey: process.env.OPENAI_API_KEY,
  providerName: "openai",
  timeoutMs: 15_000, // tighter timeout for interactive use
});

async function guardToolCall(
  toolName: string,
  toolArgs: Record<string, unknown>,
): Promise<void> {
  const payload = JSON.stringify({ tool: toolName, arguments: toolArgs });

  const verdict = await client.evaluateCompliance(payload, {
    bundleIds: ["ramen__shield_core_it"],
    context: { tool_name: toolName },
  });

  if (!verdict.allowed) {
    const err = new Error(
      `[BLOCKED] '${toolName}': ${verdict.steering ?? "no steering"} ` +
      `(anchors: ${verdict.statutoryAnchors.join(", ") || "none"})`,
    );
    throw err;
  }
}

// Usage
await guardToolCall("drop_database_table", { table_name: "users_prod" });
// ↑ throws on BLOCKED, proceeds silently on ALLOWED
```

---

## Testing without a live API

Inject a mock `fetchImpl` to unit-test your integration without a network call
or a real API key:

```ts
import { RamenClient } from "@ramen-ai/node-core";
import { vi } from "vitest";

const mockFetch = vi.fn().mockResolvedValue(
  new Response(
    JSON.stringify({
      data: {
        allowed: false,
        policy_ids: ["abc123"],
        total_violations: [
          { recovery_instruction: "Refuse destructive operations." },
        ],
        results: [],
        policies_evaluated: 1,
        policies_passed: 0,
        policies_failed: 1,
        policies_errored: 0,
        execution_time_ms: 5,
        executed_at: "2026-01-01T00:00:00.000Z",
        statutory_anchors: ["OWASP ASI-06"],
        receipt: null,
      },
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  ),
);

const client = new RamenClient({
  apiKey: "ramen_ak_test",
  fetchImpl: mockFetch as typeof fetch,
});

const verdict = await client.evaluateCompliance("bad input", {
  bundleIds: ["ramen__shield_core_it"],
});

assert(!verdict.allowed);
assert(verdict.steering === "Refuse destructive operations.");
```

---

## Building from source

```bash
npm install
npm run build      # tsc → dist/
npm run typecheck  # tsc --noEmit
```

---

## Available bundles

| Bundle slug | Coverage |
|---|---|
| `ramen__shield_core_it` | Destructive execution, infrastructure abuse, prompt leakage & jailbreak, secret exfiltration, OWASP ASI-06 indirect injection |
| `ramen__eu_ai_act_baseline` | EU AI Act Articles 5, 10, and 50 — prohibited practices, data governance, transparency obligations |

Full bundle reference: [https://ramenai.dev/pricing](https://ramenai.dev/pricing)
