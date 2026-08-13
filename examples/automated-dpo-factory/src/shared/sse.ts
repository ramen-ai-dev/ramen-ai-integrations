import {
  blockedEnvelopeSchema,
  completeEnvelopeSchema,
  errorEnvelopeSchema,
  heartbeatDataSchema,
  statusDataSchema,
  type GovernedStreamEvent,
} from "./schemas";

const knownEvents = new Set(["status", "heartbeat", "complete", "blocked", "error"]);

export function isEventStreamContentType(value: string | null): boolean {
  return value?.split(";", 1)[0]?.trim().toLowerCase() === "text/event-stream";
}

function isTerminal(event: GovernedStreamEvent): boolean {
  return event.event === "complete" || event.event === "blocked" || event.event === "error";
}

function parseEvent(event: string, dataLines: string[]): GovernedStreamEvent | undefined {
  if (!knownEvents.has(event)) return undefined;
  if (dataLines.length === 0) throw new Error(`SSE event ${event} has no data`);

  let payload: unknown;
  try {
    payload = JSON.parse(dataLines.join("\n"));
  } catch {
    throw new Error(`SSE event ${event} contains malformed JSON`);
  }

  switch (event) {
    case "status":
      return { event, data: statusDataSchema.parse(payload) };
    case "heartbeat":
      return { event, data: heartbeatDataSchema.parse(payload) };
    case "complete":
      return { event, data: completeEnvelopeSchema.parse(payload) };
    case "blocked":
      return { event, data: blockedEnvelopeSchema.parse(payload) };
    case "error":
      return { event, data: errorEnvelopeSchema.parse(payload) };
    default:
      return undefined;
  }
}

export async function* parseSseStream(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<GovernedStreamEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatchFrame = (frame: string): GovernedStreamEvent | undefined => {
    let event = "message";
    const dataLines: string[] = [];
    for (const rawLine of frame.split(/\r?\n/)) {
      if (rawLine.startsWith(":")) continue;
      const separator = rawLine.indexOf(":");
      const field = separator === -1 ? rawLine : rawLine.slice(0, separator);
      let value = separator === -1 ? "" : rawLine.slice(separator + 1);
      if (value.startsWith(" ")) value = value.slice(1);
      if (field === "event") event = value;
      if (field === "data") dataLines.push(value);
    }
    return parseEvent(event, dataLines);
  };

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      if (!frame.trim()) continue;
      const parsed = dispatchFrame(frame);
      if (!parsed) continue;
      yield parsed;
      if (isTerminal(parsed)) {
        await reader.cancel();
        return;
      }
    }

    if (done) break;
  }

  if (buffer.trim()) {
    const parsed = dispatchFrame(buffer);
    if (parsed) {
      yield parsed;
      if (isTerminal(parsed)) return;
    }
  }

  throw new Error("Governed stream ended without a terminal event");
}
