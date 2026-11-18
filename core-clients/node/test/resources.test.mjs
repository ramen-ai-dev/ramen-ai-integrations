import assert from "node:assert/strict";
import test from "node:test";

import { RamenApiError, RamenClient, RECEIPTS_MAX_LIMIT } from "../dist/index.js";
import { jsonResponse, recordingFetch } from "./helpers.mjs";

function client(handler, options = {}) {
  const { fetchImpl, calls } = recordingFetch(handler);
  return { calls, client: new RamenClient({ apiKey: "test-key", fetchImpl, ...options }) };
}

const BUNDLE = {
  id: "ramen__shield_core_it",
  name: "Core IT Security",
  description: null,
  policy_ids: ["1006492f-db62-4f46-8775-48b966c5c956"],
  policy_count: 1,
};

test("bundles.list issues an authenticated GET and returns the catalogue", async () => {
  const { client: c, calls } = client(() => jsonResponse({ success: true, data: [BUNDLE] }));
  assert.deepEqual(await c.bundles.list(), [BUNDLE]);
  assert.equal(calls[0].method, "GET");
  assert.equal(calls[0].url, "https://api.ramenai.dev/api/v1/safety/bundles");
  assert.equal(calls[0].headers.Authorization, "Bearer test-key");
  assert.equal(calls[0].body, undefined);
});

test("a custom baseUrl with a trailing slash is honoured", async () => {
  const { client: c, calls } = client(() => jsonResponse({ success: true, data: [] }), { baseUrl: "https://eu.ramenai.dev/" });
  await c.bundles.list();
  assert.equal(calls[0].url, "https://eu.ramenai.dev/api/v1/safety/bundles");
});

test("receipts.list sends limit and offset and returns the page", async () => {
  const page = { receipts: [], pagination: { limit: 25, offset: 50, count: 0 } };
  const { client: c, calls } = client(() => jsonResponse({ success: true, data: page }));
  assert.deepEqual(await c.receipts.list({ limit: 25, offset: 50 }), page);
  assert.equal(calls[0].url, "https://api.ramenai.dev/api/v1/paas/receipts?limit=25&offset=50");
});

test("receipts.list without options sends no query string", async () => {
  const { client: c, calls } = client(() => jsonResponse({ success: true, data: { receipts: [], pagination: {} } }));
  await c.receipts.list();
  assert.equal(calls[0].url, "https://api.ramenai.dev/api/v1/paas/receipts");
});

test("receipts.list rejects out-of-range pagination before any request", async () => {
  const { client: c, calls } = client(() => jsonResponse({ success: true, data: {} }));
  for (const options of [{ limit: 0 }, { limit: RECEIPTS_MAX_LIMIT + 1 }, { limit: 1.5 }, { limit: "5" }, { offset: -1 }, { offset: 0.5 }]) {
    await assert.rejects(c.receipts.list(options), RangeError, JSON.stringify(options));
  }
  assert.equal(calls.length, 0);
});

test("resource errors are RamenApiError with the server code", async () => {
  const body = { success: false, error: { code: "AUTHORIZATION_REQUIRED", message: "Authorization header required" } };
  const { client: c } = client(() => jsonResponse(body, { status: 401 }));
  for (const call of [() => c.bundles.list(), () => c.receipts.list()]) {
    await assert.rejects(call(), (error) => {
      assert.ok(error instanceof RamenApiError);
      assert.equal(error.status, 401);
      assert.equal(error.code, "AUTHORIZATION_REQUIRED");
      assert.equal(error.message, "Authorization header required");
      return true;
    });
  }
});

test("a success body that is not the envelope is INVALID_RESPONSE", async () => {
  const { client: c } = client(() => jsonResponse([BUNDLE]));
  await assert.rejects(c.bundles.list(), (error) => error instanceof RamenApiError && error.code === "INVALID_RESPONSE");
});

test("an envelope that reports success:false is never returned as data", async () => {
  const { client: c } = client(() => jsonResponse({ success: false, data: [BUNDLE] }));
  await assert.rejects(c.bundles.list(), (error) => error instanceof RamenApiError && error.code === "INVALID_RESPONSE");
});
