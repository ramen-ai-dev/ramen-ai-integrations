# ramen-cmcp-adapter

<p align="center">
  <img src="../../assets/ramen-logo.png" alt="ramen-ai" width="100"/>
</p>

cMCP policy adapter and signed TRACE v0.2 Trust Record exporter for the ramen-ai evaluation API.

The adapter evaluates MCP tool-call intent with ramen-ai and maps a verified V5 evaluation receipt into the TRACE EAT profile `tag:agentrust-io.com,2026:trace-v0.2`.

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
  <a href="https://github.com/ramen-ai-dev/mcp-shield-proxy">
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
  <a href="https://github.com/ramen-ai-dev/dsh-ramen-guard">
    <img src="https://img.shields.io/badge/DeepSeek%20Harness-4D6BFE?style=flat&logo=deepseek&logoColor=white" alt="DeepSeek Harness"/>
  </a>
</p>

---

## Trust boundary

This integration emits **TRACE Level 0** records only:

- `runtime.platform` is always `software-only`.
- `runtime.measurement` is the conventional all-zero SHA-256 development measurement.
- `appraisal.status` is always `none` because no hardware verifier is present.
- The record is signed with a dedicated Ed25519 key from `TRACE_PRIVATE_KEY_PEM`.
- The ramen-ai receipt key is used only to verify the upstream V5 receipt and is never reused for TRACE signing.
- Level 1 hardware-attestation claims are intentionally rejected by the conformance suite.

## Public API

- `RamenCmcpAdapter.evaluate(tool_call_payload)` evaluates a cMCP `tools/call` payload and returns an `AdapterDecision`.
- `verify_v5_receipt(receipt, original_input)` verifies the V5 Ed25519 receipt and its SHA-256 input binding.
- `build_trace_record(receipt, original_input=..., ...)` verifies the V5 receipt, requires caller-owned evidence that the receipt cannot supply, loads the dedicated TRACE key, and returns a natively signed TRACE v0.2 record.

## Requirements

- Python 3.11 or newer
- `ramen-ai-core >= 0.2.0`
- `agentrust-trace == 0.5.1`
- `agentrust-trace-tests == 0.4.1` for conformance checks

Install from the monorepo root:

```bash
pip install -e core-clients/python
pip install -e "plugins/cmcp-python[dev]"
```

## Configuration

```bash
export RAMEN_API_KEY=ramen_ak_...
export OPENAI_API_KEY=sk_...
export TRACE_PRIVATE_KEY_PEM="$(openssl genpkey -algorithm ED25519)"
```

The OpenSSL command is suitable for local testing. Production must inject a persistent, independently managed TRACE Ed25519 private key through its secret manager. If `TRACE_PRIVATE_KEY_PEM` is absent or invalid, record construction fails closed; no ephemeral fallback is generated.

## Policy enforcement

```python
import os
from ramen_cmcp import RamenCmcpAdapter

adapter = RamenCmcpAdapter(
    api_key=os.environ["RAMEN_API_KEY"],
    bundle_ids=["ramen__shield_core_it"],
    provider_key=os.environ.get("OPENAI_API_KEY"),
)

decision = adapter.evaluate({
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "salesforce.contacts",
        "arguments": {"query": "Acme Corp"},
        "_cmcp": {"session_id": "s1", "workflow_id": "my-agent"},
    },
})

if not decision.allowed:
    raise RuntimeError(decision.deny_message)
```

## TRACE export

The V5 receipt contract does not identify the model, classify the data, hash the policy artifact, or describe the adapter build. Those claims must be supplied by the caller rather than inferred from the evaluated input.

```python
import hashlib
import time

from ramen_cmcp import build_trace_record

record = build_trace_record(
    receipt,
    original_input=original_input,
    iat=int(time.time()),
    model={
        "provider": "your-provider",
        "model_id": "your-model-id",
        "version": "your-model-version",
    },
    data_class="internal",
    policy_bundle_hash="sha256:" + hashlib.sha256(policy_artifact).hexdigest(),
    build_provenance={
        "slsa_level": 1,
        "builder": "https://your-builder.example",
        "digest": "sha256:" + hashlib.sha256(workload_artifact).hexdigest(),
    },
    appraisal_verifier="https://your-verifier.example/software-only",
)
```

`build_trace_record` first validates the ramen receipt signature and input binding. It then delegates key derivation, RFC 8785 canonicalization, and Ed25519 signing to `agentrust_trace.sign_record`. The returned object includes `cnf.jwk` and the top-level unpadded base64url `signature`.

## Field provenance

| TRACE field | Source |
|---|---|
| `eat_profile` | TRACE v0.2 constant |
| `subject` | Verified V5 receipt ID under the `ramenai.dev` SPIFFE trust domain |
| `model` | Required caller evidence |
| `runtime` | Fixed honest software-only Level 0 values |
| `policy.bundle_hash` | Required caller digest of the policy artifact in force |
| `policy.enforcement_mode` | `enforce`, matching the adapter's blocking behavior |
| `data_class` | Required caller classification |
| `build_provenance` | Required caller build evidence |
| `appraisal` | `none`, caller-supplied verifier URI, and issue time |
| `cnf.jwk`, `signature` | Native `agentrust_trace.sign_record` output |

The Level 0 record deliberately omits:

- `transparency`, because no SCITT receipt exists.
- `tool_transcript`, because a ramen evaluation receipt is not the full MCP/A2A transcript. A future transcript-aware integration must supply an actual transcript digest rather than relabeling the receipt payload.

## Tests and conformance

```bash
pytest plugins/cmcp-python/tests -v
```

The suite asserts both sides of the trust boundary:

1. A signed software-only record passes TRACE v0.2 Level 0.
2. The same record fails Level 1 specifically at `TR-RTE-001` because `software-only` is not a hardware TEE platform.
3. Invalid ramen receipt signatures and input bindings are rejected before TRACE signing.

To run the CLI path, provide real metadata values:

```bash
python plugins/cmcp-python/examples/emit_record.py \
  --out /tmp/ramen-trust-record.json \
  --model-provider your-provider \
  --model-id your-model \
  --data-class internal \
  --policy-bundle-hash sha256:<64-lowercase-hex> \
  --slsa-level 1 \
  --build-digest sha256:<64-lowercase-hex> \
  --appraisal-verifier https://your-verifier.example/software-only

trace-tests verify --record /tmp/ramen-trust-record.json --level 0
```
