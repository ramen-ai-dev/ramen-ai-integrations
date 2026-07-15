"""Custom exceptions for the ramen-ai LangChain integration."""

from __future__ import annotations


class RamenSafetyException(Exception):
    """
    Raised by :class:`RamenSafetyCallbackHandler` when the ramen-ai firewall
    returns a BLOCKED verdict for a tool call.

    Raising this exception from inside ``on_tool_start`` propagates up through
    LangChain's callback machinery and halts the execution chain before the
    tool's ``_run`` / ``_arun`` method is invoked.

    Attributes
    ----------
    tool_name:
        The name of the tool that was blocked.
    steering:
        The deterministic, agent-facing recovery instruction returned by the
        ramen-ai API.  ``None`` if the API did not supply one.
    receipt_verified:
        Whether the Ed25519 V5 receipt was successfully verified locally.
    statutory_anchors:
        The regulatory provisions that grounded the block (e.g.
        ``["EU AI Act Art. 5(1)(a)"]``).  Empty list if none were reported.
    """

    def __init__(
        self,
        *,
        tool_name: str,
        steering: str | None,
        receipt_verified: bool,
        statutory_anchors: list[str],
    ) -> None:
        self.tool_name = tool_name
        self.steering = steering
        self.receipt_verified = receipt_verified
        self.statutory_anchors = statutory_anchors

        anchors_str = ", ".join(statutory_anchors) if statutory_anchors else "none reported"
        super().__init__(
            f"[BLOCKED] tool '{tool_name}' halted by ramen-ai firewall. "
            f"Statutory anchors: {anchors_str}. "
            f"Steering: {steering or '(none)'}. "
            f"Receipt verified (Ed25519): {receipt_verified}."
        )
