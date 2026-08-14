# ramen ai Foundry Template — Proxy Bias Showcase

A reusable Vite, React, TypeScript, and Cloudflare Worker scaffold for demonstrating governed AI decisions. This first configuration compares synthetic hiring candidates, blocks proxy bias, exposes the healing trail, and derives DPO preference records in browser memory.

The template deliberately separates the reusable engine from replaceable content:

```text
demo/
  demo.config.json       Brand, labels, policy UUIDs, generation budgets
  scenarios.json         Five input-only candidate comparisons and adversarial prompts
src/
  engine/                Reusable React experience and in-memory Dataset Lab
  shared/                Runtime schemas, request limits, prompt builder, strict SSE parser
  worker/                Stateless live governed-generation proxy
```

Changing to another comparison demo should require replacing the two files in `demo/`, not rewriting the React application or Worker.

## Security model

- `RAMEN_API_KEY` and `OPENAI_API_KEY` exist only as Worker secrets and are never sent to the browser.
- The browser submits only an allowlisted `scenarioId`. The Worker constructs the prompt from its bundled, validated JSON and fixes policy IDs, retries, temperature, and maximum tokens.
- Live requests are same-origin and body-size limited. The Worker does not create sessions, parse cookies, or persist application state.
- DPO records are derived only from live terminal attempt metadata and held only in React memory. Download uses a transient browser Blob; there is no backend persistence.
- The Worker uses `@ramen-ai/node-core` to call the fixed `https://api.ramenai.dev/api/v1/generate/governed` endpoint with `exposeHealingTrail: true`; there is no offline generation path.
- The ramen ai backend automatically rate-limits requests according to the tier of the supplied `RAMEN_API_KEY`. Because that enforcement already occurs at the governed API boundary, this public template does not add frontend bot challenges, browser sessions, cookies, or a second Cloudflare rate limiter.

This intentionally keeps onboarding stateless: React calls the same-origin Worker, the Worker injects server-side credentials, and governed SSE streams back to React.

## Requirements

- Node.js 24 or newer
- npm 10 or newer
- A Cloudflare account with Workers
- ramen ai and OpenAI API credentials

## Local setup

```bash
cd examples/automated-dpo-factory
npm install
cp .dev.vars.example .dev.vars
```

Edit `.dev.vars` with the two development credentials:

```dotenv
RAMEN_API_KEY=replace-with-a-ramen-api-key
OPENAI_API_KEY=replace-with-an-openai-api-key
```

Validate everything:

```bash
npm run check
```

Start the local Worker and static application:

```bash
npm run dev
```

Open the URL printed by Wrangler. `npm run dev` performs a production build first, then starts Wrangler; stop it with `Ctrl-C`.

## Cloudflare deployment

Review `wrangler.jsonc`, especially the Worker name. The template needs only the static-assets binding declared there; ramen ai applies API-key-tier rate limits at its backend.

Create production secrets without placing values in source files:

```bash
npx wrangler secret put RAMEN_API_KEY
npx wrangler secret put OPENAI_API_KEY
```

Then deploy:

```bash
npm run deploy
```

Cross-origin API calls are rejected. No Turnstile widget, session-signing secret, cookie configuration, or Cloudflare Rate Limiter binding is required.

## Configuration contract

`demo/demo.config.json` controls presentation, prompt framing, policy UUIDs, and hard generation limits. `demo/scenarios.json` contains exactly five sterile scenarios: display metadata, two candidate input profiles, and one adversarial prompt per scenario. It contains no expected outcome, intervention, rejected response, or chosen response.

Both content files are parsed with strict Zod schemas during frontend and Worker startup. Unknown scenario fields, invalid identifiers, UUIDs, generation limits, or any scenario count other than five fail startup rather than silently degrading. The ramen ai API alone determines whether each live generation passes, retries, or blocks. The request body limit remains fixed in `src/shared/security.ts`.

## Worker API

| Endpoint | Purpose |
| --- | --- |
| `POST /api/demo/generate` | Validates the same-origin scenario request and streams SDK-governed SSE. |

The Worker creates `RamenClient` with the fixed production base URL and Wrangler-bound secrets, then calls `generateGovernedStream` with `exposeHealingTrail: true`. It re-encodes the SDK's typed status and terminal events for the browser. The proxy is stateless: it does not issue or consume application cookies.

## Tests

```bash
npm test
npm run typecheck
npm run build
```

Tests cover SSE framing and terminal enforcement, same-origin request enforcement, scenario allowlisting, direct stateless generation, fixed governed-generation options, and server-side upstream credential attachment.

## License

MIT. Use the scaffold, replace the content, and build on ramen ai.
