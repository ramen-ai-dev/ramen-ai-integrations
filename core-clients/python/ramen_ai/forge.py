"""RemoteForgeMemoryStore: HTTP client for ramen forge (level 1 community memory).

Python counterpart of ``@ramen-ai/node-core``'s ``RemoteForgeMemoryStore``. Field
names match the forge wire contract, so Python and TypeScript agents share one
record shape.

Reads (``GET /api/v1/exemplars``) are public and fail open: network errors,
timeouts, HTTP errors and malformed bodies are logged and return ``[]``, because
memory is advisory and the ramen-ai policy boundary still evaluates every call.
Treat recalled exemplars as untrusted guidance.

Writes (``POST /api/v1/exemplars``) require a write token and a complete Schema
V5 receipt whose signed verdict is ALLOW. ramen forge rejects records without
one, so they are skipped with a warning before any network call. Contributed
records are publicly readable.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any, Literal, TypedDict
from urllib.parse import urlencode, urlsplit

import httpx

from .constants import FORGE_DEFAULT_BASE_URL
from .verifier import AUDIT_PUBLIC_KEYS, sha256_hex, verify_allow_receipt_signature

_EXEMPLARS_PATH = "/api/v1/exemplars"
_MAX_LIMIT = 50
_MAX_QUERY_LENGTH = 100
_DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_SERVED_STRING_KEYS = (
    "exemplar_id",
    "domain",
    "task_description",
    "task_fingerprint",
    "tool_name",
    "violation_reason",
    "primary_statutory_anchor",
    "steering_directive",
    "created_at",
)

_default_logger = logging.getLogger("ramen_ai.forge")


class ForgeWriteError(RuntimeError):
    """A contribution failed: invalid receipt, missing token, transport or forge rejection."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class CorrectionExemplar(TypedDict):
    """An exemplar as served by ramen forge."""

    exemplar_id: str
    domain: str
    task_description: str
    task_fingerprint: str
    tool_name: str
    failed_arguments: dict[str, Any]
    violation_reason: str
    primary_statutory_anchor: str
    steering_directive: str
    repaired_arguments: dict[str, Any]
    receipt_id: str | None
    created_at: str


class RecordCorrectionResult(TypedDict, total=False):
    status: Literal["created", "refreshed", "duplicate", "skipped"]
    exemplar_id: str
    reason: str


def _is_served_exemplar(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        all(isinstance(value.get(key), str) and value[key] for key in _SERVED_STRING_KEYS)
        and isinstance(value.get("failed_arguments"), dict)
        and isinstance(value.get("repaired_arguments"), dict)
        and (value.get("receipt_id") is None or isinstance(value.get("receipt_id"), str))
    )


def _error_detail(body: Any) -> str:
    if not isinstance(body, dict):
        return "no response body"
    error = body.get("error")
    if isinstance(error, dict):
        detail = f"{error.get('code', 'error')}: {error.get('message', 'unknown error')}"
    else:
        detail = str(error if error is not None else "unknown error")
    details = body.get("details")
    if isinstance(details, list) and details:
        detail += ": " + "; ".join(str(item) for item in details[:5])
    return detail


class RemoteForgeMemoryStore:
    """Read and contribute correction exemplars on ramen forge."""

    def __init__(
        self,
        *,
        base_url: str = FORGE_DEFAULT_BASE_URL,
        write_token: str | None = None,
        domain: str = "general",
        timeout: float = 5.0,
        http_client: httpx.Client | None = None,
        public_keys: Mapping[str, str] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        parts = urlsplit(base_url)
        if parts.scheme != "https" and not (parts.scheme == "http" and parts.hostname in _LOCAL_HOSTS):
            raise ValueError("base_url must use https (http is allowed only for localhost)")
        if not isinstance(domain, str) or not _DOMAIN_RE.match(domain):
            raise ValueError("domain must be a lowercase slug (a-z, 0-9, '_' or '-', 2-64 characters)")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("timeout must be a positive number")
        self.base_url = base_url.rstrip("/")
        self.domain = domain
        self.timeout = float(timeout)
        self._write_token = write_token.strip() if write_token and write_token.strip() else None
        self._http = http_client if http_client is not None else httpx.Client()
        self._owns_http = http_client is None
        self._public_keys = AUDIT_PUBLIC_KEYS if public_keys is None else public_keys
        self._logger = logger or _default_logger

    @property
    def writable(self) -> bool:
        """True when a write token is configured. The token itself is never exposed."""
        return self._write_token is not None

    def __repr__(self) -> str:
        # Never include the write token.
        return (
            f"{type(self).__name__}(base_url={self.base_url!r}, domain={self.domain!r}, "
            f"writable={self.writable})"
        )

    def close(self) -> None:
        """Close the HTTP client if this store created it."""
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> RemoteForgeMemoryStore:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def retrieve_relevant_exemplars(
        self,
        *,
        domain: str | None = None,
        tool_name: str | None = None,
        query: str | None = None,
        task_fingerprint: str | None = None,
        limit: int = 3,
    ) -> list[CorrectionExemplar]:
        """Query ramen forge for exemplars. Every filter except the domain is optional.

        Invalid options raise ``ValueError`` before any network call. Everything
        after that fails open and returns ``[]``.
        """
        selected_domain = domain if domain is not None else self.domain
        if not isinstance(selected_domain, str) or not _DOMAIN_RE.match(selected_domain):
            raise ValueError("domain must be a lowercase slug")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= _MAX_LIMIT:
            raise ValueError(f"limit must be an integer between 1 and {_MAX_LIMIT}")
        params: dict[str, str] = {"domain": selected_domain, "limit": str(limit)}
        if tool_name is not None:
            if not isinstance(tool_name, str) or not tool_name.strip():
                raise ValueError("tool_name must be a non-blank string")
            params["tool_name"] = tool_name
        if task_fingerprint is not None:
            if not isinstance(task_fingerprint, str) or not _SHA256_HEX_RE.match(task_fingerprint):
                raise ValueError("task_fingerprint must be a lowercase SHA-256 hex digest")
            params["task_fingerprint"] = task_fingerprint
        if query is not None:
            stripped = query.strip() if isinstance(query, str) else ""
            if not stripped:
                raise ValueError("query must be a non-blank string")
            if len(stripped) > _MAX_QUERY_LENGTH:
                raise ValueError(f"query must be at most {_MAX_QUERY_LENGTH} characters")
            params["q"] = stripped

        try:
            response = self._http.get(
                f"{self.base_url}{_EXEMPLARS_PATH}",
                params=params,
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
            if not response.is_success:
                raise httpx.HTTPError(f"HTTP {response.status_code}")
            body = response.json()
        except (httpx.HTTPError, ValueError) as error:
            self._logger.warning("ramen forge retrieval failed; continuing without exemplars: %s", error)
            return []

        records = body.get("exemplars") if isinstance(body, dict) else None
        if not isinstance(records, list):
            self._logger.warning("ramen forge returned an unexpected response shape; ignoring it")
            return []
        exemplars: list[CorrectionExemplar] = []
        for record in records:
            if not _is_served_exemplar(record):
                self._logger.warning("skipping invalid ramen forge exemplar")
                continue
            # Fingerprints are deliberately not compared: a lesson for a differently
            # phrased task is still useful for the same tool and domain.
            if record["domain"] != selected_domain or (tool_name is not None and record["tool_name"] != tool_name):
                self._logger.warning(
                    "skipping ramen forge exemplar %s that does not match the query", record["exemplar_id"]
                )
                continue
            exemplars.append(record)  # type: ignore[arg-type]
        return exemplars[:limit]

    def record_correction(self, exemplar: Mapping[str, Any]) -> RecordCorrectionResult:
        """Contribute one exemplar.

        Requires a write token and a complete Schema V5 receipt whose Ed25519
        signature verifies and whose signed verdict is ALLOW. Returns
        ``{"status": "skipped", ...}`` without a network call when the exemplar
        has no receipt. Raises :class:`ForgeWriteError` for an invalid receipt, a
        missing token, a transport failure, or any forge rejection other than a
        duplicate id.
        """
        if not isinstance(exemplar, Mapping):
            raise ForgeWriteError("exemplar must be a mapping")
        receipt = exemplar.get("receipt")
        exemplar_id = str(exemplar.get("exemplar_id", ""))
        if receipt is None:
            reason = f"exemplar {exemplar_id} has no Schema V5 receipt; skipping ramen forge upload"
            self._logger.warning(reason)
            return {"status": "skipped", "reason": reason}
        if self._write_token is None:
            raise ForgeWriteError("RemoteForgeMemoryStore is read-only: no write_token configured")

        valid, reason_text = verify_allow_receipt_signature(receipt, public_keys=self._public_keys)
        if not valid:
            raise ForgeWriteError(f"receipt is not a verified ALLOW receipt: {reason_text}")
        receipt_id = exemplar.get("receipt_id")
        if receipt_id is not None and receipt_id != receipt.get("id"):
            raise ForgeWriteError("receipt_id does not match receipt.id")
        task_description = exemplar.get("task_description")
        if not isinstance(task_description, str) or not task_description.strip():
            raise ForgeWriteError("task_description must be a non-blank string")
        fingerprint = sha256_hex(task_description)
        supplied = exemplar.get("task_fingerprint")
        if supplied is not None and supplied != fingerprint:
            raise ForgeWriteError("task_fingerprint does not match SHA-256(task_description)")

        # Only the keys ramen forge accepts; unknown keys are rejected with 422.
        payload = {
            "exemplar_id": exemplar.get("exemplar_id"),
            "domain": exemplar.get("domain", self.domain),
            "task_description": task_description,
            "task_fingerprint": fingerprint,
            "tool_name": exemplar.get("tool_name"),
            "failed_arguments": exemplar.get("failed_arguments") or {},
            "violation_reason": exemplar.get("violation_reason"),
            "primary_statutory_anchor": exemplar.get("primary_statutory_anchor"),
            "steering_directive": exemplar.get("steering_directive"),
            "repaired_arguments": exemplar.get("repaired_arguments"),
            "receipt_id": receipt.get("id"),
            "receipt": receipt,
            "created_at": exemplar.get("created_at"),
        }
        try:
            response = self._http.post(
                f"{self.base_url}{_EXEMPLARS_PATH}",
                json=payload,
                headers={"Authorization": f"Bearer {self._write_token}", "Accept": "application/json"},
                timeout=self.timeout,
            )
        except httpx.HTTPError as error:
            raise ForgeWriteError(f"ramen forge write failed: {error}") from error

        try:
            body: Any = response.json()
        except ValueError:
            body = None
        if response.status_code == 409:
            self._logger.info("ramen forge already holds exemplar %s", exemplar_id)
            return {"status": "duplicate", "exemplar_id": exemplar_id}
        if response.status_code not in (200, 201):
            raise ForgeWriteError(
                f"ramen forge rejected exemplar {exemplar_id} "
                f"(HTTP {response.status_code}): {_error_detail(body)}",
                response.status_code,
            )
        stored_id = exemplar_id
        if isinstance(body, dict) and isinstance(body.get("exemplar_id"), str):
            stored_id = body["exemplar_id"]
        # 200 + refreshed: the same lesson was already stored; only its receipt was swapped.
        refreshed = isinstance(body, dict) and body.get("refreshed") is True
        return {"status": "refreshed" if refreshed else "created", "exemplar_id": stored_id}

    def audit_uri(self, exemplar: Mapping[str, Any]) -> str:
        """Filtered listing URL that returns a lesson together with its signature."""
        query = urlencode(
            {
                "domain": exemplar["domain"],
                "tool_name": exemplar["tool_name"],
                "task_fingerprint": exemplar["task_fingerprint"],
            }
        )
        return f"{self.base_url}{_EXEMPLARS_PATH}?{query}"


def build_provenance(
    *,
    domain: str,
    tool_name: str,
    receipt_id: str | None = None,
    exemplar: Mapping[str, Any] | None = None,
    store: RemoteForgeMemoryStore | None = None,
) -> dict[str, Any]:
    """Build the ``_ramen_provenance`` envelope for a governed tool outcome.

    Lesson fields are ``None`` when no exemplar is involved. ``audit_uri`` is set
    only for exemplars that came from (or were stored in) ramen forge.
    """
    return {
        "source": "ramen-forge" if store is not None else "ramen-local",
        "version": "1.0",
        "domain": domain,
        "tool_name": tool_name,
        "exemplar_id": exemplar.get("exemplar_id") if exemplar else None,
        "statutory_anchor": exemplar.get("primary_statutory_anchor") if exemplar else None,
        "receipt_id": receipt_id,
        "prevention_summary": exemplar.get("steering_directive") if exemplar else None,
        "audit_uri": store.audit_uri(exemplar) if exemplar and store is not None else None,
    }
