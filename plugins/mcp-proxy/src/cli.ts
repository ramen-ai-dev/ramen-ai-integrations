/**
 * cli.ts — argument parser for mcp-shield-proxy.
 *
 * Usage:
 *   mcp-shield-proxy --target "node server.js" --bundle-ids ramen__shield_core_it
 *   mcp-shield-proxy --target "uvx mcp-server-fetch" --bundle-ids ramen__eu_ai_act_baseline
 *   mcp-shield-proxy --target "npx @modelcontextprotocol/server-filesystem /path" \
 *                    --policy-ids 6c787849-96db-4c92-8df9-10aa8d035527
 *
 * All secrets are read from the environment — never passed as arguments.
 *
 * Environment variables:
 *   RAMEN_API_KEY      (required) ramen-ai bearer token
 *   OPENAI_API_KEY     (optional) BYOK LLM provider key
 *   ANTHROPIC_API_KEY  (optional) BYOK alternative provider key
 *   RAMEN_PROVIDER     (optional) provider name: openai | anthropic | google
 *   RAMEN_BASE_URL     (optional) override API base URL
 */

import type { ProxyConfig } from "./types.js";

function printUsageAndExit(message?: string): never {
  if (message) process.stderr.write(`Error: ${message}\n\n`);
  process.stderr.write(
    `Usage: mcp-shield-proxy [options] -- <command> [args...]

Options:
  --target <cmd>          Target MCP server command (quoted, or use -- separator)
  --bundle-ids <ids>      Comma-separated bundle slugs (e.g. ramen__shield_core_it)
  --policy-ids <ids>      Comma-separated policy UUIDs (alternative to --bundle-ids)
  --log-level <level>     silent | info | debug  (default: info)
  --help                  Show this message

Environment variables (required):
  RAMEN_API_KEY           ramen-ai PaaS API key

Environment variables (optional / BYOK):
  OPENAI_API_KEY          LLM provider key (forwarded as X-Provider-Key)
  ANTHROPIC_API_KEY       Alternative BYOK provider key
  RAMEN_PROVIDER          Provider name override: openai | anthropic | google
                           (otherwise inferred from the selected provider key)
  RAMEN_BASE_URL          Override the ramen-ai API base URL

Examples:
  # Wrap the MCP filesystem server
  RAMEN_API_KEY=ramen_ak_... \\
    mcp-shield-proxy --target "npx @modelcontextprotocol/server-filesystem /home/user" \\
                     --bundle-ids ramen__shield_core_it

  # Claude Desktop config (claude_desktop_config.json):
  # "command": "mcp-shield-proxy"
  # "args": ["--bundle-ids", "ramen__shield_core_it", "--", "npx", "mcp-server-name"]
  # "env": { "RAMEN_API_KEY": "ramen_ak_..." }
`,
  );
  process.exit(1);
}

export function parseArgs(argv: string[], env: Record<string, string | undefined> = process.env): ProxyConfig {
  const args = argv.slice(2); // strip node + script path

  if (args.includes("--help") || args.includes("-h")) printUsageAndExit();

  let targetCommand = "";
  let targetArgs: string[] = [];
  const bundleIds: string[] = [];
  const policyIds: string[] = [];
  let logLevel: ProxyConfig["logLevel"] = "info";

  // Support both --target "cmd arg1 arg2" and -- cmd arg1 arg2
  const doubleDashIdx = args.indexOf("--");
  if (doubleDashIdx !== -1) {
    const after = args.splice(doubleDashIdx); // remove -- and everything after
    after.shift(); // discard "--" itself
    if (after.length === 0) printUsageAndExit("No command specified after --");
    targetCommand = after[0];
    targetArgs = after.slice(1);
  }

  // Parse remaining flags
  for (let i = 0; i < args.length; i++) {
    const flag = args[i];
    const next = args[i + 1];

    switch (flag) {
      case "--target": {
        if (!next) printUsageAndExit("--target requires a value");
        // Shell-split a simple quoted command (no nested quoting)
        const parts = next.trim().split(/\s+/);
        targetCommand = parts[0];
        targetArgs = parts.slice(1);
        i++;
        break;
      }
      case "--bundle-ids": {
        if (!next) printUsageAndExit("--bundle-ids requires a value");
        bundleIds.push(...next.split(",").map((s) => s.trim()).filter(Boolean));
        i++;
        break;
      }
      case "--policy-ids": {
        if (!next) printUsageAndExit("--policy-ids requires a value");
        policyIds.push(...next.split(",").map((s) => s.trim()).filter(Boolean));
        i++;
        break;
      }
      case "--log-level": {
        if (!next) printUsageAndExit("--log-level requires a value");
        if (next !== "silent" && next !== "info" && next !== "debug") {
          printUsageAndExit(`--log-level must be one of: silent, info, debug`);
        }
        logLevel = next;
        i++;
        break;
      }
      default:
        printUsageAndExit(`Unknown flag: ${flag}`);
    }
  }

  if (!targetCommand) printUsageAndExit("No target command specified. Use --target or -- separator.");
  if (!bundleIds.length && !policyIds.length) {
    printUsageAndExit("Provide at least one of --bundle-ids or --policy-ids.");
  }

  // Read secrets from environment — never from args
  const apiKey = env.RAMEN_API_KEY;
  if (!apiKey) printUsageAndExit("RAMEN_API_KEY is not set in the environment.");

  const providerKey = env.OPENAI_API_KEY || env.ANTHROPIC_API_KEY;
  const providerName = providerKey
    ? env.RAMEN_PROVIDER || (env.OPENAI_API_KEY ? "openai" : "anthropic")
    : undefined;
  const baseUrl = env.RAMEN_BASE_URL;

  return {
    apiKey,
    bundleIds,
    policyIds,
    ...(providerKey ? { providerKey } : {}),
    ...(providerName ? { providerName } : {}),
    ...(baseUrl ? { baseUrl } : {}),
    targetCommand,
    targetArgs,
    logLevel,
  };
}
