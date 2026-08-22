from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from ramen_ai import RamenClient

from .constants import DEFAULT_BASE_URL, POLICY_UUID


class EvaluationTransport(Protocol):
    def evaluate_compliance(
        self,
        input_text: str,
        *,
        policy_ids: list[str],
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class VerifiedEvaluation:
    allowed: bool
    policy_ids: tuple[str, ...]
    receipt_id: str
    violations: tuple[dict[str, Any], ...]
    data: dict[str, Any]


class EvaluationFailure(RuntimeError):
    """Raised when a live evaluation cannot establish a trusted result."""


class MunicipalWaterPolicyClient:
    def __init__(self, transport: EvaluationTransport) -> None:
        self._transport = transport

    @classmethod
    def from_environment(cls) -> "MunicipalWaterPolicyClient":
        api_key = os.environ.get("RAMEN_API_KEY", "").strip()
        base_url = os.environ.get("RAMEN_API_BASE_URL", DEFAULT_BASE_URL).strip()
        if not api_key or api_key == "ramen_ak_...":
            raise EvaluationFailure("RAMEN_API_KEY is not configured")
        if base_url != DEFAULT_BASE_URL:
            raise EvaluationFailure(
                f"This production example requires {DEFAULT_BASE_URL}"
            )
        return cls(RamenClient(api_key=api_key, base_url=base_url))

    def evaluate(self, rendered_input: str) -> VerifiedEvaluation:
        try:
            result = self._transport.evaluate_compliance(
                rendered_input,
                policy_ids=[POLICY_UUID],
            )
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            raise EvaluationFailure(f"Policy evaluation failed: {exc}") from exc

        policy_ids = result.get("policy_ids")
        if not isinstance(policy_ids, list) or policy_ids.count(POLICY_UUID) != 1:
            raise EvaluationFailure("Receipt did not resolve the required policy exactly once")
        if result.get("receipt_alert"):
            raise EvaluationFailure("Evaluation returned an unsigned-receipt alert")
        if result.get("receipt_verified") is not True:
            reason = result.get("receipt_reason") or "receipt was absent or invalid"
            raise EvaluationFailure(f"Receipt verification failed: {reason}")

        data = result.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("allowed"), bool):
            raise EvaluationFailure("Evaluation response lacks an explicit boolean verdict")
        receipt = data.get("receipt")
        if not isinstance(receipt, dict) or not isinstance(receipt.get("id"), str):
            raise EvaluationFailure("Evaluation response lacks a receipt identifier")
        violations = data.get("total_violations", [])
        if not isinstance(violations, list):
            raise EvaluationFailure("Evaluation violations are malformed")

        return VerifiedEvaluation(
            allowed=data["allowed"],
            policy_ids=tuple(policy_ids),
            receipt_id=receipt["id"],
            violations=tuple(violations),
            data=data,
        )
