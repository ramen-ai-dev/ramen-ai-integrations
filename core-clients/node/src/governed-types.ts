/** Typed contracts for governed generation requests, responses, and SSE events. */

export type GovernedProviderName =
  | "openai"
  | "anthropic"
  | "google"
  | "synthetic"
  | "hyperbolic";

export interface GovernedGenerationOptions {
  temperature?: number;
  maxTokens?: number;
}

export interface GenerateGovernedOptions {
  policyIds?: readonly string[];
  bundleIds?: readonly string[];
  maxRetries?: 0 | 1;
  generation?: GovernedGenerationOptions;
  exposeHealingTrail?: boolean;
}

export interface GovernedGenerateWireRequest {
  prompt: string;
  policy_ids?: string[];
  bundle_ids?: string[];
  max_retries: 0 | 1;
  generation?: {
    temperature?: number;
    max_tokens?: number;
  };
  expose_healing_trail?: boolean;
}

export interface GovernedTokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface GovernedAttemptMetadata {
  attempt: number;
  provider: string;
  model: string;
  generation_duration_ms: number;
  evaluation_duration_ms: number;
  policies_evaluated: number;
  allowed: boolean;
  usage?: GovernedTokenUsage;
  rejected_content?: string;
  steering_rationale?: string[];
}

export interface GovernedAccounting {
  generation_attempts: number;
  evaluation_batches: number;
  policy_evaluations: number;
}

export interface GovernedEvaluationSummary {
  allowed: boolean;
  policy_ids: string[];
  policies_evaluated: number;
  policies_passed: number;
  policies_failed: number;
  policies_errored: number;
  violation_count: number;
  statutory_anchors: string[];
  receipt_id?: string;
}

export interface GovernedCompleteData {
  content: string;
  provider: string;
  model: string;
  usage?: GovernedTokenUsage;
  attempts: number;
  attempt_metadata: GovernedAttemptMetadata[];
  evaluation: GovernedEvaluationSummary;
  accounting: GovernedAccounting;
  total_duration_ms: number;
}

export interface GovernedBlockedData {
  attempts: number;
  attempt_metadata: GovernedAttemptMetadata[];
  evaluation: GovernedEvaluationSummary;
  accounting: GovernedAccounting;
  total_duration_ms: number;
}

export type GovernedStatusStage =
  | "accepted"
  | "generating"
  | "evaluating"
  | "scrubbing"
  | "regenerating";

export interface GovernedStatusEvent {
  event: "status";
  data: {
    stage: GovernedStatusStage;
    attempt: number;
    violations?: number;
  };
}

export interface GovernedHeartbeatEvent {
  event: "heartbeat";
  data: {
    timestamp: string;
  };
}

export interface GovernedCompleteEvent {
  event: "complete";
  data: {
    success: true;
    data: GovernedCompleteData;
  };
}

export type GovernedStreamEvent =
  | GovernedStatusEvent
  | GovernedHeartbeatEvent
  | GovernedCompleteEvent;
