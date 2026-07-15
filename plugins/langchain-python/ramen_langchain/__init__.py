"""
ramen-ai LangChain integration — L2 Semantic Firewall callback handler.

Intercepts tool calls pre-execution, evaluates the serialized tool definition
and input against the ramen-ai PaaS evaluation API, and raises
:exc:`RamenSafetyException` to halt the LangChain execution chain on a
BLOCKED verdict.

Quick start::

    from ramen_langchain import RamenSafetyCallbackHandler, RamenSafetyException

    handler = RamenSafetyCallbackHandler(
        api_key=os.environ["RAMEN_API_KEY"],
        bundle_ids=["ramen__shield_core_it"],
        provider_key=os.environ.get("OPENAI_API_KEY"),  # BYOK: Starter/Pro tiers
    )
    agent_executor.invoke({"input": prompt}, config={"callbacks": [handler]})
"""

from .exceptions import RamenSafetyException
from .handler import RamenSafetyCallbackHandler

__all__ = ["RamenSafetyCallbackHandler", "RamenSafetyException"]
__version__ = "0.1.0"
