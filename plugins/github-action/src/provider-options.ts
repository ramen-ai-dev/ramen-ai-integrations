/** Request-scoped provider options derived from GitHub Action inputs. */
export function buildProviderOptions(
  rawProviderKey: string,
  rawProviderName: string,
): { providerKey?: string; providerName?: string } {
  const providerKey = rawProviderKey.trim();
  if (!providerKey) return {};

  const providerName = rawProviderName.trim().toLowerCase();
  return {
    providerKey,
    ...(providerName ? { providerName } : {}),
  };
}
