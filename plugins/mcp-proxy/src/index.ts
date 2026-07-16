#!/usr/bin/env node
/**
 * mcp-shield-proxy — universal MCP stdio transport-layer interceptor.
 *
 * Spawns a downstream MCP server as a child process, intercepts tools/call
 * JSON-RPC messages over stdio, evaluates them against the ramen-ai L2
 * Semantic Firewall, and blocks malicious payloads pre-execution by returning
 * an MCP-compliant isError tool result.
 *
 * All non-tools/call traffic is forwarded unchanged, making this a transparent
 * proxy for every other MCP message type (initialize, tools/list, resources,
 * prompts, notifications, etc.).
 */

import { parseArgs } from "./cli.js";
import { buildClient } from "./firewall.js";
import { runProxy } from "./proxy.js";

const config = parseArgs(process.argv);
const client = buildClient(config);

const { exitCode } = await runProxy(config, client);
process.exit(exitCode);
