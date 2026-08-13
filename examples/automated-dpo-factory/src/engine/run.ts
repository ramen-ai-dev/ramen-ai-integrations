import { buildScenarioPrompt, demoConfig } from "../shared/content";
import {
  publicConfigResponseSchema,
  sessionResponseSchema,
  type DemoScenario,
  type DpoRecord,
  type GovernedBlockedData,
  type GovernedCompleteData,
  type GovernedStreamEvent,
} from "../shared/schemas";
import { isEventStreamContentType, parseSseStream } from "../shared/sse";

export type RunMode = "guided" | "live";
export type SessionState = { expiresAt: string };
export type PublicConfig = { turnstileSiteKey: string; turnstileAction: string; burstLimit: number; burstWindowSeconds: number };

const wait = (milliseconds: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException("Run cancelled", "AbortError"));
    const timer = window.setTimeout(resolve, milliseconds);
    signal?.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timer);
        reject(new DOMException("Run cancelled", "AbortError"));
      },
      { once: true },
    );
  });

function evaluation(allowed: boolean, violations: number) {
  return {
    allowed,
    policy_ids: [...demoConfig.governance.policyIds],
    policies_evaluated: demoConfig.governance.policyIds.length,
    policies_passed: allowed ? demoConfig.governance.policyIds.length : 0,
    policies_failed: allowed ? 0 : demoConfig.governance.policyIds.length,
    policies_errored: 0,
    violation_count: violations,
    statutory_anchors: [] as string[],
  };
}

function attempt(
  attemptNumber: number,
  allowed: boolean,
  rejectedContent?: string,
  steeringRationale?: string[],
) {
  return {
    attempt: attemptNumber,
    provider: "guided-fixture",
    model: "configured-showcase",
    generation_duration_ms: 760 + attemptNumber * 81,
    evaluation_duration_ms: 142 + attemptNumber * 17,
    policies_evaluated: demoConfig.governance.policyIds.length,
    allowed,
    ...(rejectedContent ? { rejected_content: rejectedContent } : {}),
    ...(steeringRationale?.length ? { steering_rationale: steeringRationale } : {}),
  };
}

export async function* runGuidedScenario(
  scenario: DemoScenario,
  signal?: AbortSignal,
): AsyncGenerator<GovernedStreamEvent> {
  const path = scenario.expectedPath;
  yield { event: "status", data: { stage: "accepted", attempt: 0 } };
  await wait(320, signal);
  yield { event: "status", data: { stage: "generating", attempt: 0 } };
  await wait(520, signal);
  yield { event: "status", data: { stage: "evaluating", attempt: 0 } };
  await wait(420, signal);

  if (path === "pass") {
    const data: GovernedCompleteData = {
      content: scenario.guided.approvedContent ?? "",
      provider: "guided-fixture",
      model: "configured-showcase",
      attempts: 1,
      attempt_metadata: [attempt(0, true)],
      evaluation: evaluation(true, 0),
      accounting: { generation_attempts: 1, evaluation_batches: 1, policy_evaluations: 1 },
      total_duration_ms: 1_422,
    };
    yield { event: "complete", data: { success: true, data } };
    return;
  }

  yield { event: "status", data: { stage: "evaluating", attempt: 0, violations: 1 } };
  await wait(360, signal);
  yield { event: "status", data: { stage: "regenerating", attempt: 1 } };
  await wait(540, signal);
  yield { event: "status", data: { stage: "evaluating", attempt: 1 } };
  await wait(420, signal);

  const firstAttempt = attempt(
    0,
    false,
    scenario.guided.rejectedContent,
    scenario.guided.steeringRationale,
  );
  if (path === "block") {
    const data: GovernedBlockedData = {
      attempts: 2,
      attempt_metadata: [firstAttempt, attempt(1, false)],
      evaluation: evaluation(false, 1),
      accounting: { generation_attempts: 2, evaluation_batches: 2, policy_evaluations: 2 },
      total_duration_ms: 2_681,
    };
    yield {
      event: "blocked",
      data: {
        success: false,
        error: { code: "GOVERNED_OUTPUT_BLOCKED", message: "Every generated output remained non-compliant", http_status: 422 },
        data,
      },
    };
    return;
  }

  const data: GovernedCompleteData = {
    content: scenario.guided.approvedContent ?? "",
    provider: "guided-fixture",
    model: "configured-showcase",
    attempts: 2,
    attempt_metadata: [firstAttempt, attempt(1, true)],
    evaluation: evaluation(true, 0),
    accounting: { generation_attempts: 2, evaluation_batches: 2, policy_evaluations: 2 },
    total_duration_ms: 2_594,
  };
  yield { event: "complete", data: { success: true, data } };
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const value = (await response.json()) as { error?: { message?: unknown } };
    if (typeof value.error?.message === "string") return value.error.message;
  } catch {
    // The status fallback below intentionally avoids exposing untrusted response text.
  }
  return `Request failed (${response.status})`;
}

export async function getPublicConfig(): Promise<PublicConfig> {
  const response = await fetch("/api/demo/config", { credentials: "same-origin" });
  if (!response.ok) throw new Error(await errorMessage(response));
  return publicConfigResponseSchema.parse(await response.json());
}

export async function getSession(): Promise<SessionState | undefined> {
  const response = await fetch("/api/demo/session", { credentials: "same-origin" });
  if (response.status === 401) return undefined;
  if (!response.ok) throw new Error(await errorMessage(response));
  return sessionResponseSchema.parse(await response.json());
}

export async function createSession(turnstileToken: string): Promise<SessionState> {
  const response = await fetch("/api/demo/session", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ turnstileToken }),
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return sessionResponseSchema.parse(await response.json());
}

export async function deleteSession(): Promise<void> {
  const response = await fetch("/api/demo/session", { method: "DELETE", credentials: "same-origin" });
  if (!response.ok) throw new Error(await errorMessage(response));
}

export async function* runLiveScenario(
  scenarioId: string,
  signal?: AbortSignal,
): AsyncGenerator<GovernedStreamEvent> {
  const response = await fetch("/api/demo/generate", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ scenarioId }),
    signal,
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  if (!isEventStreamContentType(response.headers.get("Content-Type")) || !response.body) {
    throw new Error("Live endpoint did not return a governed event stream");
  }
  yield* parseSseStream(response.body);
}

export function extractDpoRecords(
  scenario: DemoScenario,
  completion: GovernedCompleteData,
  mode: RunMode,
): DpoRecord[] {
  const prompt = buildScenarioPrompt(scenario);
  return completion.attempt_metadata.flatMap((item) => {
    if (item.allowed || !item.rejected_content) return [];
    const metadata: DpoRecord["metadata"] = {
      source: mode === "guided" ? "guided_fixture" : "live",
      scenario_id: scenario.id,
      source_attempt: item.attempt,
      provider: item.provider,
      model: item.model,
      policy_ids: [...completion.evaluation.policy_ids],
      ...(completion.evaluation.receipt_id ? { receipt_id: completion.evaluation.receipt_id } : {}),
    };
    return [{
      prompt,
      rejected: item.rejected_content,
      chosen: completion.content,
      steering_rationale: [...(item.steering_rationale ?? [])],
      metadata,
    }];
  });
}
