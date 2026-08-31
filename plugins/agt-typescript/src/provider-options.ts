export interface ProviderOptions {
  providerKey?: string;
  providerName?: string;
}

/** Resolve request provider options at the example environment boundary. */
export function providerOptionsFromEnv(
  env: Record<string, string | undefined>,
): ProviderOptions {
  const providerKey = env.OPENAI_API_KEY || env.ANTHROPIC_API_KEY;
  if (!providerKey) return {};

  return {
    providerKey,
    providerName:
      env.RAMEN_PROVIDER ||
      (env.OPENAI_API_KEY ? "openai" : "anthropic"),
  };
}
