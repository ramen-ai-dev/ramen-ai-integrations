import { buildScenarioPrompt } from "../shared/content";
import {
  publicConfigResponseSchema,
  sessionResponseSchema,
  type DemoScenario,
  type DpoRecord,
  type GovernedCompleteData,
  type GovernedStreamEvent,
} from "../shared/schemas";
import { isEventStreamContentType, parseSseStream } from "../shared/sse";

export type SessionState = { expiresAt: string };
export type PublicConfig = { turnstileSiteKey: string; turnstileAction: string; burstLimit: number; burstWindowSeconds: number };

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
): DpoRecord[] {
  const prompt = buildScenarioPrompt(scenario);
  return completion.attempt_metadata.flatMap((item) => {
    if (item.allowed || !item.rejected_content) return [];
    const metadata: DpoRecord["metadata"] = {
      source: "live",
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
