import {
  GovernanceDeniedException,
  GovernedGenerationException,
} from "./governed-errors.js";
import type {
  GenerateGovernedOptions,
  GovernedAccounting,
  GovernedAttemptMetadata,
  GovernedBlockedData,
  GovernedCompleteData,
  GovernedCompleteEvent,
  GovernedEvaluationSummary,
  GovernedGenerateWireRequest,
  GovernedHeartbeatEvent,
  GovernedStatusEvent,
  GovernedStatusStage,
  GovernedStreamEvent,
  GovernedTokenUsage,
} from "./governed-types.js";

const GOVERNED_PATH = "/api/v1/generate/governed";
const GOVERNED_TIMEOUT_MS = 60_000;
const STATUS_STAGES = new Set<GovernedStatusStage>([
  "accepted",
  "generating",
  "evaluating",
  "regenerating",
]);

type UnknownRecord = Record<string, unknown>;

export interface GovernedTransportConfig {
  apiKey: string;
  baseUrl: string;
  providerKey?: string;
  providerName?: string;
  fetchImpl: typeof fetch;
}

export async function generateGoverned(
  config: GovernedTransportConfig,
  prompt: string,
  options: GenerateGovernedOptions,
): Promise<GovernedCompleteData> {
  const body = buildBody(prompt, options);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), GOVERNED_TIMEOUT_MS);

  try {
    const response = await config.fetchImpl(`${config.baseUrl}${GOVERNED_PATH}`, {
      method: "POST",
      headers: buildHeaders(config, "application/json"),
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    const payload = await decodeJson(response);
    if (!response.ok || payload.success !== true) {
      throwApiError(response.status, payload);
    }
    return parseCompleteData(payload.data, response.status);
  } catch (error) {
    if (error instanceof GovernedGenerationException) throw error;
    if (controller.signal.aborted) {
      throw new GovernedGenerationException(
        null,
        "TRANSPORT_TIMEOUT",
        "Governed generation timed out",
      );
    }
    throw new GovernedGenerationException(
      null,
      "TRANSPORT_ERROR",
      "Governed generation request failed",
      error,
    );
  } finally {
    clearTimeout(timer);
  }
}

export async function* generateGovernedStream(
  config: GovernedTransportConfig,
  prompt: string,
  options: GenerateGovernedOptions,
): AsyncGenerator<GovernedStreamEvent> {
  const body = buildBody(prompt, options);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), GOVERNED_TIMEOUT_MS);
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  let terminalSeen = false;

  try {
    const response = await config.fetchImpl(`${config.baseUrl}${GOVERNED_PATH}`, {
      method: "POST",
      headers: buildHeaders(config, "text/event-stream"),
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!response.ok) {
      const payload = await decodeJson(response);
      throwApiError(response.status, payload);
    }

    const contentType = response.headers.get("Content-Type")?.toLowerCase() ?? "";
    if (!contentType.startsWith("text/event-stream") || !response.body) {
      throw new GovernedGenerationException(
        response.status,
        "STREAM_PROTOCOL_ERROR",
        "Governed generation did not return an SSE stream",
      );
    }

    reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const parseFrames = (flush: boolean): GovernedStreamEvent[] => {
      const frames: string[] = [];
      const delimiter = /\r\n\r\n|\r\r|\n\n/g;
      let frameStart = 0;
      let match: RegExpExecArray | null;
      while ((match = delimiter.exec(buffer)) !== null) {
        frames.push(buffer.slice(frameStart, match.index));
        frameStart = match.index + match[0].length;
      }
      buffer = buffer.slice(frameStart);
      if (flush && buffer.length > 0) {
        frames.push(buffer);
        buffer = "";
      }
      const events: GovernedStreamEvent[] = [];
      for (const frame of frames) {
        const event = parseSseFrame(frame, response.status);
        if (event) events.push(event);
      }
      return events;
    };

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        buffer += decoder.decode();
        if (buffer.length > 0) buffer += "\n\n";
      } else {
        buffer += decoder.decode(value, { stream: true });
      }

      for (const event of parseFrames(done)) {
        if (event.event === "complete") terminalSeen = true;
        yield event;
        if (event.event === "complete") return;
      }
      if (done) break;
    }

    throw new GovernedGenerationException(
      response.status,
      "STREAM_TERMINATED",
      "Governed generation stream ended without a terminal event",
    );
  } catch (error) {
    if (error instanceof GovernedGenerationException) throw error;
    if (controller.signal.aborted) {
      throw new GovernedGenerationException(
        null,
        "TRANSPORT_TIMEOUT",
        "Governed generation stream timed out",
      );
    }
    throw new GovernedGenerationException(
      null,
      "TRANSPORT_ERROR",
      "Governed generation stream failed",
      error,
    );
  } finally {
    clearTimeout(timer);
    if (reader) {
      if (!terminalSeen) await reader.cancel();
      reader.releaseLock();
    }
  }
}

function buildBody(
  prompt: string,
  options: GenerateGovernedOptions,
): GovernedGenerateWireRequest {
  if (typeof prompt !== "string" || !prompt.trim() || prompt.length > 10_000) {
    throw new Error("prompt must be a non-blank string of at most 10,000 characters");
  }
  if (!options.policyIds?.length && !options.bundleIds?.length) {
    throw new Error("Provide at least one of bundleIds or policyIds");
  }
  const maxRetries = options.maxRetries ?? 1;
  if (maxRetries !== 0 && maxRetries !== 1) {
    throw new Error("maxRetries must be 0 or 1");
  }

  const body: GovernedGenerateWireRequest = { prompt, max_retries: maxRetries };
  if (options.policyIds?.length) body.policy_ids = [...options.policyIds];
  if (options.bundleIds?.length) body.bundle_ids = [...options.bundleIds];
  if (options.generation) {
    const { temperature, maxTokens } = options.generation;
    if (
      temperature !== undefined
      && (!Number.isFinite(temperature) || temperature < 0 || temperature > 2)
    ) {
      throw new Error("generation.temperature must be between 0 and 2");
    }
    if (
      maxTokens !== undefined
      && (!Number.isInteger(maxTokens) || maxTokens < 1 || maxTokens > 4096)
    ) {
      throw new Error("generation.maxTokens must be an integer between 1 and 4096");
    }
    body.generation = {
      ...(temperature !== undefined ? { temperature } : {}),
      ...(maxTokens !== undefined ? { max_tokens: maxTokens } : {}),
    };
  }
  return body;
}

function buildHeaders(
  config: GovernedTransportConfig,
  accept: "application/json" | "text/event-stream",
): Record<string, string> {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${config.apiKey}`,
    Accept: accept,
    "Content-Type": "application/json",
  };
  if (config.providerKey) {
    headers["X-Provider-Key"] = config.providerKey;
    if (config.providerName) headers["X-Provider"] = config.providerName;
  }
  return headers;
}

async function decodeJson(response: Response): Promise<UnknownRecord> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch (error) {
    throw new GovernedGenerationException(
      response.status,
      "PARSE_ERROR",
      "Failed to parse governed generation response",
      error,
    );
  }
  if (!isRecord(payload)) {
    throw new GovernedGenerationException(
      response.status,
      "PARSE_ERROR",
      "Governed generation response must be a JSON object",
    );
  }
  return payload;
}

function throwApiError(status: number, payload: UnknownRecord): never {
  const error = isRecord(payload.error) ? payload.error : {};
  const code = typeof error.code === "string" ? error.code : "UNKNOWN_ERROR";
  const message = typeof error.message === "string"
    ? error.message
    : `Governed generation failed with HTTP ${status}`;
  const details = error.details ?? payload.data;
  if (status === 422 && code === "GOVERNED_OUTPUT_BLOCKED") {
    throw new GovernanceDeniedException(
      message,
      parseBlockedData(payload.data, status),
    );
  }
  throw new GovernedGenerationException(status, code, message, details);
}

function parseSseFrame(
  frame: string,
  status: number,
): GovernedStreamEvent | null {
  let eventName: string | undefined;
  const dataLines: string[] = [];
  for (const line of frame.split(/\r\n|\r|\n/)) {
    if (line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") eventName = value;
    if (field === "data") dataLines.push(value);
  }

  if (!eventName || !["status", "heartbeat", "complete", "blocked", "error"].includes(eventName)) {
    return null;
  }
  if (!dataLines.length) {
    throw new GovernedGenerationException(
      status,
      "STREAM_PARSE_ERROR",
      `SSE event ${eventName} has no data`,
    );
  }

  let payload: unknown;
  try {
    payload = JSON.parse(dataLines.join("\n"));
  } catch (error) {
    throw new GovernedGenerationException(
      status,
      "STREAM_PARSE_ERROR",
      `Failed to parse governed generation SSE event: ${eventName}`,
      error,
    );
  }
  if (!isRecord(payload)) {
    throw new GovernedGenerationException(
      status,
      "STREAM_PARSE_ERROR",
      `Governed generation SSE event ${eventName} must contain an object`,
    );
  }

  try {
    if (eventName === "status") {
      const stage = stringField(payload, "stage");
      if (!STATUS_STAGES.has(stage as GovernedStatusStage)) {
        throw new TypeError("Invalid governed status stage");
      }
      const event: GovernedStatusEvent = {
        event: "status",
        data: {
          stage: stage as GovernedStatusStage,
          attempt: integerField(payload, "attempt"),
          ...(payload.violations !== undefined
            ? { violations: integerValue(payload.violations, "violations") }
            : {}),
        },
      };
      return event;
    }
    if (eventName === "heartbeat") {
      const event: GovernedHeartbeatEvent = {
        event: "heartbeat",
        data: { timestamp: stringField(payload, "timestamp") },
      };
      return event;
    }
    if (eventName === "complete") {
      if (payload.success !== true) throw new TypeError("Invalid complete event");
      const event: GovernedCompleteEvent = {
        event: "complete",
        data: { success: true, data: parseCompleteData(payload.data, status) },
      };
      return event;
    }

    const error = recordField(payload, "error");
    const code = stringField(error, "code");
    const message = stringField(error, "message");
    const logicalStatus = integerField(error, "http_status");
    if (eventName === "blocked") {
      if (code !== "GOVERNED_OUTPUT_BLOCKED" || logicalStatus !== 422) {
        throw new TypeError("Invalid blocked terminal event");
      }
      throw new GovernanceDeniedException(
        message,
        parseBlockedData(payload.data, logicalStatus),
      );
    }
    throw new GovernedGenerationException(
      logicalStatus,
      code,
      message,
      payload.data,
    );
  } catch (error) {
    if (error instanceof GovernedGenerationException) throw error;
    throw new GovernedGenerationException(
      status,
      "STREAM_PARSE_ERROR",
      `Invalid governed generation SSE event: ${eventName}`,
      error,
    );
  }
}

function parseCompleteData(value: unknown, status: number): GovernedCompleteData {
  try {
    const data = recordValue(value, "data");
    return {
      content: stringField(data, "content"),
      provider: stringField(data, "provider"),
      model: stringField(data, "model"),
      ...(data.usage !== undefined ? { usage: parseUsage(data.usage) } : {}),
      attempts: integerField(data, "attempts"),
      attempt_metadata: parseAttempts(data.attempt_metadata),
      evaluation: parseEvaluation(data.evaluation),
      accounting: parseAccounting(data.accounting),
      total_duration_ms: integerField(data, "total_duration_ms"),
    };
  } catch (error) {
    if (error instanceof GovernedGenerationException) throw error;
    throw new GovernedGenerationException(
      status,
      "PARSE_ERROR",
      "Invalid governed generation completion payload",
      error,
    );
  }
}

function parseBlockedData(value: unknown, status: number): GovernedBlockedData {
  try {
    const data = recordValue(value, "data");
    return {
      attempts: integerField(data, "attempts"),
      attempt_metadata: parseAttempts(data.attempt_metadata),
      evaluation: parseEvaluation(data.evaluation),
      accounting: parseAccounting(data.accounting),
      total_duration_ms: integerField(data, "total_duration_ms"),
    };
  } catch (error) {
    if (error instanceof GovernedGenerationException) throw error;
    throw new GovernedGenerationException(
      status,
      "PARSE_ERROR",
      "Invalid governed generation blocked payload",
      error,
    );
  }
}

function parseUsage(value: unknown): GovernedTokenUsage {
  const usage = recordValue(value, "usage");
  return {
    prompt_tokens: integerField(usage, "prompt_tokens"),
    completion_tokens: integerField(usage, "completion_tokens"),
    total_tokens: integerField(usage, "total_tokens"),
  };
}

function parseAttempts(value: unknown): GovernedAttemptMetadata[] {
  if (!Array.isArray(value)) throw new TypeError("attempt_metadata must be an array");
  return value.map(item => {
    const attempt = recordValue(item, "attempt_metadata item");
    return {
      attempt: integerField(attempt, "attempt"),
      provider: stringField(attempt, "provider"),
      model: stringField(attempt, "model"),
      generation_duration_ms: integerField(attempt, "generation_duration_ms"),
      evaluation_duration_ms: integerField(attempt, "evaluation_duration_ms"),
      policies_evaluated: integerField(attempt, "policies_evaluated"),
      allowed: booleanField(attempt, "allowed"),
      ...(attempt.usage !== undefined ? { usage: parseUsage(attempt.usage) } : {}),
    };
  });
}

function parseAccounting(value: unknown): GovernedAccounting {
  const accounting = recordValue(value, "accounting");
  return {
    generation_attempts: integerField(accounting, "generation_attempts"),
    evaluation_batches: integerField(accounting, "evaluation_batches"),
    policy_evaluations: integerField(accounting, "policy_evaluations"),
  };
}

function parseEvaluation(value: unknown): GovernedEvaluationSummary {
  const evaluation = recordValue(value, "evaluation");
  const receiptId = evaluation.receipt_id;
  if (receiptId !== undefined && typeof receiptId !== "string") {
    throw new TypeError("receipt_id must be a string");
  }
  return {
    allowed: booleanField(evaluation, "allowed"),
    policy_ids: stringArrayField(evaluation, "policy_ids"),
    policies_evaluated: integerField(evaluation, "policies_evaluated"),
    policies_passed: integerField(evaluation, "policies_passed"),
    policies_failed: integerField(evaluation, "policies_failed"),
    policies_errored: integerField(evaluation, "policies_errored"),
    violation_count: integerField(evaluation, "violation_count"),
    statutory_anchors: stringArrayField(evaluation, "statutory_anchors"),
    ...(receiptId !== undefined ? { receipt_id: receiptId } : {}),
  };
}

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function recordValue(value: unknown, name: string): UnknownRecord {
  if (!isRecord(value)) throw new TypeError(`${name} must be an object`);
  return value;
}

function recordField(record: UnknownRecord, key: string): UnknownRecord {
  return recordValue(record[key], key);
}

function stringField(record: UnknownRecord, key: string): string {
  const value = record[key];
  if (typeof value !== "string") throw new TypeError(`${key} must be a string`);
  return value;
}

function integerValue(value: unknown, name: string): number {
  if (!Number.isInteger(value)) throw new TypeError(`${name} must be an integer`);
  return value as number;
}

function integerField(record: UnknownRecord, key: string): number {
  return integerValue(record[key], key);
}

function booleanField(record: UnknownRecord, key: string): boolean {
  const value = record[key];
  if (typeof value !== "boolean") throw new TypeError(`${key} must be a boolean`);
  return value;
}

function stringArrayField(record: UnknownRecord, key: string): string[] {
  const value = record[key];
  if (!Array.isArray(value) || value.some(item => typeof item !== "string")) {
    throw new TypeError(`${key} must be an array of strings`);
  }
  return value as string[];
}
