export const SECURITY_LIMITS = Object.freeze({
  sessionTtlSeconds: 3_600,
  burstLimit: 5,
  burstWindowSeconds: 60 as const,
  maxRequestBytes: 2_048,
  upstreamTimeoutMs: 60_000,
});
