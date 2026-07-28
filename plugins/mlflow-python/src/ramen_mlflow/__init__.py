"""
ramen-ai MLflow integration — algorithmic governance for classical ML.

Wraps an MLflow pyfunc model so every inference request is evaluated against
ramen-ai compliance policies before the wrapped model runs. Feature values (and
SHAP attributions where available) are serialised and submitted to the ramen-ai
evaluation API; a BLOCKED verdict raises :exc:`GovernanceDeniedException` and the
wrapped model is never invoked.

Quick start::

    import mlflow
    from ramen_mlflow import RamenGovernedModel

    governed = RamenGovernedModel(
        bundle_ids=["ramen__eu_ai_act_baseline"],
        inner_model=sklearn_model,
        model_name="credit-risk-scorer-v3",
    )

    mlflow.pyfunc.log_model(name="governed-model", python_model=governed)

The ramen-ai API key is read from ``RAMEN_API_KEY`` in the serving environment
at call time and is never serialised into the model artifact.
"""

from .exceptions import GovernanceDeniedException
from .wrapper import RamenGovernedModel

__all__ = ["RamenGovernedModel", "GovernanceDeniedException"]
__version__ = "0.1.0"
