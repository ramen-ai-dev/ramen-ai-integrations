"""
ramen-ai PydanticAI integration — L2 Semantic Firewall args_validator middleware.

Intercepts PydanticAI tool calls pre-execution via the native ``args_validator``
hook, evaluates the tool name and arguments against the ramen-ai PaaS evaluation
API, and raises :exc:`RamenSafetyException` to halt the agent run on a BLOCKED
verdict.

Quick start::

    import os
    from pydantic_ai import Agent, RunContext
    from ramen_pydantic import ramen_firewall, RamenSafetyException

    firewall = ramen_firewall(
        api_key=os.environ["RAMEN_API_KEY"],
        bundle_ids=["ramen__shield_core_it"],
        provider_key=os.environ.get("OPENAI_API_KEY"),  # BYOK: Starter/Pro tiers
    )

    agent = Agent("openai:gpt-4o-mini")

    @agent.tool(args_validator=firewall)
    def fetch_docs(ctx: RunContext[None], query: str) -> str:
        return f"docs for {query}"
"""

from .exceptions import RamenSafetyException
from .middleware import ramen_firewall

__all__ = ["ramen_firewall", "RamenSafetyException"]
__version__ = "0.1.0"
