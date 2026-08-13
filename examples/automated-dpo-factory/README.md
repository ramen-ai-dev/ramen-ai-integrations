# ramen ai Foundry Template — Proxy Bias Showcase

A reusable Vite, React, TypeScript, and Cloudflare Worker scaffold for demonstrating governed AI decisions. This first configuration compares synthetic hiring candidates, blocks proxy bias, exposes the healing trail, and derives DPO preference records in browser memory.

The template deliberately separates the reusable engine from replaceable content:

```text
demo/
  demo.config.json       Brand, labels, policy UUIDs, generation budgets
  scenarios.json         Five input-only candidate comparisons and adversarial prompts
src/
  engine/                Reusable React experience and in-memory Dataset Lab
  shared/                Runtime schemas, fixed security limits, prompt builder, strict SSE parser
  worker/                Turnstile, signed sessions, rate limiting, live proxy
```

Changing to another comparison demo should require replacing the two files in `demo/`, not rewriting the React application or Worker.

## Security model

- `RAMEN_API_KEY` and `OPENAI_API_KEY` exist only as Worker secrets.
- Turnstile must succeed with the expected action and hostname before a session is issued.
- The session is an HMAC-SHA256 signed token in a one-hour `HttpOnly; Secure; SameSite=Strict` cookie.
- The cookie contains a random `session_id`; the Cloudflare Rate Limiter binding uses that ID as its key and applies burst protection of five generation requests per 60 seconds. This is not a hard lifetime quota for the one-hour session.
- The browser submits only an allowlisted `scenarioId`. The Worker constructs the prompt from its bundled, validated JSON and fixes policy IDs, retries, temperature, and maximum tokens.
- Live requests are same-origin, body-size limited, timeout bounded, and never reveal upstream credentials.
- DPO records are derived only from live terminal attempt metadata and held only in React memory. Download uses a transient browser Blob; there is no backend persistence.
- The Worker uses `@ramen-ai/node-core` to call the fixed `https://api.ramenai.dev/api/v1/generate/governed` endpoint with `exposeHealingTrail: true`; there is no offline generation path.

`SESSION_SIGNING_SECRET` is an additional required secret because stateless signed cookies need a dedicated HMAC key. Do not reuse an API or Turnstile secret for cookie signing.

## Requirements

- Node.js 24 or newer
- npm 10 or newer
- A Cloudflare account with Workers, Turnstile, and Rate Limiting bindings
- ramen ai and OpenAI API credentials

## Local setup

```bash
cd examples/automated-dpo-factory
npm install
cp .dev.vars.example .dev.vars
```

Edit `.dev.vars` with development credentials and a random signing value of at least 32 characters. On macOS, generate one with:

```bash
openssl rand -base64 48
```

Configure a Turnstile development widget whose action is `foundry-demo`. Set its public site key in `.dev.vars` as `TURNSTILE_SITE_KEY` and its secret as `TURNSTILE_SECRET_KEY`.

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

Review `wrangler.jsonc`, especially the Worker name, public Turnstile site key, and Rate Limiter namespace. Cloudflare's native binding supports 10- or 60-second windows; this template accurately configures burst protection at five requests per 60 seconds.

Create production secrets without placing values in shell history or source files:

```bash
npx wrangler secret put RAMEN_API_KEY
npx wrangler secret put OPENAI_API_KEY
npx wrangler secret put TURNSTILE_SECRET_KEY
npx wrangler secret put SESSION_SIGNING_SECRET
```

Then deploy:

```bash
npm run deploy
```

The Turnstile widget hostname must match the hostname serving the Worker. Cross-origin API calls are rejected.

## Configuration contract

`demo/demo.config.json` controls presentation, prompt framing, policy UUIDs, and hard generation limits. `demo/scenarios.json` contains exactly five sterile scenarios: display metadata, two candidate input profiles, and one adversarial prompt per scenario. It contains no expected outcome, intervention, rejected response, or chosen response.

Both content files are parsed with strict Zod schemas during frontend and Worker startup. Unknown scenario fields, invalid identifiers, UUIDs, generation limits, or any scenario count other than five fail startup rather than silently degrading. The ramen ai API alone determines whether each live generation passes, retries, or blocks. Session lifetime, request size, and displayed 5/60 burst settings are fixed separately in `src/shared/security.ts`; the Wrangler binding remains the enforcement boundary.

## Worker API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/demo/config` | Returns the public Turnstile configuration and burst-limit settings. |
| `GET /api/demo/session` | Restores the expiry of a valid cookie-backed session after reload. |
| `POST /api/demo/session` | Verifies Turnstile and sets the secure one-hour cookie. |
| `DELETE /api/demo/session` | Expires the browser session cookie. |
| `POST /api/demo/generate` | Validates the session and scenario, consumes rate-limit capacity, and streams SDK-governed SSE. |

The Worker creates `RamenClient` with the fixed production base URL and Wrangler-bound secrets, then calls `generateGovernedStream` with `exposeHealingTrail: true`. It re-encodes the SDK's typed status and terminal events for the browser.

## Tests

```bash
npm test
npm run typecheck
npm run build
```

Tests cover token integrity and expiry, SSE framing and terminal enforcement, strict Turnstile session issuance, cookie flags, 60-second burst-limit rejection, scenario allowlisting, and server-side upstream credential attachment.

## License

MIT. Use the scaffold, replace the content, and build on ramen ai.
