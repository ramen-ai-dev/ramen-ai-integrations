/**
 * firewall.ts — ramen-ai evaluation wrapper for the MCP proxy.
 *
 * Evaluates a tools/call payload against the ramen-ai PaaS API and returns
 * a structured verdict. Fail-closed: any transport or parse error is treated
 * as a denial so an unreachable firewall never becomes an open door.
 */

import { RamenClient } from "@ramen-ai/node-core";
import type { ComplianceVerdict } from "@ramen-ai/node-core";
import type { ProxyConfig, ToolsCallParams } from "./types.js";

export interface FirewallVerdict {
  allowed: boolean;
  steering: string | null;
  statutoryAnchors: string[];
  receiptVerified: boolean;
  /** Present when the call was blocked due to an evaluation error */
  error?: string;
}

/**
 * Evaluate a tools/call against the ramen-ai firewall.
 *
 * The evaluation payload is a JSON object containing the tool name and its
 * resolved arguments — giving the evaluator full context about what the
 * agent is about to do.
 */
export async function evaluate(
  params: ToolsCallParams,
  config: ProxyConfig,
  client: RamenClient,
): Promise<FirewallVerdict> {
  const payload = JSON.stringify({
    tool: params.name,
    arguments: params.arguments ?? {},
  });

  let verdict: ComplianceVerdict;
  try {
    verdict = await client.evaluateCompliance(payload, {
      bundleIds: config.bundleIds.length ? config.bundleIds : undefined,
      policyIds: config.policyIds.length ? config.policyIds : undefined,
      context: { tool_name: params.name },
    });
  } catch (err) {
    // Fail-closed: evaluation errors are treated as blocks.
    const message = err instanceof Error ? err.message : String(err);
    return {
      allowed: false,
      steering:
        `ramen-ai evaluation could not complete (fail-closed). ` +
        `Tool '${params.name}' has been blocked. Error: ${message}`,
      statutoryAnchors: [],
      receiptVerified: false,
      error: message,
    };
  }

  return {
    allowed: verdict.allowed,
    steering: verdict.steering,
    statutoryAnchors: verdict.statutoryAnchors,
    receiptVerified: verdict.receiptVerified,
  };
}

/** Build a RamenClient from proxy config. */
export function buildClient(config: ProxyConfig): RamenClient {
  return new RamenClient({
    apiKey: config.apiKey,
    ...(config.baseUrl ? { baseUrl: config.baseUrl } : {}),
    ...(config.providerKey ? { providerKey: config.providerKey } : {}),
    ...(config.providerName ? { providerName: config.providerName } : {}),
  });
}
