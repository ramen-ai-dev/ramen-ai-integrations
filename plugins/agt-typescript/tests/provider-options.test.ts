import { describe, expect, it } from "vitest";

import { providerOptionsFromEnv } from "../src/provider-options.js";

describe("providerOptionsFromEnv", () => {
  it("infers OpenAI routing from OPENAI_API_KEY", () => {
    expect(providerOptionsFromEnv({ OPENAI_API_KEY: "openai-key" })).toEqual({
      providerKey: "openai-key",
      providerName: "openai",
    });
  });

  it("infers Anthropic routing when only ANTHROPIC_API_KEY is set", () => {
    expect(providerOptionsFromEnv({ ANTHROPIC_API_KEY: "anthropic-key" })).toEqual({
      providerKey: "anthropic-key",
      providerName: "anthropic",
    });
  });

  it("prefers OpenAI when both provider keys are set", () => {
    expect(
      providerOptionsFromEnv({
        OPENAI_API_KEY: "openai-key",
        ANTHROPIC_API_KEY: "anthropic-key",
      }),
    ).toEqual({ providerKey: "openai-key", providerName: "openai" });
  });

  it("honors an explicit provider override", () => {
    expect(
      providerOptionsFromEnv({
        OPENAI_API_KEY: "custom-key",
        RAMEN_PROVIDER: "google",
      }),
    ).toEqual({ providerKey: "custom-key", providerName: "google" });
  });

  it("omits both fields in Enterprise managed mode", () => {
    expect(providerOptionsFromEnv({ RAMEN_PROVIDER: "anthropic" })).toEqual({});
  });
});
