# ramen-cmcp-adapter

cMCP policy adapter and TRACE Trust Record exporter for the ramen-ai evaluation API.

Intercepts tool calls at the cMCP boundary, evaluates them via
[ramen-ai](https://ramenai.dev), and maps the resulting V5 Ed25519-signed
receipt onto a TRACE Trust Record ([EAT profile
`tag:agentrust.io,2026:trace-v0.1`](https://github.com/agentrust-io/trace-spec)).

## What it does

- **`RamenCmcpAdapter.evaluate(tool_call_payload)`** — takes a cMCP JSON-RPC
  `tools/call` payload, serialises `params.name` + `params.arguments` as the
  evaluated text, calls `POST /api/v1/paas/evaluate`, and returns an
  `AdapterDecision` with `allowed: bool`, the raw V5 receipt, and a
  `[DENIED] <steering>` message when the call is blocked.
- **`build_trace_record(receipt, iat, jwk)`** — maps a ramen-ai V5 receipt onto
  a TRACE Trust Record dict. Sign with `agentrust_trace.sign_record` to produce
  a cMCP-compatible envelope for `trace-tests verify`.
- **`verify_v5_receipt(receipt, original_input)`** — standalone two-step
  verifier: Ed25519 signature over `canonical_payload`, then SHA-256 input
  binding. Uses the built-in production key (`ramen_pk_v1`) and the conformance
  doc ephemeral key (`ramen_pk_ephemeral_test`).

## What it does NOT claim

- The adapter does not modify the cMCP runtime, Cedar policies, or the upstream
  MCP server. It is a pre-call evaluation hook only.
- `runtime.platform` is `software-only`. No TEE or hardware attestation is
  exercised by this integration.
- TRACE conformance level 0 is targeted. The released `agentrust-trace-tests`
  0.1.0 loader rejects plain records carrying a top-level `signature` field
  (anti-downgrade), so the `trace-tests`-gradable output is the unsigned
  payload; the signed form is written alongside it. See the
  [SpendGuard integration](https://github.com/agentrust-io/integrations/tree/main/integrations/spendguard)
  for the same limitation described in detail.
- V5 receipts prove input binding, verdict, and policy UUIDs at the time of
  evaluation. Policy *rule content* is mutable under the same UUID; see
  `alane-v5-conformance.md §6` for the full disclosure.

## Requirements

- Python ≥ 3.10
- `ramen-ai-core >= 0.2.0` (editable install from this monorepo)
- `cryptography >= 42.0.0`

Optional, for the TRACE conformance workflow:

- `agentrust-trace >= 0.3.0`
- `agentrust-trace-tests >= 0.1.0`

## Installation

From the monorepo root:

```bash
# core adapter only
pip install -e plugins/cmcp-python

# with TRACE conformance tooling
pip install -e "plugins/cmcp-python[agentrust]"

# with test dependencies
pip install -e "plugins/cmcp-python[dev]"
```

## Configuration

```bash
export RAMEN_API_KEY=ramen_ak_...        # required — ramen-ai platform token
export OPENAI_API_KEY=sk-...             # required on Starter/Professional tiers (BYOK)
```

## cMCP policy enforcement

```python
import os
from ramen_cmcp import RamenCmcpAdapter

adapter = RamenCmcpAdapter(
    api_key=os.environ["RAMEN_API_KEY"],
    bundle_ids=["ramen__shield_core_it"],
    provider_key=os.environ.get("OPENAI_API_KEY"),
)

# cMCP JSON-RPC tool-call payload (method == "tools/call")
tool_call = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "salesforce.contacts",
        "arguments": {"query": "Acme Corp"},
        "_cmcp": {"session_id": "s1", "workflow_id": "my-agent"},
    },
}

decision = adapter.evaluate(tool_call)

if not decision.allowed:
    # return deny to the cMCP gateway
    raise RuntimeError(decision.deny_message)

# call is allowed — proceed to the MCP server
```

`_cmcp.session_id` and `_cmcp.workflow_id` are forwarded to the ramen-ai audit
log as context metadata. They are never included in the evaluated text.

## TRACE Trust Record export

```python
import time
import agentrust_trace
from ramen_cmcp import build_trace_record, verify_v5_receipt

# 1. Verify the V5 receipt before mapping
valid, reason = verify_v5_receipt(receipt, original_input)
assert valid, f"Receipt invalid: {reason}"

# 2. Generate an ephemeral key for the TRACE record
key = agentrust_trace.generate_key()
jwk = agentrust_trace.key_to_jwk(key)

# 3. Build the unsigned TRACE Trust Record
record = build_trace_record(receipt, iat=int(time.time()), jwk=jwk)

# 4. Sign and verify the round-trip
signed = agentrust_trace.sign_record(record, key)
agentrust_trace.verify_record(signed, allow_embedded_key=True)
```

See `examples/emit_record.py` for the full end-to-end script.

## TRACE field mapping

| TRACE field | Source |
|---|---|
| `eat_profile` | `"tag:agentrust.io,2026:trace-v0.1"` (constant) |
| `subject` | `"urn:ramen-ai:receipt:<kid>:<receipt.id>"` |
| `policy.bundle_hash` | `canonical_payload.payload_hash` (SHA-256 of evaluated input) |
| `policy.version` | `canonical_payload.schema_version` (`"5.0"`) |
| `policy.enforcement_mode` | `"enforce"` (constant) |
| `runtime.measurement` | `receipt.id` (UUID of the evaluation event) |
| `runtime.platform` | `"software-only"` (constant) |
| `tool_transcript.hash` | `canonical_payload.payload_hash` |
| `tool_transcript.transcript_uri` | `"urn:ramen-ai:evaluation:<receipt.id>"` |
| `appraisal.status` | `"affirming"` if `verdict==1`, else `"denying"` |
| `appraisal.policy_ref` | comma-joined `canonical_payload.policy_ids` |
| `appraisal.statutory_anchors` | `canonical_payload.statutory_anchors` (when non-empty) |
| `appraisal.steering` | `canonical_payload.steering` (omitted when empty) |

## Running the tests

```bash
pip install -e "plugins/cmcp-python[dev]"
pytest plugins/cmcp-python/tests -v
```

No network access or real credentials are required. HTTP calls are intercepted
by `pytest-httpx`. The conformance vectors use the ephemeral key from
`alane-v5-conformance.md §3.2`, embedded in `_receipt_verify._AUDIT_PUBLIC_KEYS`.

## Running the conformance workflow locally

```bash
pip install -e "plugins/cmcp-python[agentrust]"
python plugins/cmcp-python/examples/emit_record.py --out /tmp/trust-record.jwt
trace-tests verify --record /tmp/trust-record.jwt --level 0
```

The CI workflow (`.github/workflows/ramen-cmcp-conformance.yml`) runs this
matrix across Python 3.11–3.13 on every push that touches this plugin.
