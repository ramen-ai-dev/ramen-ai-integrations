"""
ramen_pydantic.middleware — PydanticAI args_validator firewall middleware.

Architecture note
-----------------
PydanticAI offers two tool-level interception hooks:

``prepare`` — fires before each agent step to decide whether to offer a tool
to the model at all.  Signature: ``(ctx, tool_def) -> ToolDefinition | None``.
It does **not** receive the call arguments and cannot inspect what the model
actually wants to do.

``args_validator`` — fires after the LLM has chosen a tool and PydanticAI has
schema-validated the arguments, but before the tool function is called.
Signature: ``(ctx: RunContext[T], **args_dict) -> None``.  This is the correct
interception point: the validator sees the real, typed call arguments and can
halt execution by raising.

This module uses ``args_validator``.  The ramen-ai evaluation payload is built
from ``ctx.tool_name`` (the tool being called) plus the full ``args_dict`` so
the evaluator has maximum context.

Fail-closed behaviour
---------------------
Any exception during the HTTP evaluation (network error, timeout, 4xx/5xx,
parse error) is caught and re-raised as :exc:`.exceptions.RamenSafetyException`
with the original exception as ``__cause__``.  An unreachable firewall must
never silently allow a call through.

Usage
-----
``ramen_firewall()`` returns a ready-to-use ``args_validator`` function::

    from ramen_pydantic import ramen_firewall, RamenSafetyException

    firewall = ramen_firewall(
        api_key=os.environ["RAMEN_API_KEY"],
        bundle_ids=["ramen__shield_core_it"],
        provider_key=os.environ.get("OPENAI_API_KEY"),
    )

    @agent.tool(args_validator=firewall)
    def drop_database_table(ctx: RunContext[None], table_name: str) -> str:
        return f"dropped {table_name}"

    # Or with the Tool() constructor:
    Tool(drop_database_table, args_validator=firewall)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from pydantic_ai import RunContext

from ramen_ai import RamenClient

from .exceptions import RamenSafetyException

logger = logging.getLogger(__name__)


def ramen_firewall(
    *,
    api_key: str,
    bundle_ids: list[str] | None = None,
    policy_ids: list[str] | None = None,
    provider_key: str | None = None,
    base_url: str | None = None,
    timeout: float = 30.0,
    require_receipt_verified: bool = True,
    context: dict[str, str] | None = None,
) -> Any:
    """
    Return an ``args_validator`` function that intercepts PydanticAI tool calls
    and evaluates them against the ramen-ai L2 Semantic Firewall.

    The returned function matches PydanticAI's ``ArgsValidatorFunc`` type alias
    and can be passed directly to ``@agent.tool(args_validator=...)`` or
    ``Tool(func, args_validator=...)``.

    Parameters
    ----------
    api_key:
        ramen-ai bearer token (``ramen_ak_...``).  Load from the environment.
    bundle_ids:
        Pre-built bundle slugs (e.g. ``["ramen__shield_core_it"]``).
    policy_ids:
        Explicit policy UUIDs.  At least one of *bundle_ids* or *policy_ids*
        must be non-empty.
    provider_key:
        BYOK — your LLM provider API key (OpenAI, Anthropic, etc.).  Required
        on Starter / Professional tiers; forwarded as ``X-Provider-Key``.
    base_url:
        Override the ramen-ai API base URL (for staging / local testing).
    timeout:
        HTTP request timeout in seconds (default: 30).
    require_receipt_verified:
        When ``True`` (default), an ALLOWED verdict whose Ed25519 receipt
        cannot be locally verified is escalated to a BLOCK (fail-closed on
        evidence).
    context:
        Optional string-keyed metadata forwarded to the audit log on every
        evaluation request.

    Returns
    -------
    An async ``args_validator`` callable:
    ``async (ctx: RunContext[Any], **args_dict: Any) -> None``

    Raises
    ------
    ValueError
        If neither *bundle_ids* nor *policy_ids* is supplied.

    Example
    -------
    ::

        firewall = ramen_firewall(
            api_key=os.environ["RAMEN_API_KEY"],
            bundle_ids=["ramen__shield_core_it"],
        )

        @agent.tool(args_validator=firewall)
        async def send_funds(ctx: RunContext[None], to: str, amount: int) -> str:
            ...
    """
    if not bundle_ids and not policy_ids:
        raise ValueError(
            "ramen_firewall() requires at least one of 'bundle_ids' or 'policy_ids'."
        )

    client_kwargs: dict[str, Any] = {"api_key": api_key, "timeout": timeout}
    if base_url:
        client_kwargs["base_url"] = base_url
    if provider_key:
        client_kwargs["provider_key"] = provider_key

    client = RamenClient(**client_kwargs)
    _bundle_ids = list(bundle_ids) if bundle_ids else []
    _policy_ids = list(policy_ids) if policy_ids else []
    _context: dict[str, str] = dict(context) if context else {}

    async def _args_validator(ctx: RunContext[Any], **args_dict: Any) -> None:
        """ramen-ai firewall args_validator — intercepts the tool call pre-execution."""
        # ctx.tool_name is set by PydanticAI's run context at call time.
        tool_name: str = ctx.tool_name or "unknown_tool"

        # Build the evaluation payload: tool name + all resolved call arguments.
        payload: dict[str, Any] = {"tool": tool_name, "args": args_dict}
        payload_json = json.dumps(payload, ensure_ascii=False)

        logger.debug(
            "ramen-ai: evaluating tool call '%s' (run_id=%s)", tool_name, ctx.run_id
        )

        try:
            result = await asyncio.to_thread(
                client.evaluate_compliance,
                payload_json,
                bundle_ids=_bundle_ids or None,
                policy_ids=_policy_ids or None,
                context={
                    **_context,
                    "tool_name": tool_name,
                    **({"run_id": str(ctx.run_id)} if ctx.run_id else {}),
                },
            )
        except Exception as exc:
            # Fail-closed: any infrastructure failure is treated as a BLOCK.
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

        # Fail-closed on evidence: ALLOWED verdict + unverifiable receipt → BLOCK
        # when require_receipt_verified=True.
        receipt_present = result.get("receipt_valid") is not None
        evidence_block = (
            allowed
            and receipt_present
            and not receipt_verified
            and require_receipt_verified
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

    return _args_validator
