"""Custom exceptions for the ramen-ai MLflow integration."""

from __future__ import annotations

from typing import Any


class GovernanceDeniedException(RuntimeError):
    """
    Raised by :class:`~ramen_mlflow.wrapper.RamenGovernedModel` when the
    ramen-ai firewall returns a BLOCKED verdict for an inference request.

    Inherits from ``RuntimeError`` so it propagates out of
    ``mlflow.pyfunc.PythonModel.predict`` and halts the serving request.
    MLflow Model Serving surfaces this as a 500 with the exception message,
    which is the intended behaviour: a governance block is a hard stop, not a
    recoverable prediction failure.

    Attributes
    ----------
    steering:
        The deterministic recovery instruction returned by the ramen-ai API.
        ``None`` if the API did not supply one.
    receipt_verified:
        Whether the V5 Ed25519 receipt was verified locally. ``False`` when no
        receipt was present or verification failed.
    statutory_anchors:
        Regulatory provisions grounding the block (e.g.
        ``["EU AI Act Art. 10", "GDPR Art. 22"]``). Empty list if none.
    policy_ids:
        Resolved policy UUIDs that were evaluated.
    receipt:
        The raw V5 receipt dict, for audit logging. ``None`` if unsigned.
    """

    def __init__(
        self,
        *,
        steering: str | None,
        receipt_verified: bool,
        statutory_anchors: list[str],
        policy_ids: list[str] | None = None,
        receipt: dict[str, Any] | None = None,
    ) -> None:
        self.steering = steering
        self.receipt_verified = receipt_verified
        self.statutory_anchors = statutory_anchors
        self.policy_ids = policy_ids or []
        self.receipt = receipt

        anchors_str = ", ".join(statutory_anchors) if statutory_anchors else "none reported"
        super().__init__(
            f"[BLOCKED] inference halted by ramen-ai algorithmic governance. "
            f"Statutory anchors: {anchors_str}. "
            f"Steering: {steering or '(none)'}. "
            f"Receipt verified (Ed25519): {receipt_verified}."
        )
