import assert from "node:assert/strict";
import test from "node:test";

import { buildProviderOptions } from "../src/provider-options.ts";

test("forwards a normalized provider key and name together", () => {
  assert.deepEqual(buildProviderOptions(" provider-secret ", " Anthropic "), {
    providerKey: "provider-secret",
    providerName: "anthropic",
  });
});

test("allows a provider key without an explicit provider name", () => {
  assert.deepEqual(buildProviderOptions("provider-secret", ""), {
    providerKey: "provider-secret",
  });
});

test("omits both provider fields in Enterprise managed mode", () => {
  assert.deepEqual(buildProviderOptions("  ", "anthropic"), {});
});
