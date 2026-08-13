import {
  GovernanceDeniedException,
  GovernedGenerationException,
  RamenClient,
  type GovernedStreamEvent,
} from "@ramen-ai/node-core";
import { demoConfig, getScenario, buildScenarioPrompt } from "../shared/content";
import { generateRequestSchema } from "../shared/schemas";
import { SECURITY_LIMITS } from "../shared/security";
import type { Env } from "./env";
import { applySecurityHeaders, errorResponse, readJsonBody, RequestBodyError } from "./http";
import { readCookie, verifySessionToken } from "./session";

const RAMEN_API_BASE_URL = "https://api.ramenai.dev";
const encoder = new TextEncoder();

function abortableFetch(externalSignal: AbortSignal): typeof fetch {
  return async (input, init) => {
    const controller = new AbortController();
    const signals = [externalSignal, init?.signal].filter((signal): signal is AbortSignal => Boolean(signal));
    const abort = () => controller.abort();
    if (signals.some((signal) => signal.aborted)) controller.abort();
    else signals.forEach((signal) => signal.addEventListener("abort", abort, { once: true }));

    try {
      return await fetch(input, { ...init, signal: controller.signal });
    } finally {
      signals.forEach((signal) => signal.removeEventListener("abort", abort));
    }
  };
}

function encodeEvent(event: string, data: unknown): Uint8Array {
  return encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
}

function eventFrame(event: GovernedStreamEvent): Uint8Array {
  return encodeEvent(event.event, event.data);
}

function governedEventStream(
  client: RamenClient,
  prompt: string,
  upstreamAbort: AbortController,
  requestSignal: AbortSignal,
): ReadableStream<Uint8Array> {
  let source: AsyncGenerator<GovernedStreamEvent> | undefined;
  let cancelled = false;
  const abortUpstream = () => upstreamAbort.abort();
  if (requestSignal.aborted) abortUpstream();
  else requestSignal.addEventListener("abort", abortUpstream, { once: true });

  return new ReadableStream<Uint8Array>({
    async start(controller) {
      source = client.generateGovernedStream(prompt, {
        policyIds: demoConfig.governance.policyIds,
        maxRetries: demoConfig.governance.maxRetries,
        exposeHealingTrail: true,
        generation: {
          temperature: demoConfig.governance.generation.temperature,
          maxTokens: demoConfig.governance.generation.maxTokens,
        },
      });

      try {
        for await (const event of source) {
          if (cancelled) return;
          controller.enqueue(eventFrame(event));
        }
      } catch (error) {
        if (cancelled) return;
        if (error instanceof GovernanceDeniedException) {
          controller.enqueue(encodeEvent("blocked", {
            success: false,
            error: {
              code: error.code,
              message: error.message,
              http_status: error.status,
            },
            data: error.data,
          }));
        } else if (error instanceof GovernedGenerationException) {
          controller.enqueue(encodeEvent("error", {
            success: false,
            error: {
              code: error.code,
              message: error.message,
              http_status: error.status ?? 502,
            },
          }));
        } else {
          controller.enqueue(encodeEvent("error", {
            success: false,
            error: {
              code: "UPSTREAM_UNAVAILABLE",
              message: "The governed generation service is unavailable",
              http_status: 502,
            },
          }));
        }
      } finally {
        requestSignal.removeEventListener("abort", abortUpstream);
        if (!cancelled) controller.close();
      }
    },
    async cancel() {
      cancelled = true;
      upstreamAbort.abort();
      requestSignal.removeEventListener("abort", abortUpstream);
      await source?.return(undefined);
    },
  });
}

export async function handleGenerate(request: Request, env: Env): Promise<Response> {
  const token = readCookie(request, env.SESSION_COOKIE_NAME);
  if (!token) return errorResponse(401, "SESSION_REQUIRED", "Complete verification before running the live demo");

  const session = await verifySessionToken(token, env.SESSION_SIGNING_SECRET);
  if (!session) return errorResponse(401, "SESSION_INVALID", "The demo session is invalid or expired");

  let input: unknown;
  try {
    input = await readJsonBody(request, SECURITY_LIMITS.maxRequestBytes);
  } catch (error) {
    if (error instanceof RequestBodyError) return errorResponse(error.status, error.code, error.message);
    throw error;
  }
  const parsed = generateRequestSchema.safeParse(input);
  if (!parsed.success) return errorResponse(400, "INVALID_REQUEST", "Choose a valid configured scenario");

  const scenario = getScenario(parsed.data.scenarioId);
  if (!scenario) return errorResponse(404, "SCENARIO_NOT_FOUND", "The requested scenario is not configured");
  if (!env.RAMEN_API_KEY || !env.OPENAI_API_KEY) return errorResponse(503, "DEMO_NOT_CONFIGURED", "The live demo credentials are not configured");

  const rateLimit = await env.DEMO_RATE_LIMITER.limit({ key: session.session_id });
  if (!rateLimit.success) {
    return errorResponse(429, "BURST_LIMIT_EXCEEDED", "This session reached the five-request burst limit; retry after the 60-second window resets");
  }

  const upstreamAbort = new AbortController();
  const client = new RamenClient({
    apiKey: env.RAMEN_API_KEY,
    baseUrl: RAMEN_API_BASE_URL,
    providerKey: env.OPENAI_API_KEY,
    providerName: "openai",
    fetchImpl: abortableFetch(upstreamAbort.signal),
  });

  return applySecurityHeaders(
    new Response(governedEventStream(client, buildScenarioPrompt(scenario), upstreamAbort, request.signal), {
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-store, no-transform",
      },
    }),
    true,
  );
}
