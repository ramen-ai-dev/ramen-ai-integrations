"""policy_adapter — ramen-ai policy enforcement at the cMCP tool-call boundary.

Usage in a cMCP-compatible gateway:

    from ramen_cmcp import RamenCmcpAdapter

    adapter = RamenCmcpAdapter(
        api_key=os.environ["RAMEN_API_KEY"],
        bundle_ids=["ramen__shield_core_it"],
        provider_key=os.environ.get("OPENAI_API_KEY"),
    )

    decision = adapter.evaluate(tool_call_payload)
    if not decision.allowed:
        # return deny to cMCP gateway
        raise ToolCallDeniedError(decision.deny_message)

The adapter is stateless and thread-safe.  One instance may be shared across
concurrent request handlers.

cMCP tool-call payload shape (JSON-RPC 2.0 extension):
    {
      "jsonrpc": "2.0",
      "id": <int|str>,
      "method": "tools/call",
      "params": {
        "name": "<tool-name>",
        "arguments": { ... },
        "_cmcp": {
          "session_id": "<str>",
          "workflow_id": "<str>"
        }
      }
    }

The adapter serialises ``params.name`` + ``params.arguments`` as the
``input_text`` submitted to the ramen-ai API.  The ``_cmcp`` extension fields
are forwarded as ``context`` metadata for audit logging.

Allow/deny decision structure returned to the gateway:
    AdapterDecision(
        allowed=True,
        receipt=<dict>,          # V5 receipt for TRACE mapping; None if absent
        receipt_verified=<bool>,
        steering=None,
    )
    AdapterDecision(
        allowed=False,
        deny_message="[DENIED] <steering>",
        receipt=<dict | None>,
        receipt_verified=<bool>,
        statutory_anchors=["…"],
    )

Fail-closed: any transport or API error raises the underlying exception.
The caller must treat an exception as a deny decision.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from ramen_ai import RamenClient


@dataclass(frozen=True)
class AdapterDecision:
    """Allow or deny decision returned by :class:`RamenCmcpAdapter`."""

    allowed: bool
    """``True`` if the ramen-ai API verdict permits the tool call."""

    deny_message: str | None = None
    """Human-readable denial reason (steering text).  ``None`` when allowed."""

    receipt: dict[str, Any] | None = None
    """Raw V5 receipt dict from the API response.  ``None`` if signing failed."""

    receipt_verified: bool = False
    """``True`` only when a receipt was present and both verification steps passed."""

    receipt_alert: str | None = None
    """Populated when the server could not sign the receipt."""

    steering: str | None = None
    """Pipe-joined recovery instructions.  ``None`` when allowed with no guidance."""

    policy_ids: list[str] = field(default_factory=list)
    """Resolved policy UUIDs that were evaluated."""

    statutory_anchors: list[str] = field(default_factory=list)
    """Statutory anchors from the API response."""


class RamenCmcpAdapter:
    """Intercept a cMCP tool-call payload and enforce ramen-ai policy before
    the call reaches the downstream MCP server.

    Args:
        api_key:
            ramen-ai platform bearer token (``ramen_ak_...``).
            Load from ``RAMEN_API_KEY``; never hard-code.
        bundle_ids:
            One or more ramen-ai bundle slugs to evaluate against.
            Mutually exclusive with ``policy_ids``; both may be supplied.
        policy_ids:
            Explicit policy UUIDs.  Optional alongside ``bundle_ids``.
        provider_key:
            BYOK — forwarded as ``X-Provider-Key``.
            Required on Starter/Professional tiers.
        provider_name:
            BYOK — provider routing hint.  Defaults to ``"openai"``.
        base_url:
            Override the API base URL (staging / local testing).
        timeout:
            HTTP request timeout in seconds.  Defaults to 30.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        bundle_ids: list[str] | None = None,
        policy_ids: list[str] | None = None,
        provider_key: str | None = None,
        provider_name: str | None = None,
        base_url: str = "https://api.ramenai.dev",
        timeout: float = 30.0,
    ) -> None:
        resolved_key = api_key or os.environ.get("RAMEN_API_KEY", "")
        if not resolved_key:
            raise ValueError(
                "api_key must be provided or RAMEN_API_KEY must be set in the environment."
            )
        if not bundle_ids and not policy_ids:
            raise ValueError(
                "Provide at least one of 'bundle_ids' or 'policy_ids'."
            )

        self._client = RamenClient(
            api_key=resolved_key,
            base_url=base_url,
            timeout=timeout,
        )
        self._bundle_ids = bundle_ids
        self._policy_ids = policy_ids
        self._provider_key = provider_key or os.environ.get("OPENAI_API_KEY")
        self._provider_name = provider_name

    # ── public ────────────────────────────────────────────────────────────────

    def evaluate(self, tool_call_payload: dict[str, Any]) -> AdapterDecision:
        """Evaluate a cMCP JSON-RPC tool-call payload against ramen-ai policy.

        Args:
            tool_call_payload:
                The full JSON-RPC request dict (``method == "tools/call"``).
                ``params.name`` and ``params.arguments`` are serialised as the
                evaluated text.  ``params._cmcp`` is forwarded as audit context.

        Returns:
            :class:`AdapterDecision` with ``allowed=True`` or ``allowed=False``.

        Raises:
            httpx.HTTPStatusError: on 4xx/5xx responses from the ramen-ai API.
            ValueError: if the payload is missing ``params.name``.
        """
        input_text, context = self._extract(tool_call_payload)

        result = self._client.evaluate_compliance(
            input_text=input_text,
            bundle_ids=self._bundle_ids,
            policy_ids=self._policy_ids,
            context=context,
            provider_key=self._provider_key,
            provider_name=self._provider_name,
        )

        allowed: bool = result["allowed"]
        receipt: dict[str, Any] | None = result["data"].get("receipt")
        statutory: list[str] = result["data"].get("statutory_anchors") or []

        deny_message: str | None = None
        if not allowed:
            steering = result.get("steering") or "ramen-ai policy denied this tool call."
            deny_message = f"[DENIED] {steering}"

        return AdapterDecision(
            allowed=allowed,
            deny_message=deny_message,
            receipt=receipt,
            receipt_verified=result["receipt_verified"],
            receipt_alert=result.get("receipt_alert"),
            steering=result.get("steering"),
            policy_ids=result["policy_ids"],
            statutory_anchors=statutory,
        )

    def close(self) -> None:
        """Release the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> "RamenCmcpAdapter":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ── internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _extract(payload: dict[str, Any]) -> tuple[str, dict[str, str]]:
        """Serialise the tool call and build the audit context dict."""
        params: dict[str, Any] = payload.get("params") or {}
        tool_name: str = params.get("name") or ""
        if not tool_name:
            raise ValueError(
                "tool_call_payload must contain params.name (the tool name)."
            )
        arguments: dict[str, Any] = params.get("arguments") or {}
        cmcp_meta: dict[str, Any] = params.get("_cmcp") or {}

        input_text = json.dumps(
            {"tool": tool_name, "arguments": arguments},
            sort_keys=True,
            default=str,
        )

        context: dict[str, str] = {"tool_name": tool_name}
        if session_id := cmcp_meta.get("session_id"):
            context["session_id"] = str(session_id)
        if workflow_id := cmcp_meta.get("workflow_id"):
            context["workflow_id"] = str(workflow_id)

        return input_text, context
