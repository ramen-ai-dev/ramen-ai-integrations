"""
ramen_ai.client — Synchronous HTTP client for the ramen-ai cloud API.

Usage
-----
    from ramen_ai import RamenClient

    client = RamenClient(api_key="ramen_ak_...")
    result = client.evaluate_compliance(
        input_text="Recommend the highest-commission product.",
        policy_ids=["1006492f-db62-4f46-8775-48b966c5c956"],
    )
    print(result["allowed"])          # False
    print(result["receipt_verified"]) # True
    print(result["steering"])         # "Reassess product suitability..."

The client calls :func:`ramen_ai.verifier.signed_verdict_problem` internally on
every response that carries a V5 receipt and surfaces the result. The signed
verdict, input hash, id, kid, timestamp, policy ids and anchors must all agree
with the response, so a genuine BLOCK receipt wrapped in ``allowed: true`` never
verifies. Pass ``require_verified_receipt=True`` to raise instead of returning
an unverified verdict.

Besides evaluation the client exposes ``client.memory`` (Enterprise Memory
Mesh), ``client.bundles`` (global bundle catalogue) and ``client.receipts``
(signed receipt ledger).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Literal

import httpx

from ._http import _invalid, error_from_response
from .errors import ReceiptVerificationError

from .governed import (
    generate_governed as _generate_governed,
    generate_governed_stream as _generate_governed_stream,
)
from .governed_types import (
    GovernedCompleteData,
    GovernedGenerationOptions,
    GovernedProviderName,
    GovernedStreamEvent,
)
from .memory_mesh import MemoryMeshApi
from .resources import BundlesApi, ReceiptsApi
from .types import AttestationPayload, ComplianceVerdict
from .verifier import AUDIT_PUBLIC_KEYS, VERDICT_ALLOW, VERDICT_BLOCK, signed_verdict_problem

_EVALUATE_PATH = "/api/v1/paas/evaluate"
_DEFAULT_BASE_URL = "https://api.ramenai.dev"
_DEFAULT_TIMEOUT = 30.0


class RamenClient:
    """
    Synchronous client for the ramen-ai PaaS evaluation API.

    Parameters
    ----------
    api_key:
        A ``ramen_ak_...`` bearer token issued by the ramen-ai platform.
    base_url:
        Override the API base URL (useful for staging / local testing).
    timeout:
        HTTP request timeout in seconds (default: 30).
    require_verified_receipt:
        Fail closed. When true, :meth:`evaluate_compliance` raises
        :class:`ramen_ai.ReceiptVerificationError` unless the response carries a
        receipt that verifies against its own signed verdict. Default: false.
    public_keys:
        Override the pinned receipt keys (for example with test vectors). The
        production key ``ramen_pk_v1`` is used by default.
    transport:
        A custom ``httpx`` transport, for proxies or tests. Default: httpx's own.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = _DEFAULT_TIMEOUT,
        require_verified_receipt: bool = False,
        public_keys: Mapping[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must be a non-empty string.")
        self._api_key = api_key
        self._require_verified_receipt = require_verified_receipt
        self._public_keys: Mapping[str, str] = AUDIT_PUBLIC_KEYS if public_keys is None else public_keys
        self._http = httpx.Client(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
            transport=transport,
        )
        #: Enterprise Memory Mesh (``/api/v1/memory/*``).
        self.memory = MemoryMeshApi(self._http)
        #: Global bundle catalogue (``GET /api/v1/safety/bundles``).
        self.bundles = BundlesApi(self._http)
        #: Signed receipt ledger (``GET /api/v1/paas/receipts``).
        self.receipts = ReceiptsApi(self._http)

    # ---------------------------------------------------------------------- #
    # Public API                                                               #
    # ---------------------------------------------------------------------- #

    def evaluate_compliance(
        self,
        input_text: str,
        *,
        bundle_ids: list[str] | None = None,
        policy_ids: list[str] | None = None,
        context: dict[str, str] | None = None,
        attestation: AttestationPayload | None = None,
        provider_key: str | None = None,
        provider_name: str | None = None,
    ) -> ComplianceVerdict:
        """
        Evaluate *input_text* against the specified policies or bundles.

        At least one of *bundle_ids* or *policy_ids* must be supplied.
        Both may be supplied simultaneously (the server merges them).

        Parameters
        ----------
        input_text:
            The text to evaluate (1–50 000 characters).
        bundle_ids:
            Pre-built bundle identifiers (e.g. ``"ramen__eu_ai_act_baseline"``).
        policy_ids:
            Explicit policy UUIDs to evaluate in parallel.
        context:
            Optional string-keyed metadata forwarded to the audit log.
        attestation:
            Optional vendor attestation payload forwarded with the evaluation.
        provider_key:
            BYOK — the caller's LLM provider API key (e.g. an OpenAI or
            Anthropic key). Required on Starter/Professional tiers; omit on
            Enterprise where managed keys are provisioned server-side. When
            present, forwarded as the ``X-Provider-Key`` HTTP header.
        provider_name:
            BYOK — the LLM provider to route inference to when *provider_key*
            is supplied. Accepted values: ``"openai"`` (default),
            ``"anthropic"``, ``"google"``, ``"synthetic"``, ``"hyperbolic"``.
            Forwarded as the ``X-Provider`` HTTP header. Has no effect when
            *provider_key* is absent.

        Returns
        -------
        A dict with the following keys:

        ``allowed`` (bool)
            The compliance verdict from the server.
        ``receipt_verified`` (bool)
            ``True`` only if a V5 receipt was present *and* its signature
            verifies, its signed verdict equals ``allowed``, and the signed
            input hash, id, kid, timestamp, policy ids and anchors all match.
        ``receipt_valid`` (bool | None)
            Raw result of :func:`verify_receipt`; ``None`` if no receipt
            was present.
        ``receipt_reason`` (str | None)
            Human-readable reason for a verification failure; ``None`` on
            success or when no receipt was present.
        ``receipt_alert`` (str | None)
            Populated when the server could not sign the receipt (signing
            infrastructure failure).  The verdict remains valid but there
            is no cryptographic proof.
        ``steering`` (str | None)
            Pipe-joined ``recovery_instruction`` strings from all blocking
            violations, plus any ``instruction`` from gentle-hand policies.
            ``None`` when the input was allowed.
        ``policy_ids`` (list[str])
            Resolved, flat list of policy UUIDs that were actually evaluated
            and signed (important for bundle callers).
        ``data`` (dict)
            The full ``EvaluationResponse`` payload for downstream use.

        Raises
        ------
        ValueError
            If neither *bundle_ids* nor *policy_ids* is provided.
        ramen_ai.RamenApiError
            On 4xx / 5xx HTTP responses, or a body that is not JSON. It subclasses
            ``httpx.HTTPStatusError``. Transport failures propagate as
            ``httpx.TransportError``.
        ramen_ai.ReceiptVerificationError
            If ``require_verified_receipt`` is set and the receipt does not verify.
        """
        if not bundle_ids and not policy_ids:
            raise ValueError(
                "Provide at least one of 'bundle_ids' or 'policy_ids'."
            )

        body: dict[str, Any] = {"input": input_text}
        if bundle_ids:
            body["bundle_ids"] = bundle_ids
        if policy_ids:
            body["policy_ids"] = policy_ids
        if context:
            body["context"] = context
        if attestation is not None:
            body["attestation"] = attestation

        # BYOK: inject per-request provider headers when present.
        # X-Provider-Key is required on Starter/Professional tiers.
        # X-Provider selects the inference backend (default: openai).
        # These are passed as request-level overrides rather than shared
        # client headers so one caller's key never bleeds into another's request.
        extra_headers: dict[str, str] = {}
        if provider_key:
            extra_headers["X-Provider-Key"] = provider_key
            if provider_name:
                extra_headers["X-Provider"] = provider_name

        response = self._http.post(
            _EVALUATE_PATH, json=body, headers=extra_headers if extra_headers else None
        )
        if not response.is_success:
            raise error_from_response(response, prefix="evaluate failed")
        try:
            envelope: Any = response.json()
        except ValueError as error:
            raise _invalid(response, "evaluate response was not valid JSON") from error
        if not isinstance(envelope, dict):
            raise _invalid(response, "evaluate response was not a JSON object")
        data: dict[str, Any] = envelope.get("data") or {}

        allowed: bool = data.get("allowed", False)
        resolved_policy_ids: list[str] = data.get("policy_ids", [])
        executed_at: str = data.get("executed_at", "")
        total_violations: list[dict[str, Any]] = data.get("total_violations", [])
        results: list[dict[str, Any]] = data.get("results", [])
        statutory_anchors: list[str] | None = data.get("statutory_anchors")
        receipt: dict[str, Any] | None = data.get("receipt")
        receipt_alert: str | None = data.get("receipt_alert")

        # ------------------------------------------------------------------ #
        # Cryptographic verification                                           #
        # ------------------------------------------------------------------ #
        receipt_valid: bool | None = None
        receipt_reason: str | None = None

        if receipt and receipt.get("canonical_payload"):
            # The signed verdict must match the response's own ``allowed``, and
            # the signed timestamp, policy ids and anchors must match the response.
            receipt_reason = signed_verdict_problem(
                receipt,
                input_text,
                VERDICT_ALLOW if allowed is True else VERDICT_BLOCK,
                public_keys=self._public_keys,
                binding={
                    "executed_at": executed_at,
                    "policy_ids": resolved_policy_ids,
                    "statutory_anchors": statutory_anchors,
                },
            )
            receipt_valid = receipt_reason is None

        receipt_verified: bool = receipt_valid is True

        # ------------------------------------------------------------------ #
        # Steering string — pipe-join all host-agent recovery directives.      #
        # ------------------------------------------------------------------ #
        steering_parts: list[str] = []

        for v in total_violations:
            instr = v.get("recovery_instruction")
            if instr:
                steering_parts.append(instr)

        for r in results:
            instr = r.get("instruction")
            if instr:
                steering_parts.append(instr)

        steering: str | None = " | ".join(steering_parts) if steering_parts else None

        verdict: ComplianceVerdict = {
            "allowed": allowed,
            "receipt_verified": receipt_verified,
            "receipt_valid": receipt_valid,
            "receipt_reason": receipt_reason,
            "receipt_alert": receipt_alert,
            "steering": steering,
            "policy_ids": resolved_policy_ids,
            "data": data,  # type: ignore[typeddict-item]
        }
        if self._require_verified_receipt and not receipt_verified:
            raise ReceiptVerificationError(
                receipt_reason or receipt_alert or "No Schema V5 receipt was returned.",
                verdict,
            )
        return verdict

    def generate_governed(
        self,
        prompt: str,
        *,
        policy_ids: Sequence[str] | None = None,
        bundle_ids: Sequence[str] | None = None,
        max_retries: Literal[0, 1] = 1,
        generation: GovernedGenerationOptions | None = None,
        expose_healing_trail: bool = False,
        provider_key: str | None = None,
        provider_name: GovernedProviderName | None = None,
    ) -> GovernedCompleteData:
        """Generate content and return it only after strict governance approval."""
        return _generate_governed(
            self._http,
            prompt,
            policy_ids=policy_ids,
            bundle_ids=bundle_ids,
            max_retries=max_retries,
            generation=generation,
            expose_healing_trail=expose_healing_trail,
            provider_key=provider_key,
            provider_name=provider_name,
        )

    def generate_governed_stream(
        self,
        prompt: str,
        *,
        policy_ids: Sequence[str] | None = None,
        bundle_ids: Sequence[str] | None = None,
        max_retries: Literal[0, 1] = 1,
        generation: GovernedGenerationOptions | None = None,
        expose_healing_trail: bool = False,
        provider_key: str | None = None,
        provider_name: GovernedProviderName | None = None,
    ) -> Iterator[GovernedStreamEvent]:
        """Stream governed progress and the successful terminal event."""
        return _generate_governed_stream(
            self._http,
            prompt,
            policy_ids=policy_ids,
            bundle_ids=bundle_ids,
            max_retries=max_retries,
            generation=generation,
            expose_healing_trail=expose_healing_trail,
            provider_key=provider_key,
            provider_name=provider_name,
        )

    # ---------------------------------------------------------------------- #
    # Context-manager support                                                  #
    # ---------------------------------------------------------------------- #

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._http.close()

    def __enter__(self) -> RamenClient:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
