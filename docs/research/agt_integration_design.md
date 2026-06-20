# Microsoft Agent Governance Toolkit (AGT) — Integration Design

**Status:** Research blueprint (Master Architect review pending)
**Author:** Coding Agent
**Date:** 2026-06-20
**Scope:** Mechanical integration path for embedding the ramen-ai L2 Semantic
Firewall directly into Microsoft AGT, for the `plugins/agt/` plugin.

> Sources are Microsoft's public AGT repository and docs (MIT-licensed):
> [BaseIntegration source](https://github.com/microsoft/agent-governance-toolkit),
> [Quick Start](https://microsoft.github.io/agent-governance-toolkit/quickstart/),
> [Framework Adapter Contract](https://microsoft.github.io/agent-governance-toolkit/specs/FRAMEWORK-ADAPTER-CONTRACT-1.0/),
> [TypeScript SDK tutorial](https://microsoft.github.io/agent-governance-toolkit/tutorials/20-typescript-sdk/).
> Code excerpts below are paraphrased/condensed for licensing compliance.

---

## 0. Decision: target the TypeScript SDK as primary

The operator's backend is TypeScript and already signs receipts with Ed25519.
AGT ships a first-class TypeScript SDK — `@microsoft/agent-governance-sdk` —
whose identity layer uses `@noble/ed25519`, the **same primitive family** our
backend and Node core-client use. This gives us:

- Shared types and a shared canonical-payload/verification path with the
  existing Node core-client (`core-clients/node/`), no Python-to-Node byte
  re-derivation risk.
- A single language across backend + plugin.

The Python path (below) remains valid and is documented for AutoGen/AGT-Python
hosts, but the **recommended build order is TypeScript first**.

---

## 1. The Hook — intercepting a planned action pre-execution

AGT exposes **three** interception surfaces, from shallowest to deepest.

### 1a. `govern()` wrapper (Python, shallowest)
```python
from agentmesh.governance import govern
safe_tool = govern(my_tool, policy="policy.yaml")
```
Evaluates the policy on every call, logs the decision, and raises
`GovernanceDenied` on block. Good for a quick proof-of-concept, too coarse for
our firewall (it gates on the YAML policy engine, not a custom evaluator).

### 1b. `ToolCallInterceptor` protocol (Python, mid-level)
Defined in `agent_os.integrations.base`. A structural protocol — implement one
method:
```python
class ToolCallInterceptor(Protocol):
    def intercept(self, request: ToolCallRequest) -> ToolCallResult: ...
```
`ToolCallRequest` carries `tool_name`, `arguments`, `call_id`, `agent_id`,
`metadata`. Interceptors compose via `CompositeInterceptor` (all must allow).
This is the cleanest seam for a custom check that does not need full lifecycle
context.

### 1c. `BaseIntegration` ABC (Python, deepest — recommended for Python hosts)
Every framework adapter extends the single abstract base class
`BaseIntegration` and maps the host framework's native hook surface onto a
unified contract. The pre-execution gate is:
```python
def pre_execute_check(self, ctx: ExecutionContext, input_data: Any) -> PolicyCheckResult
# async: async_pre_execute_check(...)
```
A custom `PolicyEvaluator` can be injected (`evaluator=...` or
`BaseIntegration.from_cedar(...)`); `pre_execute_check` consults it first and
**fails closed** if it raises. Subclasses must implement `wrap(agent)` /
`unwrap(governed_agent)` and may override `_build_cedar_context(...)`.

### 1d. TypeScript — `AgentMeshClient.executeWithGovernance()` (recommended)
The TS SDK runs every action through a 4-stage pipeline
(policy → trust → audit → trust-update):
```typescript
const gov = await client.executeWithGovernance(action, context);
// gov.decision: 'allow' | 'deny' | 'review'
```
For deeper control, `PolicyEngine.evaluatePolicy(did, context)` returns a
`PolicyDecisionResult` directly. The TS SDK does **not** throw on deny — it
returns a `decision`; the host enforces it. Our wrapper raises/blocks.

**Answer:** Python → subclass `BaseIntegration` (or a `ToolCallInterceptor`);
TypeScript → wrap `AgentMeshClient.executeWithGovernance` (or call
`PolicyEngine.evaluatePolicy`).

---

## 2. The Steering — communicating denial + our custom instruction

### Python
Denials are structured, not just booleans. `PolicyCheckResult` (a Pydantic
model in `agent_os.policies.decision`) carries:

| Field | Use for us |
|---|---|
| `allowed: bool` | `False` to block |
| `reason: str` | legacy free-form string — **our steering instruction** |
| `public_message: str` | sanitized, end-user-safe message |
| `category: ViolationCategory` | map our violation type |
| `audit_entry: dict[str, Any]` | structured metadata (see §3) |

`ToolCallResult(allowed=False, reason=...)` is the interceptor-level
equivalent. When the wrapper raises, `PolicyViolationError.from_check_result`
builds the error and merges `**result.audit_entry` into the error `details`.

**Yes — we pass our steering string directly via `reason` / `public_message`.**
Recommended: put the agent-facing recovery directive in `public_message`
(end-user safe) and the full clinical reasoning in `reason`/`detail`.

### TypeScript
`PolicyDecisionResult` includes a `reason?: string` field and `matchedRule` /
`policyName`. `GovernanceResult` returns `decision` plus the `auditEntry`. Our
governed wrapper reads `decision !== 'allow'` and surfaces our steering string
(from the firewall response) to the host as the denial message.

**Answer:** Yes — both SDKs accept a custom denial string. Python: `reason` /
`public_message` on `PolicyCheckResult`. TypeScript: `reason` on the decision
result, carried through to the host by our wrapper.

---

## 3. The Evidence — attaching our Ed25519 receipt + statutory anchors

### Python
Two complementary surfaces:

1. **`PolicyCheckResult.audit_entry: dict[str, Any]`** — free-form structured
   metadata. This is where our receipt rides. It propagates into the raised
   `PolicyViolationError.details` via `from_check_result` (`**result.audit_entry`).
2. **Event bus** — `BaseIntegration.on(event_type, callback)` /
   `emit(event_type, data: dict)` over `GovernanceEventType`
   (`POLICY_CHECK`, `POLICY_VIOLATION`, `TOOL_CALL_BLOCKED`, ...). The helper
   `emit_skill_audit_event(..., **extra)` accepts arbitrary extra keys, so we
   emit a `ramen_receipt` payload alongside the standard audit fields.

Proposed audit payload shape (attached to every governed decision):
```python
audit_entry = {
    "ramen_receipt": {
        "id": receipt["id"],
        "schema_version": "5.0",
        "kid": receipt["kid"],
        "signature": receipt["signature"],
        "canonical_payload": receipt["canonical_payload"],
    },
    "statutory_anchors": ["FCA PRIN 2A.2.8", ...],
    "ramen_verified": True,  # result of local verify_receipt()
}
```

### TypeScript
`AuditLogger` is an append-only **hash-chain** (each entry's SHA-256 includes
the previous hash — tamper-evident). Entries are created via
`logger.log({ agentId, action, decision })` and the chain is checked with
`logger.verify()`.

**Open question for the MA (verify before building):** the documented
`AuditLogger.log()` signature shows only `{agentId, action, decision}`. We must
confirm whether entries accept an arbitrary metadata field for embedding the
receipt, or whether we attach the receipt out-of-band (e.g., encode a receipt
reference into `action`, or keep our own parallel ledger keyed by the AGT entry
`hash`). Do **not** assume an undocumented metadata field.

**Answer:** Python — yes, via `audit_entry` (and the event bus). TypeScript —
the hash-chain logger is ideal conceptually, but the metadata-attachment
mechanism needs confirmation; our receipt already carries its own Ed25519 proof
independent of AGT's chain.

---

## 4. Proposed plugin structure

### 4a. TypeScript (primary) — `plugins/agt/` (TS) or under `core-clients/node`
```
plugins/agt-ts/
├── package.json            # deps: @microsoft/agent-governance-sdk, ramen-ai-core (node)
├── src/
│   ├── governedClient.ts   # wraps AgentMeshClient.executeWithGovernance
│   ├── firewall.ts         # calls ramen-ai backend /paas/evaluate
│   ├── receipt.ts          # re-exports Node core-client verifier (shared types)
│   └── index.ts
└── tests/
```
Sketch:
```typescript
import { AgentMeshClient } from '@microsoft/agent-governance-sdk';
import { evaluateCompliance, verifyReceipt } from 'ramen-ai-core';

export async function governAction(client: AgentMeshClient, action: string, input: string) {
  const verdict = await evaluateCompliance(input, { /* policy/bundle ids */ });
  if (!verdict.allowed) {
    // steering string + receipt → host
    throw new GovernanceDenied(verdict.steering, { receipt: verdict.receipt });
  }
  return client.executeWithGovernance(action, { input });
}
```

### 4b. Python (secondary) — `plugins/agt/` (Python, for AGT-Python / AutoGen hosts)
```
plugins/agt/
├── pyproject.toml          # deps: agent-governance-toolkit, ramen-ai-core
├── ramen_agt/
│   ├── integration.py      # class RamenFirewallIntegration(BaseIntegration)
│   ├── interceptor.py      # class RamenInterceptor (ToolCallInterceptor)
│   └── __init__.py
└── tests/
```
Sketch:
```python
from agent_os.integrations.base import BaseIntegration, ExecutionContext
from agent_os.policies.decision import PolicyCheckResult, ViolationCategory
from ramen_ai import RamenClient  # our core-clients/python package

class RamenFirewallIntegration(BaseIntegration):
    def __init__(self, ramen_api_key: str, **kw):
        super().__init__(**kw)
        self._ramen = RamenClient(api_key=ramen_api_key)

    def wrap(self, agent): ...      # map host hook -> pre_execute_check
    def unwrap(self, governed): ...

    def pre_execute_check(self, ctx: ExecutionContext, input_data) -> PolicyCheckResult:
        text = self._extract_text_payload(input_data)
        res = self._ramen.evaluate_compliance(text, policy_ids=[...])
        if res["allowed"]:
            return PolicyCheckResult(allowed=True)
        receipt = res["data"].get("receipt", {})
        return PolicyCheckResult(
            allowed=False,
            category=ViolationCategory.POLICY_ERROR,
            public_message=res["steering"] or "Blocked by ramen-ai firewall",
            reason=res["steering"] or "Blocked by ramen-ai firewall",
            audit_entry={
                "ramen_receipt": receipt,
                "statutory_anchors": res["data"].get("statutory_anchors", []),
                "ramen_verified": res["receipt_verified"],
            },
        )
```

---

## 5. Required imports — reference

**Python**
```python
from agent_os.integrations.base import (
    BaseIntegration, ToolCallInterceptor, ToolCallRequest, ToolCallResult,
    ExecutionContext, GovernancePolicy, GovernanceEventType,
)
from agent_os.policies.decision import PolicyCheckResult, ViolationCategory
from agent_os.exceptions import PolicyViolationError
```
**TypeScript**
```typescript
import {
  AgentMeshClient, PolicyEngine, AuditLogger,
  type GovernanceResult, type PolicyDecisionResult,
} from '@microsoft/agent-governance-sdk';
```

---

## 6. Build order & open questions for the Master Architect

1. **Confirm primary target = TypeScript SDK** (recommended; matches backend).
2. **TS audit metadata:** confirm how to attach our receipt to an
   `AuditLogger` entry (or use a parallel ledger keyed by AGT entry hash).
3. **Pin versions:** TS `@microsoft/agent-governance-sdk` (docs show v3.7.0);
   Python `agent-governance-toolkit[full]`. Verify latest stable before pinning.
4. **Decision mapping:** AGT `review` (require-approval) vs our `allowed=false` —
   define how `require_approval` maps to a firewall verdict.
5. **Fail-closed parity:** AGT fails closed on evaluator error; our wrapper must
   do the same when the backend `/paas/evaluate` call fails.

Per AGENTS.md, this is a blueprint only — no plugin code is to be written until
the Master Architect ratifies the target and resolves the open questions above.
