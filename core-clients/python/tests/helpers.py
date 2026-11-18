"""Shared test helpers (generated Ed25519 signer, recording transport)."""
from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable
from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from ramen_ai import RamenClient

POLICY_ID = "1006492f-db62-4f46-8775-48b966c5c956"
RECEIPT_ID = "b1d9c3e0-7a52-4f8c-9e21-0c4a6f7b2d18"
EXECUTED_AT = "2026-06-18T15:00:00.000Z"
ANCHORS = ["FCA PRIN 2A.2.8"]


class Signer:
    """A throwaway Ed25519 key registered under *kid*."""

    def __init__(self, kid: str = "ramen_pk_v1") -> None:
        self.kid = kid
        self._private = Ed25519PrivateKey.generate()
        der = self._private.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
        self.keys = {kid: base64.b64encode(der).decode("ascii")}

    def receipt(
        self,
        input_text: str,
        *,
        verdict: int,
        payload: dict[str, Any] | None = None,
        receipt: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Sign a receipt. *payload* overrides signed fields; *receipt* overrides unsigned ones."""
        signed = {
            "schema_version": "5.0",
            "kid": self.kid,
            "id": RECEIPT_ID,
            "timestamp": EXECUTED_AT,
            "policy_ids": [POLICY_ID],
            "payload_hash": hashlib.sha256(input_text.encode("utf-8")).hexdigest(),
            "verdict": verdict,
            "reasoning": "",
            "steering": "",
            "statutory_anchors": list(ANCHORS),
            **(payload or {}),
        }
        canonical = json.dumps(signed, separators=(",", ":"))
        signature = base64.urlsafe_b64encode(self._private.sign(canonical.encode("utf-8"))).rstrip(b"=")
        return {
            "id": RECEIPT_ID,
            "schema_version": "5.0",
            "kid": self.kid,
            "signature": signature.decode("ascii"),
            "canonical_payload": canonical,
            "statutory_anchors": list(ANCHORS),
            **(receipt or {}),
        }


def evaluation_data(allowed: bool, receipt: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "allowed": allowed,
        "policy_ids": [POLICY_ID],
        "policies_evaluated": 1,
        "policies_passed": 1 if allowed else 0,
        "policies_failed": 0 if allowed else 1,
        "policies_errored": 0,
        "total_violations": [],
        "results": [],
        "execution_time_ms": 3,
        "executed_at": EXECUTED_AT,
        "statutory_anchors": list(ANCHORS),
    }
    if receipt is not None:
        data["receipt"] = receipt
    data.update(extra)
    return data


class Recorder:
    """Collects the requests a client sends and answers each from *handler*."""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self.requests: list[httpx.Request] = []
        self._handler = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._handler(request)

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    def body(self, index: int = -1) -> Any:
        return json.loads(self.requests[index].content)


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
    **options: Any,
) -> tuple[RamenClient, Recorder]:
    recorder = Recorder(handler)
    client = RamenClient(api_key="ramen_ak_test", transport=httpx.MockTransport(recorder), **options)
    return client, recorder


def ok(data: Any, status: int = 200) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _request: httpx.Response(status, json={"success": True, "data": data})
