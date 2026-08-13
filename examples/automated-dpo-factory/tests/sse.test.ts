import { describe, expect, it } from "vitest";
import { isEventStreamContentType, parseSseStream } from "../src/shared/sse";

function streamFrom(value: string): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(value));
      controller.close();
    },
  });
}

const completion = {
  success: true,
  data: {
    content: "Candidate B should progress.",
    provider: "openai",
    model: "model",
    attempts: 1,
    attempt_metadata: [{
      attempt: 0,
      provider: "openai",
      model: "model",
      generation_duration_ms: 10,
      evaluation_duration_ms: 5,
      policies_evaluated: 1,
      allowed: true,
    }],
    evaluation: {
      allowed: true,
      policy_ids: ["policy"],
      policies_evaluated: 1,
      policies_passed: 1,
      policies_failed: 0,
      policies_errored: 0,
      violation_count: 0,
      statutory_anchors: [],
    },
    accounting: { generation_attempts: 1, evaluation_batches: 1, policy_evaluations: 1 },
    total_duration_ms: 15,
  },
};

describe("governed SSE parser", () => {
  it("parses CRLF frames, comments, and an unterminated final event", async () => {
    const input = [
      ": keepalive\r\n",
      "event: status\r\n",
      'data: {"stage":"accepted","attempt":0}\r\n\r\n',
      "event: complete\r\n",
      `data: ${JSON.stringify(completion)}`,
    ].join("");

    const events = [];
    for await (const event of parseSseStream(streamFrom(input))) events.push(event);

    expect(events).toHaveLength(2);
    expect(events[0]).toEqual({ event: "status", data: { stage: "accepted", attempt: 0 } });
    expect(events[1]?.event).toBe("complete");
  });

  it("joins repeated data lines before parsing", async () => {
    const pretty = JSON.stringify(completion, null, 2)
      .split("\n")
      .map((line) => `data: ${line}`)
      .join("\n");
    const events = [];
    for await (const event of parseSseStream(streamFrom(`event: complete\n${pretty}\n\n`))) events.push(event);
    expect(events[0]?.event).toBe("complete");
  });

  it("rejects malformed events and streams without a terminal event", async () => {
    const malformed = async () => {
      for await (const event of parseSseStream(streamFrom("event: status\ndata: nope\n\n"))) void event;
    };
    const unterminated = async () => {
      for await (const event of parseSseStream(streamFrom('event: status\ndata: {"stage":"accepted","attempt":0}\n\n'))) void event;
    };

    await expect(malformed()).rejects.toThrow("malformed JSON");
    await expect(unterminated()).rejects.toThrow("without a terminal event");
  });
});

describe("SSE protocol boundaries", () => {
  it("accepts only the exact event-stream media type with optional parameters", () => {
    expect(isEventStreamContentType("text/event-stream; charset=utf-8")).toBe(true);
    expect(isEventStreamContentType("text/event-stream-invalid")).toBe(false);
    expect(isEventStreamContentType(null)).toBe(false);
  });

  it("stops at the first terminal event", async () => {
    const duplicate = [
      `event: complete\ndata: ${JSON.stringify(completion)}\n\n`,
      'event: error\ndata: {"success":false,"error":{"code":"LATE","message":"late","http_status":500}}\n\n',
    ].join("");
    const events = [];
    for await (const event of parseSseStream(streamFrom(duplicate))) events.push(event);
    expect(events).toHaveLength(1);
    expect(events[0]?.event).toBe("complete");
  });
});
