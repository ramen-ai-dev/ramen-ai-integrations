# ramen-ai PR Compliance Interceptor

A GitHub Action that scans pull request diffs for system-prompt and
markdown/policy instruction changes, evaluates the added text against the
[ramen-ai PaaS evaluation API](../../core-clients/node), and **fails the CI
build** on a `[BLOCKED]` verdict. On a block it posts a single pull request
comment carrying the verdict, the statutory anchor(s), the steering
instruction, and the Ed25519 cryptographic receipt signature.

Receipt verification is performed locally by the
[`@ramen-ai/node-core`](../../core-clients/node) client, against the V5
Evaluation API contract — no trust in the API server is required to confirm a
verdict.

---

## API Key

To use this integration, you must mint an API Key. We offer a **Free Starter Tier** (1,000 evaluations/month, BYOK) which includes full access to our Core IT Security bundle. Mint your key at: **[https://ramenai.dev/pricing](https://ramenai.dev/pricing)**

---

## Usage

> **Required:** The job must declare `permissions` at **job level** and pass
> `github_token` explicitly. A workflow-level `permissions` block is not
> sufficient on organisations with restrictive default token settings — job-level
> always wins. Omitting `github_token` from `with:` causes a
> `Resource not accessible by integration` (403) crash when the action tries to
> list PR files.

Add a workflow such as `.github/workflows/ramen-compliance.yml`:

```yaml
name: ramen-ai Compliance

on:
  pull_request:

jobs:
  compliance:
    runs-on: ubuntu-latest
    permissions:
      contents: read        # required: list changed files in the PR
      pull-requests: write  # required: list PR files + post verdict comment
    steps:
      - uses: actions/checkout@v4

      - name: ramen-ai PR Compliance Interceptor
        uses: ramen-ai-dev/ramen-ai-integrations/plugins/github-action@master
        with:
          ramen_api_key: ${{ secrets.RAMEN_API_KEY }}
          bundle_ids: ramen__eu_ai_act_baseline,ramen__shield_core_it
          github_token: ${{ secrets.GITHUB_TOKEN }}
```

The `permissions` block **must be at job level** (inside `jobs.<job-id>:`, not
at the top of the file). A partial `permissions:` block at any level silently
drops every scope not listed, so both `contents` and `pull-requests` must appear
together. `github_token` must be passed explicitly in `with:` — the action
cannot rely on the `action.yml` default resolving at runtime.

### Raw policy testing (no bundle)

Leave `bundle_ids` empty and pass explicit `policy_ids` instead:

```yaml
        with:
          ramen_api_key: ${{ secrets.RAMEN_API_KEY }}
          bundle_ids: ""
          policy_ids: 1006492f-db62-4f46-8775-48b966c5c956
```

At least one of `bundle_ids` or `policy_ids` must resolve to a value; otherwise
the evaluation cannot run and the Action fails with a configuration error.

---

## Bring Your Own Key (BYOK)

The Starter and Professional tiers require you to supply your own LLM provider
key. The Action forwards it to the ramen-ai API as the `X-Provider-Key` header.
Without it, evaluations on these tiers return `402 Payment Required`.

### 1. Add the provider key to GitHub Secrets

In your repository go to **Settings → Secrets and variables → Actions → New
repository secret** and add:

| Secret name | Value |
|---|---|
| `RAMEN_API_KEY` | Your `ramen_ak_...` key from [ramenai.dev/pricing](https://ramenai.dev/pricing) |
| `OPENAI_API_KEY` | Your OpenAI (or Anthropic) API key from your provider portal |

### 2. Map it to the `provider_key` input in your workflow

```yaml
name: ramen-ai Compliance

on:
  pull_request:

jobs:
  compliance:
    runs-on: ubuntu-latest
    permissions:
      contents: read        # required: list changed files in the PR
      pull-requests: write  # required: list PR files + post verdict comment
    steps:
      - uses: actions/checkout@v4

      - name: ramen-ai PR Compliance Interceptor
        uses: ramen-ai-dev/ramen-ai-integrations/plugins/github-action@master
        with:
          ramen_api_key: ${{ secrets.RAMEN_API_KEY }}
          bundle_ids: "ramen__shield_core_it"
          github_token: ${{ secrets.GITHUB_TOKEN }}
          provider_key: ${{ secrets.OPENAI_API_KEY }}
```

**Enterprise tier:** omit `provider_key` entirely — managed keys are
provisioned server-side and the header is not required.

---

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `ramen_api_key` | **yes** | — | ramen-ai PaaS API key. Always provide via a repository/organization **secret**, never inline. |
| `provider_key` | Starter/Pro | `""` | BYOK — your LLM provider API key (e.g. OpenAI `sk-...` or Anthropic key). Required on Starter and Professional tiers; forwarded as `X-Provider-Key`. Omit on Enterprise. Use `${{ secrets.OPENAI_API_KEY }}`. |
| `bundle_ids` | no | `""` | Comma-separated bundle slugs to evaluate against (e.g. `ramen__eu_ai_act_baseline`). The server resolves them to policy IDs. |
| `policy_ids` | no | `""` | Comma-separated policy UUIDs for raw policy testing when no bundle is supplied. |
| `github_token` | **yes** | — | Token used to list PR files and post the verdict comment. Pass `${{ secrets.GITHUB_TOKEN }}` explicitly — do not rely on the default. The job must also declare `permissions: contents: read` and `pull-requests: write` at **job level** or the token will lack the required scopes and the action will crash with a 403. |
| `base_url` | no | `""` | Override the ramen-ai API base URL (defaults to the production endpoint). |
| `file_extensions` | no | `.md,.txt,.py` | Comma-separated file extensions whose added text is scanned. |
| `fail_on_unverified_receipt` | no | `"true"` | When `true`, a verdict whose Ed25519 receipt cannot be verified is treated as a build failure (fail-closed on evidence). |

## Outputs

| Output | Description |
|---|---|
| `blocked` | `"true"` if any scanned change was blocked (or failed closed), else `"false"`. |
| `blocked_count` | Number of files that received a `[BLOCKED]` verdict. |

---

## How it works

1. Reads the pull request's changed files via the GitHub REST API.
2. Keeps only files whose extension matches `file_extensions`, and extracts the
   **added** lines from each file's diff hunks.
3. Sends each file's added text to the ramen-ai evaluation API through the Node
   core client, which verifies the returned V5 Ed25519 receipt locally.
4. On a `[BLOCKED]` verdict (or, when `fail_on_unverified_receipt` is set, an
   evaluation that could not complete), calls `@actions/core.setFailed()` to
   break the build.
5. Posts one aggregated PR comment summarising every blocked file with its
   statutory anchor(s), steering instruction, and receipt signature.

The Action is **fail-closed**: an evaluation or transport error is surfaced as a
blocking failure rather than a silent pass. Inputs are also subject to the
contract's limits — the evaluation API accepts 1–50,000 characters per request,
so a single file whose added text exceeds 50,000 characters is rejected by the
API and treated as a blocking failure.

---

## GitHub Platform Constraints & Troubleshooting

GitHub's token security model imposes hard limits that can override your
workflow YAML configuration. Both constraints below produce the same
`403 Resource not accessible by integration` error, but they have different
fixes.

### 1. Repository-level token permissions

By default, GitHub may issue workflow tokens with **read-only** access at the
repository level, regardless of what `permissions:` you declare in your YAML.
This setting is controlled outside the workflow file entirely.

**Symptom:** The action crashes with `Resource not accessible by integration`
even though your job block contains:

```yaml
permissions:
  contents: read
  pull-requests: write
```

**Fix:** Navigate to your repository's
**Settings → Actions → General → Workflow permissions** and select
**"Read and write permissions"**. This sets the repository-level default that
GitHub applies when issuing the `GITHUB_TOKEN` for workflow runs.

---

### 2. Fork security limits (`pull_request` event)

For security reasons, GitHub **automatically downgrades the `GITHUB_TOKEN` to
read-only** for `pull_request` events that originate from a forked repository,
regardless of your `permissions:` block. This is a hard platform limit — it
cannot be overridden by workflow configuration alone.

This action requires write access to post the cryptographic receipt comment on
the pull request. Automated PR commenting is therefore **only supported** on:

- **Internal branches** within the same repository, or
- Workflows using the `pull_request_target` event (runs in the base repo
  context, preserving write access and secret access even for fork PRs)

**Fix for fork PRs:** Switch the trigger from `pull_request` to
`pull_request_target`:

```yaml
on:
  pull_request_target:        # ← replaces pull_request
    types: [opened, synchronize, reopened]

jobs:
  evaluate-ai-prompts:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2

      - name: Evaluate PR with Ramen AI
        uses: ramen-ai-dev/ramen-ai-integrations/plugins/github-action@master
        with:
          ramen_api_key: ${{ secrets.RAMEN_API_KEY }}
          bundle_ids: "ramen__shield_core_it"
          github_token: ${{ secrets.GITHUB_TOKEN }}
```

> **Security note:** `pull_request_target` runs with base-repo write access and
> exposes secrets even on fork PRs. This is safe for this action because it
> reads the PR diff as text via the API — it does not check out or execute any
> code from the fork. Never add steps that install or run fork-provided code in
> the same job.

---

## Data Privacy & Security

This Action transmits pull request content to an external evaluation API. The
points below describe exactly what is sent and what is durably recorded, so it
can be reviewed before adoption. Each claim is scoped to what is verifiable —
either from this Action's own behaviour or from the published V5 Evaluation API
contract.

### 1. Only an explicit, configured subset of the diff is read

The Action reads and transmits **only the added/modified lines** of files whose
extension matches `file_extensions` (default: `.md`, `.txt`, `.py` — the file
types that typically house system prompts and instructions). Files outside that
allowlist, removed lines, and unchanged context lines are never read or sent.
The allowlist is fully under your control via the `file_extensions` input.

### 2. The evaluation endpoint is a semantic execution boundary

For each matching file, only the extracted added text is sent to the evaluation
API over HTTPS. The API's purpose is to return a compliance verdict plus a
signed receipt; the raw text you send is **not** part of any signed, durably
stored record it returns (see §3). The Action never sends repository secrets,
environment variables, or the `context` metadata field.

### 3. The cryptographic receipt ledger stores a hash, not your source

Every evaluation returns a V5 Ed25519 receipt. Per the
[Evaluation API contract](../../core-clients/node), the signed and durably
stored **canonical payload binds your input by its SHA-256 hash
(`payload_hash`)** — never the raw text. The immutable ledger row records that
hash alongside the verdict, the short reasoning/steering strings, the statutory
anchors, the evaluated policy IDs, and a timestamp. Your proprietary source
content is therefore not persisted in the receipt: binding is by hash, which is
enough to prove offline that a specific input produced a specific verdict
(verify the signature against the published Ed25519 public key, then confirm
`SHA-256(input) === payload_hash`) without the ledger holding your code.

### Scope of these guarantees

§1 is enforced by this Action's code. §3 is guaranteed by the signed receipt
schema in the V5 contract and is independently verifiable. §2 describes the
intended request/response model: the durable audit artifact contains only the
hash, but how the transient request payload is handled in memory or forwarded to
the underlying evaluation model is an operational property of the ramen-ai
service, not something this Action enforces or that the public contract
specifies. For a formal, contractual zero-retention-of-source assurance, request
ramen-ai's data processing agreement, and avoid routing secrets through scanned
files.

---

## Building

The Action ships a single compiled bundle at `dist/index.js` (required by
GitHub Actions). To rebuild after changing `src/`:

```bash
npm install
npm run build      # esbuild -> dist/index.js
npm run typecheck  # tsc --noEmit
```
