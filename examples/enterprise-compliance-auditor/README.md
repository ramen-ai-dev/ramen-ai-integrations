# Enterprise Compliance Auditor

A synthetic enterprise-security demonstration of concurrent ramen-ai compliance evaluation, locally verified Ed25519 receipts, audit evidence generation, and a live CISO-facing threat dashboard.

This directory contains two related workflows:

1. **Historical compliance audit** — evaluates 20 fixed historical assistant outputs against one configured policy and writes a Markdown evidence report.
2. **CISO Threat Matrix** — evaluates 1,000 simulated agent tool calls against the `ramen__shield_core_it` bundle, or a configured proxy policy, while rendering live interception telemetry in the terminal.

Both workflows use the public `ramen-ai-core` Python SDK. They do not construct API requests, authentication headers, receipt payloads, or cryptographic verification logic themselves.

## API Key

A live run requires a ramen-ai API key. Account and tier information is available at [ramenai.dev/pricing](https://ramenai.dev/pricing).

The CISO dashboard submits **1,000 live evaluations**. Confirm account quota, rate limits, and provider configuration before running it. The scripts currently pass `RAMEN_API_KEY` but do not forward a per-request BYOK provider key; use an account or configured proxy policy that supports this evaluation path.

Never commit `.env`, API keys, provider credentials, receipts, or customer log data.

## What the Demo Shows

The simulated traffic resembles normal enterprise agent activity:

- Jira ticket summaries
- AWS inventory and CloudWatch queries
- GitHub pull-request lookups
- ServiceNow change checks
- Snowflake analytics queries
- Slack and Datadog searches

The large CISO corpus contains exactly 1,000 records:

| Fixture classification | Count | Examples |
|---|---:|---|
| Benign | 950 | Read-only ticket, infrastructure, monitoring, and analytics requests |
| Secret Exfiltration | 17 | Simulated `.env`, environment-variable, and secrets-manager extraction |
| Destructive Execution | 17 | Simulated `DROP TABLE`, recursive deletion, and infrastructure-destroy commands |
| OWASP ASI06 | 16 | Base64-encoded indirect prompt injections instructing an agent to exfiltrate secrets |

The malicious strings are inert test data. This example sends them to the evaluation API as text; it never executes a shell command, SQL statement, cloud operation, decoded instruction, or tool call. Exfiltration URLs use the reserved `.invalid` domain.

## Trust Boundary

The fixture labels describe the synthetic scenario; they do not control the ramen verdict. A record marked `malicious: true` is not automatically counted as blocked, and a record marked benign is not automatically counted as allowed.

For each record, the application:

1. Sends the exact `payload` string to `RamenClient.evaluate_compliance()`.
2. Supplies the log ID, timestamp, source, and tool name as audit context.
3. Uses either the configured policy UUID or the `ramen__shield_core_it` bundle.
4. Reads the observed `allowed` verdict from the SDK result.
5. Accepts a receipt `kid` as verified evidence only when `receipt_verified` is exactly `True`.
6. Uses response statutory anchors and triggered policy labels to populate the threat matrix.
7. Uses the SDK-provided steering string in the live intercept feed.

Receipt signature validation, canonical-payload validation, input-hash binding, verdict binding, policy binding, and statutory-anchor binding are performed by `ramen-ai-core`. The example does not duplicate those security operations.

The dashboard therefore demonstrates observed policy enforcement, not a guaranteed benchmark score. Exact blocked counts depend on the deployed bundle or proxy policy and backend configuration.

## Setup

Use Python 3.11 or newer. From the repository root on macOS or Linux:

```bash
cd examples/enterprise-compliance-auditor
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and set local credentials and policy configuration:

```dotenv
RAMEN_API_KEY="ramen_ak_..."
RAMEN_POLICY_UUID="0d5ed2af-5e98-4a8c-92c3-dea26c07bf9a"
```

Configuration behavior differs slightly between the two workflows:

| Variable | Historical audit | CISO dashboard |
|---|---|---|
| `RAMEN_API_KEY` | Required | Required |
| `RAMEN_POLICY_UUID` | Required | Optional override |
| `CISO_MAX_WORKERS` | Not used | Optional; defaults to `20`, valid range `1`–`128` |

When `RAMEN_POLICY_UUID` is set, the dashboard evaluates against that configured proxy policy. When it is absent or still contains `<YOUR_POLICY_UUID>`, the dashboard evaluates against `ramen__shield_core_it`.

Environment variables already present in the invoking shell take precedence over values in `.env`.

## Run the Historical Audit

```bash
./.venv/bin/python auditor.py
```

The historical workflow:

- Loads `historical_logs.jsonl`.
- Requires exactly 20 records and five fixture-designated expected violations.
- Evaluates records through five `ThreadPoolExecutor` workers.
- Prints completion status as each evaluation returns.
- Writes `AUDIT_REPORT.md` with observed blocked payloads, triggered policies, and compact verified-receipt evidence.

`AUDIT_REPORT.md` is generated and gitignored. `AUDIT_REPORT.example.md` is a checked-in format example; its counts are illustrative and are not a promise about future API outcomes.

Exit codes:

| Code | Meaning |
|---:|---|
| `0` | Audit completed with no receipt evidence failures |
| `1` | One or more evaluations lacked verifiable receipt evidence |
| `2` | Configuration or input-corpus validation failed |

Observed policy blocks are findings, not process failures, so they do not by themselves produce a non-zero exit code.

## Run the CISO Threat Matrix

The generated corpus is checked in as `ciso_logs.jsonl`. To reproduce it deterministically:

```bash
./.venv/bin/python generate_ciso_logs.py
```

Run the live dashboard:

```bash
./.venv/bin/python ciso_dashboard.py
```

To reduce or increase bounded concurrency without changing source:

```bash
CISO_MAX_WORKERS=10 ./.venv/bin/python ciso_dashboard.py
```

The executor submits all 1,000 evaluations and processes results in completion order. `CISO_MAX_WORKERS` controls the number of simultaneous worker threads; it does not change the number of evaluations.

### Dashboard Panels

**Progress Panel**

Tracks completed evaluations out of 1,000 and shows how many remain in flight or queued.

**Threat Matrix**

Shows live `[ALLOWED]`, `[BLOCKED]`, and receipt-evidence-failure counts. Blocked requests are broken down by returned statutory anchors or triggered policy labels. Known labels are normalized for display as `OWASP ASI06`, `Secret Exfiltration`, or `Destructive Execution` when the returned metadata supports that mapping.

A single blocked evaluation may carry more than one anchor or rule label, so the breakdown rows can sum to more than the total blocked count.

**Live Intercept Feed**

Shows the latest observed blocked payload in red, together with:

- The exact submitted payload
- The SDK-provided steering instruction
- Triggered anchors or rules
- The verified Ed25519 receipt `kid`

If receipt verification fails, the panel displays `UNVERIFIED RECEIPT` and an evidence alert. It never presents an unverified raw `kid` as trusted evidence.

The SDK exposes a synchronous `evaluate_compliance()` call rather than a passive-evaluation callback API. Worker futures return complete SDK results; the main thread routes each completed result into dashboard state and refreshes Rich. Worker threads do not mutate terminal UI state.

Dashboard exit codes:

| Code | Meaning |
|---:|---|
| `0` | All 1,000 evaluations completed with verifiable receipt evidence |
| `1` | One or more API/worker/receipt evidence failures occurred |
| `2` | API key, worker configuration, or corpus validation failed |

## Failure Handling

The scripts preserve row-level failures instead of silently discarding them. Common causes include:

| Symptom | Likely cause |
|---|---|
| `401 Unauthorized` | Invalid or expired `RAMEN_API_KEY` |
| `402 Payment Required` | Account requires per-request provider credentials not forwarded by this demo |
| `429 Too Many Requests` | Worker concurrency exceeds the account rate limit |
| Receipt absent or unverified | Signing alert, unknown key ID, invalid signature, binding mismatch, or non-V5 receipt |
| Corpus validation failure | Missing, malformed, duplicate, or incorrectly counted JSONL records |

For rate-limit pressure, lower `CISO_MAX_WORKERS`. Do not weaken receipt checks to make a sales demonstration appear successful.

## Files

| File | Purpose |
|---|---|
| `auditor.py` | Concurrent 20-record historical audit and Markdown report generation |
| `historical_logs.jsonl` | Fixed historical audit fixture |
| `AUDIT_REPORT.example.md` | Checked-in example of the historical report format |
| `ciso_dashboard.py` | Rich live CISO Threat Matrix and concurrent SDK evaluation loop |
| `generate_ciso_logs.py` | Deterministic 1,000-record corpus generator |
| `ciso_logs.jsonl` | Generated 950-benign/50-malicious CISO corpus |
| `.env.example` | Local configuration template; contains no usable secret |
| `requirements.txt` | Pinned Python dependencies |

Local-only files include `.env`, `.venv/`, `__pycache__/`, and generated `AUDIT_REPORT.md`. They must not be committed.

## Agent and Contributor Invariants

Agents and contributors changing this example must preserve these boundaries:

- Use the public `ramen-ai-core` SDK; do not hand-roll HTTP requests, authentication, signing, receipt parsing, or Ed25519 verification.
- Keep credentials in `.env` or the process environment only.
- Keep malicious fixtures inert. Never add code that executes fixture payloads or decoded prompt injections.
- Preserve deterministic corpus generation and validate exactly 1,000 records, 950 benign records, and 50 malicious records.
- Drive dashboard counters from observed SDK results, never from `expected_outcome`, `malicious`, or `expected_rule_set` fixture labels.
- Trust and display a receipt `kid` only after SDK verification succeeds.
- Retain explicit API, worker, malformed-response, and receipt failure handling.
- Keep Rich state mutation on the main thread consuming `as_completed()` results.
- Do not replace bounded concurrency with 1,000 worker threads. Submit 1,000 jobs to the bounded executor instead.
- Do not add real customer prompts, credentials, production endpoints, or operationally executable attack targets to the corpus.
- When changing the generator, regenerate `ciso_logs.jsonl` and verify that the checked-in output exactly matches generator output.

## Demo Limitations

- All logs, identities, tickets, account numbers, tool calls, and attacks are synthetic.
- The dashboard is a terminal sales and evaluation aid, not a SIEM, SOC case-management system, or production log shipper.
- It evaluates payload strings independently; it does not execute or observe real agent tools.
- Returned policy labels are backend response metadata and may vary as bundle definitions evolve.
- Terminal output intentionally shows intercepted payloads. Do not replace the synthetic corpus with sensitive customer logs during a screen-shared demonstration.
- A successful run proves that the observed responses carried SDK-verified receipts bound to the submitted inputs; it does not independently prove the truth of external source data or future policy behavior.
