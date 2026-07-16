/**
 * Minimal MCP / JSON-RPC 2.0 types needed by the proxy.
 *
 * Only the shapes the proxy actually inspects are fully typed.
 * Everything else passes through as `unknown` to avoid breaking
 * compatibility with future MCP spec revisions.
 */

// ---------------------------------------------------------------------------
// JSON-RPC 2.0 primitives
// ---------------------------------------------------------------------------

export type JsonRpcId = string | number | null;

export interface JsonRpcRequest {
  jsonrpc: "2.0";
  id?: JsonRpcId;
  method: string;
  params?: unknown;
}

export interface JsonRpcNotification {
  jsonrpc: "2.0";
  method: string;
  params?: unknown;
  // Notifications have no id
}

export interface JsonRpcResponse {
  jsonrpc: "2.0";
  id: JsonRpcId;
  result?: unknown;
  error?: JsonRpcError;
}

export interface JsonRpcError {
  code: number;
  message: string;
  data?: unknown;
}

export type JsonRpcMessage =
  | JsonRpcRequest
  | JsonRpcNotification
  | JsonRpcResponse;

// ---------------------------------------------------------------------------
// MCP tools/call shapes
// ---------------------------------------------------------------------------

/** params of a tools/call request */
export interface ToolsCallParams {
  name: string;
  arguments?: Record<string, unknown>;
}

/** A single content item in a tool result */
export interface McpTextContent {
  type: "text";
  text: string;
}

/** The result field of a successful tools/call response */
export interface ToolsCallResult {
  content: McpTextContent[];
  isError?: boolean;
}

// ---------------------------------------------------------------------------
// Proxy configuration
// ---------------------------------------------------------------------------

export interface ProxyConfig {
  /** ramen-ai PaaS API key */
  apiKey: string;
  /** Bundle IDs to evaluate against (e.g. ["ramen__shield_core_it"]) */
  bundleIds: string[];
  /** Explicit policy UUIDs (alternative to bundleIds) */
  policyIds: string[];
  /** BYOK LLM provider key — forwarded as X-Provider-Key */
  providerKey?: string;
  /** BYOK LLM provider name — forwarded as X-Provider */
  providerName?: string;
  /** Override the ramen-ai API base URL */
  baseUrl?: string;
  /** The downstream MCP server command to spawn */
  targetCommand: string;
  /** Arguments to pass to the target command */
  targetArgs: string[];
  /** Log level: silent | info | debug */
  logLevel: "silent" | "info" | "debug";
}
