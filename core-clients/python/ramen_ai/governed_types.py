"""Typed contracts for governed generation requests, responses, and SSE events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

GovernedProviderName: TypeAlias = Literal[
    "openai",
    "anthropic",
    "google",
    "synthetic",
    "hyperbolic",
]
GovernedStatusStage: TypeAlias = Literal[
    "accepted",
    "generating",
    "evaluating",
    "regenerating",
]


@dataclass(frozen=True, slots=True)
class GovernedGenerationOptions:
    """Optional provider generation controls."""

    temperature: float | None = None
    max_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class GovernedTokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class GovernedAttemptMetadata:
    attempt: int
    provider: str
    model: str
    generation_duration_ms: int
    evaluation_duration_ms: int
    policies_evaluated: int
    allowed: bool
    usage: GovernedTokenUsage | None = None
    rejected_content: str | None = None
    steering_rationale: list[str] | None = None


@dataclass(frozen=True, slots=True)
class GovernedAccounting:
    generation_attempts: int
    evaluation_batches: int
    policy_evaluations: int


@dataclass(frozen=True, slots=True)
class GovernedEvaluationSummary:
    allowed: bool
    policy_ids: tuple[str, ...]
    policies_evaluated: int
    policies_passed: int
    policies_failed: int
    policies_errored: int
    violation_count: int
    statutory_anchors: tuple[str, ...]
    receipt_id: str | None = None


@dataclass(frozen=True, slots=True)
class GovernedCompleteData:
    content: str
    provider: str
    model: str
    attempts: int
    attempt_metadata: tuple[GovernedAttemptMetadata, ...]
    evaluation: GovernedEvaluationSummary
    accounting: GovernedAccounting
    total_duration_ms: int
    usage: GovernedTokenUsage | None = None


@dataclass(frozen=True, slots=True)
class GovernedBlockedData:
    attempts: int
    attempt_metadata: tuple[GovernedAttemptMetadata, ...]
    evaluation: GovernedEvaluationSummary
    accounting: GovernedAccounting
    total_duration_ms: int


@dataclass(frozen=True, slots=True)
class GovernedStatusData:
    stage: GovernedStatusStage
    attempt: int
    violations: int | None = None


@dataclass(frozen=True, slots=True)
class GovernedHeartbeatData:
    timestamp: str


@dataclass(frozen=True, slots=True)
class GovernedStatusEvent:
    event: Literal["status"]
    data: GovernedStatusData


@dataclass(frozen=True, slots=True)
class GovernedHeartbeatEvent:
    event: Literal["heartbeat"]
    data: GovernedHeartbeatData


@dataclass(frozen=True, slots=True)
class GovernedCompleteEnvelope:
    success: Literal[True]
    data: GovernedCompleteData


@dataclass(frozen=True, slots=True)
class GovernedCompleteEvent:
    event: Literal["complete"]
    data: GovernedCompleteEnvelope


GovernedStreamEvent: TypeAlias = (
    GovernedStatusEvent | GovernedHeartbeatEvent | GovernedCompleteEvent
)
