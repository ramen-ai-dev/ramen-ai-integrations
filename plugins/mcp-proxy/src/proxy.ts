/**
 * proxy.ts — MCP stdio transport interceptor.
 *
 * Spawns the downstream MCP server as a child process and sits between the
 * MCP client (e.g. Claude Desktop) and the server, intercepting every
 * tools/call JSON-RPC message before it reaches the server.
 *
 * Wire diagram:
 *
 *   MCP client
 *     │ stdin  (newline-delimited JSON-RPC)
 *     ▼
 *   [mcp-shield-proxy]  ← this module
 *     │  tools/call?  → evaluate against ramen-ai
 *     │  ALLOWED      → forward to child stdin
 *     │  BLOCKED      → synthesise error response to client stdout
 *     │  anything else→ forward unchanged
 *     ▼
 *   Downstream MCP server (child process)
 *     │ stdout (responses, notifications)
 *     ▼
 *   MCP client
 *
 * Newline-delimited framing: each JSON-RPC message is exactly one line.
 * The proxy buffers partial lines across chunk boundaries and only processes
 * complete lines. This is required by the MCP stdio transport specification.
 */

import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import type { ChildProcess } from "node:child_process";
import type { RamenClient } from "@ramen-ai/node-core";
import type {
  JsonRpcMessage,
  JsonRpcRequest,
  JsonRpcResponse,
  ProxyConfig,
  ToolsCallParams,
  ToolsCallResult,
} from "./types.js";
import { evaluate } from "./firewall.js";

const TOOLS_CALL_METHOD = "tools/call";

// ---------------------------------------------------------------------------
// JSON-RPC helpers
// ---------------------------------------------------------------------------

function isRequest(msg: JsonRpcMessage): msg is JsonRpcRequest {
  return "method" in msg && "id" in msg && msg.id !== undefined;
}

function isToolsCall(msg: JsonRpcMessage): msg is JsonRpcRequest & { params: ToolsCallParams } {
  return (
    isRequest(msg) &&
    msg.method === TOOLS_CALL_METHOD &&
    msg.params !== null &&
    typeof msg.params === "object" &&
    "name" in (msg.params as object)
  );
}

/**
 * Synthesise an MCP-compliant blocked tool result response.
 * Uses the isError=true path specified in the MCP tools spec.
 */
function buildBlockedResponse(
  id: string | number | null,
  toolName: string,
  steering: string | null,
  anchors: string[],
  receiptVerified: boolean,
): JsonRpcResponse {
  const anchorStr = anchors.length ? anchors.join(", ") : "none";
  const steeringStr = steering ?? "This tool call has been blocked by the ramen-ai compliance firewall.";

  const text =
    `[BLOCKED] Tool '${toolName}' was blocked by the ramen-ai L2 Semantic Firewall.\n` +
    `Statutory anchors: ${anchorStr}\n` +
    `Steering: ${steeringStr}\n` +
    `Receipt verified (Ed25519): ${receiptVerified}`;

  const result: ToolsCallResult = {
    content: [{ type: "text", text }],
    isError: true,
  };

  return {
    jsonrpc: "2.0",
    id,
    result,
  };
}

// ---------------------------------------------------------------------------
// Logger
// ---------------------------------------------------------------------------

function makeLogger(level: ProxyConfig["logLevel"]) {
  return {
    info: (msg: string) => {
      if (level === "info" || level === "debug") process.stderr.write(`[ramen-proxy] ${msg}\n`);
    },
    debug: (msg: string) => {
      if (level === "debug") process.stderr.write(`[ramen-proxy:debug] ${msg}\n`);
    },
    error: (msg: string) => {
      // Errors always go to stderr regardless of log level
      process.stderr.write(`[ramen-proxy:error] ${msg}\n`);
    },
  };
}

// ---------------------------------------------------------------------------
// Main proxy runner
// ---------------------------------------------------------------------------

export interface ProxyRunResult {
  exitCode: number;
}

export async function runProxy(
  config: ProxyConfig,
  client: RamenClient,
  // Injectable streams for testing; defaults to process streams
  options?: {
    stdin?: NodeJS.ReadableStream;
    stdout?: NodeJS.WritableStream;
    stderr?: NodeJS.WritableStream;
  },
): Promise<ProxyRunResult> {
  const stdin = options?.stdin ?? process.stdin;
  const stdout = options?.stdout ?? process.stdout;
  const log = makeLogger(config.logLevel);

  log.info(
    `Starting proxy → target: "${config.targetCommand} ${config.targetArgs.join(" ")}" ` +
      `bundles: [${config.bundleIds.join(", ")}]`,
  );

  // Spawn the downstream MCP server
  const child: ChildProcess = spawn(config.targetCommand, config.targetArgs, {
    stdio: ["pipe", "pipe", "inherit"],
    env: process.env,
  });

  if (!child.stdin || !child.stdout) {
    throw new Error("Failed to obtain stdio pipes from child process");
  }

  // Forward child stdout → parent stdout verbatim (responses & notifications)
  child.stdout.pipe(stdout as NodeJS.WritableStream);

  // Forward parent stderr → child stderr is already "inherit" so child writes
  // directly to the terminal. Nothing more to wire for stderr.

  return new Promise<ProxyRunResult>((resolve) => {
    // Buffer incoming data and process complete lines
    const rl = createInterface({ input: stdin, crlfDelay: Infinity });

    // Track in-flight evaluations so we process lines serially for each id
    // but don't block unrelated messages.
    const pending = new Set<string | number | null>();

    rl.on("line", (line: string) => {
      void handleLine(line);
    });

    async function handleLine(line: string): Promise<void> {
      if (!line.trim()) return; // skip blank lines

      let msg: JsonRpcMessage;
      try {
        msg = JSON.parse(line) as JsonRpcMessage;
      } catch {
        // Unparseable line — forward unchanged and let the server handle it
        log.debug(`Forwarding unparseable line: ${line.slice(0, 120)}`);
        child.stdin!.write(line + "\n");
        return;
      }

      // Only intercept tools/call requests
      if (!isToolsCall(msg)) {
        log.debug(`Pass-through: ${"method" in msg ? msg.method : "(response)"}`);
        child.stdin!.write(line + "\n");
        return;
      }

      const params = msg.params as ToolsCallParams;
      log.info(`Intercepting tools/call: ${params.name}`);

      // Deduplicate in-flight evaluations with the same id
      if (pending.has(msg.id!)) {
        log.debug(`Duplicate id ${String(msg.id)} — forwarding`);
        child.stdin!.write(line + "\n");
        return;
      }
      pending.add(msg.id!);

      try {
        const verdict = await evaluate(params, config, client);

        if (verdict.allowed) {
          log.info(`ALLOWED: ${params.name}`);
          child.stdin!.write(line + "\n");
        } else {
          log.info(
            `BLOCKED: ${params.name} | anchors: ${verdict.statutoryAnchors.join(", ") || "none"} | ` +
              (verdict.error ? `error: ${verdict.error}` : `receipt_verified: ${verdict.receiptVerified}`),
          );
          const response = buildBlockedResponse(
            msg.id ?? null,
            params.name,
            verdict.steering,
            verdict.statutoryAnchors,
            verdict.receiptVerified,
          );
          stdout.write(JSON.stringify(response) + "\n");
        }
      } finally {
        pending.delete(msg.id!);
      }
    }

    child.on("exit", (code) => {
      const exitCode = code ?? 0;
      log.info(`Child process exited with code ${exitCode}`);
      resolve({ exitCode });
    });

    child.on("error", (err) => {
      log.error(`Child process error: ${err.message}`);
      resolve({ exitCode: 1 });
    });

    // When the client closes its stdin, wait for all in-flight evaluations to
    // settle before closing child stdin. Without this, `cat`-style piping closes
    // stdin before the async evaluate() call returns, causing the child to exit
    // before the blocked response can be written.
    rl.on("close", () => {
      log.debug("stdin closed — waiting for in-flight evaluations before closing child stdin");
      const drain = async () => {
        // Poll until pending is empty (all evaluations have completed)
        while (pending.size > 0) {
          await new Promise((r) => setTimeout(r, 10));
        }
        log.debug("all evaluations settled — closing child stdin");
        child.stdin!.end();
      };
      void drain();
    });
  });
}
