# ramen ai Foundry Template — Proxy Bias Showcase

A reusable Vite, React, TypeScript, and Cloudflare Worker scaffold for demonstrating governed AI decisions. This first configuration compares synthetic hiring candidates, blocks proxy bias, exposes the healing trail, and derives DPO preference records in browser memory.

The template deliberately separates the reusable engine from replaceable content:

```text
demo/
  demo.config.json       Brand, labels, policy UUIDs, generation budgets
  scenarios.json         Domain-specific entities, evidence, prompts, fixtures
src/
  engine/                Reusable React experience and in-memory Dataset Lab
  shared/                Runtime schemas, fixed security limits, prompt builder, strict SSE parser
  worker/                Turnstile, signed sessions, rate limiting, live proxy
```

Changing to another comparison demo should require replacing the two files in `demo/`, not rewriting the React application or Worker.

## Security model

- `RAMEN_API_KEY` and `PROVIDER_API_KEY` exist only as Worker secrets.
- Turnstile must succeed with the expected action and hostname before a session is issued.
- The session is an HMAC-SHA256 signed token in a one-hour `HttpOnly; Secure; SameSite=Strict` cookie.
- The cookie contains a random `session_id`; the Cloudflare Rate Limiter binding uses that ID as its key and applies burst protection of five generation requests per 60 seconds. This is not a hard lifetime quota for the one-hour session.
- The browser submits only an allowlisted `scenarioId`. The Worker constructs the prompt from its bundled, validated JSON and fixes policy IDs, retries, temperature, and maximum tokens.
- Live requests are same-origin, body-size limited, timeout bounded, and never reveal upstream credentials.
- DPO records are held only in React memory. Download uses a transient browser Blob; there is no backend persistence.
- Guided Showcase records are explicitly marked `guided_fixture`; live records are marked `live`.

`SESSION_SIGNING_SECRET` is an additional required secret because stateless signed cookies need a dedicated HMAC key. Do not reuse an API or Turnstile secret for cookie signing.

## Requirements

- Node.js 22.12 or newer
- npm 10 or newer
- A Cloudflare account with Workers, Turnstile, and Rate Limiting bindings
- ramen ai and model-provider API credentials for Live Endpoint mode

Guided Showcase mode requires no network credentials after the application is running.

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

Review `wrangler.jsonc`, especially the Worker name, public Turnstile site key, provider name, and Rate Limiter namespace. Cloudflare's native binding supports 10- or 60-second windows; this template accurately configures burst protection at five requests per 60 seconds.

Create production secrets without placing values in shell history or source files:

```bash
npx wrangler secret put RAMEN_API_KEY
npx wrangler secret put PROVIDER_API_KEY
npx wrangler secret put TURNSTILE_SECRET_KEY
npx wrangler secret put SESSION_SIGNING_SECRET
```

Then deploy:

```bash
npm run deploy
```

The Turnstile widget hostname must match the hostname serving the Worker. Cross-origin API calls are rejected.

## Configuration contract

`demo/demo.config.json` controls presentation, prompt framing, policy UUIDs, and hard generation limits. `demo/scenarios.json` supplies two generic comparison entities per scenario. Each attribute is classified as `relevant` or `proxy` for presentation, while the Worker renders the configured profile into the governed prompt.

Both content files are parsed with Zod during frontend and Worker startup. Invalid identifiers, UUIDs, generation limits, entity references, or guided fixtures fail the build/runtime rather than silently degrading. Session lifetime, request size, timeout, and displayed 5/60 burst settings are fixed separately in `src/shared/security.ts`; the Wrangler binding remains the enforcement boundary.

The configured paths are:

- `pass`: first response is approved; no preference pair is produced.
- `heal`: a rejected attempt is steered and followed by an approved response; one or more preference pairs are produced.
- `block`: every attempt is rejected; no chosen response or DPO pair is produced.

## Worker API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/demo/config` | Returns the public Turnstile configuration and burst-limit settings. |
| `GET /api/demo/session` | Restores the expiry of a valid cookie-backed session after reload. |
| `POST /api/demo/session` | Verifies Turnstile and sets the secure one-hour cookie. |
| `DELETE /api/demo/session` | Expires the browser session cookie. |
| `POST /api/demo/generate` | Validates the session and scenario, consumes rate-limit capacity, and proxies governed SSE. |

The live proxy calls `POST https://api.ramenai.dev/api/v1/generate/governed` with `expose_healing_trail: true`. It requires the upstream to return `text/event-stream`.

## Tests

```bash
npm test
npm run typecheck
npm run build
```

Tests cover token integrity and expiry, SSE framing and terminal enforcement, strict Turnstile session issuance, cookie flags, 60-second burst-limit rejection, scenario allowlisting, and server-side upstream credential attachment.

## License

MIT. Use the scaffold, replace the content, and build on ramen ai.
