export interface RateLimiterBinding {
  limit(options: { key: string }): Promise<{ success: boolean }>;
}

export interface AssetsBinding {
  fetch(request: Request): Promise<Response>;
}

export interface Env {
  ASSETS: AssetsBinding;
  DEMO_RATE_LIMITER: RateLimiterBinding;
  RAMEN_API_KEY: string;
  OPENAI_API_KEY: string;
  TURNSTILE_SECRET_KEY: string;
  SESSION_SIGNING_SECRET: string;
  TURNSTILE_SITE_KEY: string;
  TURNSTILE_EXPECTED_ACTION: string;
  SESSION_COOKIE_NAME: string;
}
