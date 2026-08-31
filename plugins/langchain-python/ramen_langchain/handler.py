"""
ramen_langchain.handler — LangChain BaseCallbackHandler integration.

The :class:`RamenSafetyCallbackHandler` wires the ramen-ai L2 Semantic
Firewall into any LangChain agent or chain as a standard callback.  It
intercepts every tool call in ``on_tool_start``, evaluates the serialized
tool definition and the resolved input string against the ramen-ai
evaluation API, and raises :exc:`.exceptions.RamenSafetyException` to halt
the LangChain execution chain before the tool's ``_run`` / ``_arun`` is ever
called.

Architecture note
-----------------
LangChain's callback system is synchronous at the ``on_tool_start`` boundary
even when the surrounding chain is async.  This handler therefore uses the
synchronous ``RamenClient`` from ``ramen-ai-core``.  If you need async
support wrap the call with ``asyncio.to_thread`` or swap the client for an
async HTTP variant in a future iteration.

Fail-closed behaviour
---------------------
Any exception raised during the evaluation request (network error, timeout,
parse error, HTTP 4xx/5xx) is treated as a BLOCK.  An unreachable firewall
must never become an open door.  The original exception is attached as
``__cause__`` to the resulting :exc:`.exceptions.RamenSafetyException` so
operators can distinguish infrastructure failures from policy blocks.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from langchain_core.callbacks.base import BaseCallbackHandler

from ramen_ai import RamenClient

from .exceptions import RamenSafetyException

logger = logging.getLogger(__name__)


class RamenSafetyCallbackHandler(BaseCallbackHandler):
    """
    LangChain callback handler that intercepts tool calls and evaluates them
    against the ramen-ai L2 Semantic Firewall before execution.

    Parameters
    ----------
    api_key:
        ramen-ai bearer token (``ramen_ak_...``).  Load from the environment
        — never hard-code.
    bundle_ids:
        One or more pre-built bundle slugs to evaluate against
        (e.g. ``["ramen__shield_core_it"]``).
    policy_ids:
        Explicit policy UUIDs.  At least one of *bundle_ids* or *policy_ids*
        must be non-empty.
    provider_key:
        BYOK — your LLM provider API key (OpenAI, Anthropic, etc.).
        Required on Starter / Professional tiers; forwarded as the
        ``X-Provider-Key`` header.  Omit on Enterprise.
    provider_name:
        Provider identifier paired with ``provider_key`` (for example,
        ``"openai"`` or ``"anthropic"``); forwarded as the
        ``X-Provider`` header. Omit on Enterprise.
    base_url:
        Override the ramen-ai API base URL (for staging / local testing).
    timeout:
        HTTP request timeout in seconds (default: 30).
    require_receipt_verified:
        When ``True`` (default), an ALLOWED verdict whose Ed25519 receipt
        cannot be locally verified is escalated to a BLOCK.  Set to
        ``False`` to allow unverified receipts through (not recommended).
    context:
        Optional string-keyed metadata forwarded to the audit log on every
        evaluation request.

    Example
    -------
    ::

        import os
        from langchain.agents import AgentExecutor
        from ramen_langchain import RamenSafetyCallbackHandler, RamenSafetyException

        handler = RamenSafetyCallbackHandler(
            api_key=os.environ["RAMEN_API_KEY"],
            bundle_ids=["ramen__shield_core_it"],
            provider_key=os.environ.get("OPENAI_API_KEY"),
            provider_name="openai" if os.environ.get("OPENAI_API_KEY") else None,
        )

        try:
            result = agent_executor.invoke(
                {"input": user_prompt},
                config={"callbacks": [handler]},
            )
        except RamenSafetyException as exc:
            print(f"Blocked: {exc.steering}")
    """

    # Tell LangChain not to suppress exceptions raised in this handler.
    raise_error = True

    def __init__(
        self,
        *,
        api_key: str,
        bundle_ids: list[str] | None = None,
        policy_ids: list[str] | None = None,
        provider_key: str | None = None,
        provider_name: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
        require_receipt_verified: bool = True,
        context: dict[str, str] | None = None,
    ) -> None:
        super().__init__()

        if not bundle_ids and not policy_ids:
            raise ValueError(
                "RamenSafetyCallbackHandler requires at least one of "
                "'bundle_ids' or 'policy_ids'."
            )

        client_kwargs: dict[str, Any] = {"api_key": api_key, "timeout": timeout}
        if base_url:
            client_kwargs["base_url"] = base_url

        self._client = RamenClient(**client_kwargs)
        self._bundle_ids = list(bundle_ids) if bundle_ids else []
        self._policy_ids = list(policy_ids) if policy_ids else []
        self._provider_key = provider_key
        self._provider_name = provider_name
        self._require_receipt_verified = require_receipt_verified
        self._context = context or {}

    # ------------------------------------------------------------------ #
    # Core interception hook                                               #
    # ------------------------------------------------------------------ #

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Called by LangChain immediately before a tool is executed.

        Constructs the evaluation payload from the serialised tool definition
        and the resolved input string, calls the ramen-ai evaluation API, and
        raises :exc:`.exceptions.RamenSafetyException` if the verdict is
        BLOCKED (or if the firewall cannot be reached — fail-closed).

        Parameters
        ----------
        serialized:
            LangChain's internal serialisation of the tool being invoked.
            Contains ``name``, ``description``, and schema metadata.
        input_str:
            The tool input as a string.  Non-string inputs are cast to
            strings by LangChain before this callback fires.
        """
        tool_name: str = serialized.get("name", "unknown_tool")

        # Build the evaluation payload: tool name + description + input, so
        # the evaluator has full context about what the agent is about to do.
        payload: dict[str, Any] = {
            "tool": tool_name,
            "description": serialized.get("description", ""),
            "input": input_str,
        }
        # Include structured inputs when available (richer context for the
        # evaluator than the flattened string representation alone).
        if inputs:
            payload["inputs"] = inputs

        payload_json = json.dumps(payload, ensure_ascii=False)

        logger.debug(
            "ramen-ai: evaluating tool call '%s' (run_id=%s)", tool_name, run_id
        )

        try:
            result = self._client.evaluate_compliance(
                input_text=payload_json,
                bundle_ids=self._bundle_ids or None,
                policy_ids=self._policy_ids or None,
                context={
                    **self._context,
                    "tool_name": tool_name,
                    "run_id": str(run_id),
                },
                provider_key=self._provider_key,
                provider_name=self._provider_name,
            )
        except Exception as exc:
            # Fail-closed: infrastructure failures are treated as blocks.
            logger.error(
                "ramen-ai: evaluation request failed for tool '%s' — "
                "treating as BLOCKED (fail-closed). Error: %s",
                tool_name,
                exc,
            )
            safety_exc = RamenSafetyException(
                tool_name=tool_name,
                steering=(
                    "ramen-ai evaluation could not complete. "
                    "The tool call has been halted (fail-closed). "
                    f"Underlying error: {exc}"
                ),
                receipt_verified=False,
                statutory_anchors=[],
            )
            raise safety_exc from exc

        allowed: bool = result["allowed"]
        steering: str | None = result["steering"]
        receipt_verified: bool = result["receipt_verified"]
        statutory_anchors: list[str] = result["data"].get("statutory_anchors") or []

        # Fail-closed on evidence: an ALLOWED verdict with an unverifiable
        # receipt is escalated to a BLOCK when require_receipt_verified=True.
        receipt_present = result.get("receipt_valid") is not None
        evidence_block = (
            allowed
            and receipt_present
            and not receipt_verified
            and self._require_receipt_verified
        )

        if not allowed or evidence_block:
            reason = (
                "[BLOCKED] policy violation"
                if not allowed
                else "[BLOCKED] unverifiable receipt (fail-closed on evidence)"
            )
            logger.warning(
                "ramen-ai: %s for tool '%s'. Anchors: %s. Steering: %s. "
                "Receipt verified: %s.",
                reason,
                tool_name,
                statutory_anchors or "none",
                steering,
                receipt_verified,
            )
            raise RamenSafetyException(
                tool_name=tool_name,
                steering=steering,
                receipt_verified=receipt_verified,
                statutory_anchors=statutory_anchors,
            )

        logger.info(
            "ramen-ai: ALLOWED tool '%s' (receipt_verified=%s).",
            tool_name,
            receipt_verified,
        )

    # ------------------------------------------------------------------ #
    # Resource management                                                  #
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> RamenSafetyCallbackHandler:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
