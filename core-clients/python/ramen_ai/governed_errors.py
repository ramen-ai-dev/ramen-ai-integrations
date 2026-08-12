"""Exceptions raised by governed generation methods."""

from __future__ import annotations

from typing import Any, Literal

from .governed_types import GovernedBlockedData


class GovernedGenerationException(Exception):
    """A governed-generation transport, API, or stream protocol failure."""

    def __init__(
        self,
        status: int | None,
        code: str,
        message: str,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.details = details


class GovernanceDeniedException(GovernedGenerationException):
    """No compliant output was produced within the governed retry limit."""

    status: Literal[422] = 422
    code: Literal["GOVERNED_OUTPUT_BLOCKED"] = "GOVERNED_OUTPUT_BLOCKED"

    def __init__(self, message: str, data: GovernedBlockedData) -> None:
        super().__init__(self.status, self.code, message, data)
        self.data = data
