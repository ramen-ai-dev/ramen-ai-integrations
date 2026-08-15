import assert from "node:assert/strict";
import test from "node:test";

import {
  GovernanceDeniedException,
  GovernedGenerationException,
  RamenClient,
} from "../dist/index.js";

const POLICY_ID = "1006492f-db62-4f46-8775-48b966c5c956";
const encoder = new TextEncoder();

function evaluation(allowed = true) {
  return {
    allowed,
    policy_ids: [POLICY_ID],
    policies_evaluated: 1,
    policies_passed: allowed ? 1 : 0,
    policies_failed: allowed ? 0 : 1,
    policies_errored: 0,
    violation_count: allowed ? 0 : 1,
    statutory_anchors: ["FCA PRIN 2A.2.8"],
    receipt_id: "receipt-1",
  };
}

function attempt(allowed = true) {
  return {
    attempt: 1,
    provider: "openai",
    model: "gpt-test",
    generation_duration_ms: 12,
    evaluation_duration_ms: 8,
    policies_evaluated: 1,
    allowed,
    usage: {
      prompt_tokens: 4,
      completion_tokens: 3,
      total_tokens: 7,
    },
  };
}

function accounting() {
  return {
    generation_attempts: 1,
    evaluation_batches: 1,
    policy_evaluations: 1,
  };
}

function completeData() {
  return {
    content: "approved output",
    provider: "openai",
    model: "gpt-test",
    usage: {
      prompt_tokens: 4,
      completion_tokens: 3,
      total_tokens: 7,
    },
    attempts: 1,
    attempt_metadata: [attempt()],
    evaluation: evaluation(),
    accounting: accounting(),
    total_duration_ms: 20,
  };
}

function blockedData() {
  return {
    attempts: 1,
    attempt_metadata: [attempt(false)],
    evaluation: evaluation(false),
    accounting: accounting(),
    total_duration_ms: 20,
  };
}

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function sseResponse(chunks, onCancel) {
  let index = 0;
  const stream = new ReadableStream({
    pull(controller) {
      if (index === chunks.length) {
        controller.close();
        return;
      }
      controller.enqueue(encoder.encode(chunks[index++]));
    },
    cancel() {
      onCancel?.();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream; charset=utf-8" },
  });
}

function client(fetchImpl, provider = {}) {
  return new RamenClient({
    apiKey: "ramen_ak_test",
    baseUrl: "https://example.test",
    fetchImpl,
    ...provider,
  });
}

test("generateGoverned maps request, BYOK headers, bundles, and response", async () => {
  const fetchImpl = async (url, init) => {
    assert.equal(url, "https://example.test/api/v1/generate/governed");
    assert.equal(init.method, "POST");
    assert.equal(init.headers.Authorization, "Bearer ramen_ak_test");
    assert.equal(init.headers.Accept, "application/json");
    assert.equal(init.headers["X-Provider-Key"], "provider-secret");
    assert.equal(init.headers["X-Provider"], "openai");
    assert.ok(init.signal instanceof AbortSignal);
    assert.deepEqual(JSON.parse(init.body), {
      prompt: "Write a compliant answer",
      policy_ids: [POLICY_ID],
      bundle_ids: ["ramen__baseline"],
      max_retries: 0,
      generation: { temperature: 0.2, max_tokens: 256 },
    });
    return jsonResponse({ success: true, data: completeData() });
  };

  const result = await client(fetchImpl, {
    providerKey: "provider-secret",
    providerName: "openai",
  }).generateGoverned("Write a compliant answer", {
    policyIds: [POLICY_ID],
    bundleIds: ["ramen__baseline"],
    maxRetries: 0,
    generation: { temperature: 0.2, maxTokens: 256 },
  });

  assert.equal(result.content, "approved output");
  assert.equal(result.usage.total_tokens, 7);
  assert.equal(result.evaluation.receipt_id, "receipt-1");
});

test("provider name is not sent without provider key", async () => {
  const fetchImpl = async (_url, init) => {
    assert.equal(init.headers["X-Provider-Key"], undefined);
    assert.equal(init.headers["X-Provider"], undefined);
    return jsonResponse({ success: true, data: completeData() });
  };
  await client(fetchImpl, { providerName: "anthropic" }).generateGoverned(
    "prompt",
    { bundleIds: ["ramen__baseline"] },
  );
});

test("JSON blocked response throws GovernanceDeniedException", async () => {
  const fetchImpl = async () => jsonResponse({
    success: false,
    error: {
      code: "GOVERNED_OUTPUT_BLOCKED",
      message: "No compliant output was produced within the retry limit",
      http_status: 422,
    },
    data: blockedData(),
  }, 422);

  await assert.rejects(
    client(fetchImpl).generateGoverned("prompt", { policyIds: [POLICY_ID] }),
    error => {
      assert.ok(error instanceof GovernanceDeniedException);
      assert.equal(error.status, 422);
      assert.equal(error.code, "GOVERNED_OUTPUT_BLOCKED");
      assert.equal(error.data.evaluation.allowed, false);
      return true;
    },
  );
});

for (const status of [400, 401, 402, 403, 404, 429, 502, 503]) {
  test(`HTTP ${status} response throws a structured exception`, async () => {
    const fetchImpl = async () => jsonResponse({
      success: false,
      error: {
        code: `ERROR_${status}`,
        message: "request failed",
        details: { status },
      },
    }, status);

    await assert.rejects(
      client(fetchImpl).generateGoverned("prompt", { policyIds: [POLICY_ID] }),
      error => {
        assert.ok(error instanceof GovernedGenerationException);
        assert.equal(error.status, status);
        assert.equal(error.code, `ERROR_${status}`);
        assert.deepEqual(error.details, { status });
        return true;
      },
    );
  });
}

test("stream yields multiline CRLF status, heartbeat, and complete across chunks", async () => {
  const complete = JSON.stringify({ success: true, data: completeData() });
  const chunks = [
    "event: status\r\ndata: {\"stage\":\r\n",
    "data: \"accepted\",\"attempt\":0}\r\n\r\nevent: heartbeat\r\n",
    'data: {"timestamp":"2026-08-12T12:00:00.000Z"}\r\n\r\n',
    `event: complete\r\ndata: ${complete}\r\n\r\n`,
  ];
  const fetchImpl = async (_url, init) => {
    assert.equal(init.headers.Accept, "text/event-stream");
    assert.equal(init.headers["X-Provider-Key"], "provider-secret");
    return sseResponse(chunks);
  };

  const events = [];
  for await (const event of client(fetchImpl, {
    providerKey: "provider-secret",
  }).generateGovernedStream("prompt", { policyIds: [POLICY_ID] })) {
    events.push(event);
  }

  assert.equal(events[0].event, "status");
  assert.equal(events[0].data.stage, "accepted");
  assert.equal(events[1].event, "heartbeat");
  assert.equal(events[2].event, "complete");
  assert.equal(events[2].data.data.content, "approved output");
});

test("stream accepts the scrubbing status stage with violations", async () => {
  const complete = JSON.stringify({ success: true, data: completeData() });
  const fetchImpl = async () => sseResponse([
    'event: status\ndata: {"stage":"scrubbing","attempt":0,"violations":1}\n\n',
    `event: complete\ndata: ${complete}\n\n`,
  ]);

  const events = [];
  for await (const event of client(fetchImpl).generateGovernedStream(
    "prompt",
    { policyIds: [POLICY_ID] },
  )) {
    events.push(event);
  }

  assert.equal(events[0].event, "status");
  assert.equal(events[0].data.stage, "scrubbing");
  assert.equal(events[0].data.attempt, 0);
  assert.equal(events[0].data.violations, 1);
  assert.equal(events[1].event, "complete");
});

test("blocked SSE terminal throws and is never yielded", async () => {
  const blocked = JSON.stringify({
    success: false,
    error: {
      code: "GOVERNED_OUTPUT_BLOCKED",
      message: "blocked",
      http_status: 422,
    },
    data: blockedData(),
  });
  const fetchImpl = async () => sseResponse([
    'event: status\ndata: {"stage":"accepted","attempt":0}\n\n',
    `event: blocked\ndata: ${blocked}\n\n`,
  ]);
  const iterator = client(fetchImpl).generateGovernedStream(
    "prompt",
    { policyIds: [POLICY_ID] },
  );

  const first = await iterator.next();
  assert.equal(first.value.event, "status");
  await assert.rejects(iterator.next(), error => {
    assert.ok(error instanceof GovernanceDeniedException);
    assert.equal(error.data.attempts, 1);
    return true;
  });
});

test("SSE error terminal throws a structured exception", async () => {
  const terminal = JSON.stringify({
    success: false,
    error: {
      code: "GOVERNANCE_UNAVAILABLE",
      message: "unavailable",
      http_status: 503,
    },
    data: { accounting: accounting(), attempts: 1, total_duration_ms: 20 },
  });
  const fetchImpl = async () => sseResponse([
    `event: error\ndata: ${terminal}\n\n`,
  ]);

  await assert.rejects(
    async () => {
      for await (const _event of client(fetchImpl).generateGovernedStream(
        "prompt",
        { policyIds: [POLICY_ID] },
      )) { /* no terminal event is yielded */ }
    },
    error => {
      assert.ok(error instanceof GovernedGenerationException);
      assert.equal(error.status, 503);
      assert.equal(error.code, "GOVERNANCE_UNAVAILABLE");
      return true;
    },
  );
});

test("stream preflight HTTP error is parsed as JSON", async () => {
  const fetchImpl = async () => jsonResponse({
    success: false,
    error: { code: "UNAUTHORIZED", message: "bad key" },
  }, 401);

  await assert.rejects(
    async () => {
      for await (const _event of client(fetchImpl).generateGovernedStream(
        "prompt",
        { policyIds: [POLICY_ID] },
      )) { /* no events */ }
    },
    error => error instanceof GovernedGenerationException
      && error.status === 401
      && error.code === "UNAUTHORIZED",
  );
});

test("stream rejects an incorrect content type", async () => {
  const fetchImpl = async () => jsonResponse({}, 200);
  await assert.rejects(
    async () => {
      for await (const _event of client(fetchImpl).generateGovernedStream(
        "prompt",
        { policyIds: [POLICY_ID] },
      )) { /* no events */ }
    },
    error => error instanceof GovernedGenerationException
      && error.code === "STREAM_PROTOCOL_ERROR",
  );
});

test("stream rejects malformed known event JSON", async () => {
  const fetchImpl = async () => sseResponse([
    "event: status\ndata: {not-json}\n\n",
  ]);
  await assert.rejects(
    async () => {
      for await (const _event of client(fetchImpl).generateGovernedStream(
        "prompt",
        { policyIds: [POLICY_ID] },
      )) { /* no events */ }
    },
    error => error instanceof GovernedGenerationException
      && error.code === "STREAM_PARSE_ERROR",
  );
});

test("stream ignores unknown events and flushes complete event at EOF", async () => {
  const complete = JSON.stringify({ success: true, data: completeData() });
  const fetchImpl = async () => sseResponse([
    'event: future-event\ndata: {"ignored":true}\n\n',
    `event: complete\ndata: ${complete}`,
  ]);
  const events = [];
  for await (const event of client(fetchImpl).generateGovernedStream(
    "prompt",
    { policyIds: [POLICY_ID] },
  )) {
    events.push(event);
  }
  assert.equal(events.length, 1);
  assert.equal(events[0].event, "complete");
});

test("stream throws when EOF arrives without a terminal event", async () => {
  const fetchImpl = async () => sseResponse([
    'event: status\ndata: {"stage":"accepted","attempt":0}\n\n',
  ]);
  await assert.rejects(
    async () => {
      for await (const _event of client(fetchImpl).generateGovernedStream(
        "prompt",
        { policyIds: [POLICY_ID] },
      )) { /* consume status */ }
    },
    error => error instanceof GovernedGenerationException
      && error.code === "STREAM_TERMINATED",
  );
});

test("returning early from iterator cancels response body", async () => {
  let cancelled = false;
  const fetchImpl = async () => sseResponse([
    'event: status\ndata: {"stage":"accepted","attempt":0}\n\n',
    'event: heartbeat\ndata: {"timestamp":"later"}\n\n',
  ], () => { cancelled = true; });
  const iterator = client(fetchImpl).generateGovernedStream(
    "prompt",
    { policyIds: [POLICY_ID] },
  );
  assert.equal((await iterator.next()).value.event, "status");
  await iterator.return();
  assert.equal(cancelled, true);
});

test("transport failure is wrapped", async () => {
  const fetchImpl = async () => {
    throw new TypeError("network unavailable");
  };
  await assert.rejects(
    client(fetchImpl).generateGoverned("prompt", { policyIds: [POLICY_ID] }),
    error => error instanceof GovernedGenerationException
      && error.status === null
      && error.code === "TRANSPORT_ERROR",
  );
});

test("request validation rejects missing scope and invalid generation controls", async () => {
  const fetchImpl = async () => {
    throw new Error("fetch must not be called");
  };
  const ramen = client(fetchImpl);
  await assert.rejects(
    ramen.generateGoverned("prompt", {}),
    /at least one/,
  );
  await assert.rejects(
    ramen.generateGoverned("prompt", {
      policyIds: [POLICY_ID],
      generation: { maxTokens: 0 },
    }),
    /maxTokens/,
  );
});


test("stream accepts CR-only SSE framing", async () => {
  const complete = JSON.stringify({ success: true, data: completeData() });
  const fetchImpl = async () => sseResponse([
    'event: status\rdata: {"stage":"accepted","attempt":0}\r\r',
    `event: complete\rdata: ${complete}\r\r`,
  ]);
  const events = [];
  for await (const event of client(fetchImpl).generateGovernedStream(
    "prompt",
    { policyIds: [POLICY_ID] },
  )) {
    events.push(event);
  }
  assert.equal(events.length, 2);
  assert.equal(events[0].event, "status");
  assert.equal(events[1].event, "complete");
});
