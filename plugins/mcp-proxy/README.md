# @ramen-ai/mcp-shield-proxy

<p align="center">
  <img src="https://raw.githubusercontent.com/ramen-ai-dev/ramen-ai-integrations/master/assets/ramen-logo.png" alt="ramen-ai" width="100"/>
</p>

A universal MCP stdio proxy that intercepts **tools/call** JSON-RPC messages
at the transport layer, evaluates them against the
[ramen-ai L2 Semantic Firewall](https://ramenai.dev), and blocks malicious
payloads pre-execution — before they ever reach the downstream MCP server.

Works with any MCP server that uses stdio transport: filesystem, fetch,
GitHub, Brave Search, custom servers, and more. No SDK changes required.
Drop it in front of any existing server in under two minutes.

---

## Can you bypass it?

Standard safety filters catch basic syntax. They fail against encoded payloads
and corporate jargon. We challenge you to bypass our semantic firewall using
the zero-day evasion vectors in our official **[Red Team Guide](https://github.com/ramen-ai-dev/ramen-ai-integrations/blob/master/RED_TEAM_GUIDE.md)**.

Below is a simulation of the Grok/Bankr heist. We fed the raw adversarial
prompt directly into our sandbox. It uses a social engineering wrapper
(claiming a visual impairment) to smuggle a 3,000,000,000 DRB transfer
instruction encoded in Morse code. The firewall evaluated the underlying
semantic intent, intercepted the unauthorized financial transfer, and blocked
it pre-execution, issuing a verified Ed25519 receipt.

<p align="center">
  <img src="https://raw.githubusercontent.com/ramen-ai-dev/ramen-ai-integrations/master/assets/grok-bankr.png" alt="ramen-ai intercepting the Grok/Bankr Morse-code heist pre-execution" width="720"/>
</p>

---

## API Key

To use this integration, you must mint an API Key. We offer a **Free Starter
Tier** (1,000 evaluations/month, BYOK) which includes full access to our Core
IT Security bundle. Mint your key at:
**[https://ramenai.dev/pricing](https://ramenai.dev/pricing)**

---

## How it works

```
Claude Desktop / MCP client
  │
  │  stdin  (newline-delimited JSON-RPC)
  ▼
┌─────────────────────────────────────────────┐
│           mcp-shield-proxy                  │
│                                             │
│  tools/call?                                │
│    → evaluate: {tool, arguments}            │
│      ALLOWED  → forward to child stdin      │
│      BLOCKED  → synthesise isError response │
│                 back to client stdout       │
│                                             │
│  anything else → forward unchanged          │
└─────────────────────────────────────────────┘
  │
  │  stdin  (only allowed tool calls reach here)
  ▼
Downstream MCP server (child process)
  │
  │  stdout (responses, notifications)
  ▼
Claude Desktop / MCP client
```

Every `tools/call` is intercepted and evaluated against the ramen-ai PaaS API
before being forwarded. All other MCP messages — `initialize`, `tools/list`,
`resources/read`, notifications — pass through unchanged. The proxy is
transparent to the MCP client.

**Fail-closed:** if the ramen-ai API is unreachable or returns an error, the
tool call is blocked and an `isError: true` response is returned. An
unavailable firewall never becomes an open door.

---

## Installation

```bash
npm install -g @ramen-ai/mcp-shield-proxy
# or run directly without installing:
npx @ramen-ai/mcp-shield-proxy --help
```

**npm:** [https://www.npmjs.com/package/@ramen-ai/mcp-shield-proxy](https://www.npmjs.com/package/@ramen-ai/mcp-shield-proxy)

---

## Claude Desktop configuration

Claude Desktop's `claude_desktop_config.json` normally points directly at your
MCP server. To add the firewall, wrap the server command with `mcp-shield-proxy`.

**Before** (direct connection):
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user/projects"],
      "env": {}
    }
  }
}
```

**After** (firewall-wrapped):
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@ramen-ai/mcp-shield-proxy",
        "--bundle-ids", "ramen__shield_core_it",
        "--",
        "npx", "-y", "@modelcontextprotocol/server-filesystem", "/home/user/projects"
      ],
      "env": {
        "RAMEN_API_KEY": "ramen_ak_...",
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

The `--` separator marks the boundary between proxy flags and the downstream
server command. Everything after `--` is spawned as the child process.

### Config file location

| Platform | Path |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

---

## Usage

```
mcp-shield-proxy [options] -- <command> [args...]

Options:
  --target <cmd>      Target MCP server command (quoted, alternative to --)
  --bundle-ids <ids>  Comma-separated bundle slugs
  --policy-ids <ids>  Comma-separated policy UUIDs (alternative to --bundle-ids)
  --log-level <level> silent | info | debug  (default: info)
  --help              Show this message
```

### Examples

```bash
# Wrap the MCP filesystem server
RAMEN_API_KEY=ramen_ak_... \
  mcp-shield-proxy --bundle-ids ramen__shield_core_it \
    -- npx -y @modelcontextprotocol/server-filesystem /home/user

# Wrap the Brave Search MCP server (BYOK)
RAMEN_API_KEY=ramen_ak_... \
OPENAI_API_KEY=sk-... \
  mcp-shield-proxy --bundle-ids ramen__shield_core_it \
    -- npx -y @modelcontextprotocol/server-brave-search

# Use explicit policy UUIDs instead of a bundle
RAMEN_API_KEY=ramen_ak_... \
  mcp-shield-proxy --policy-ids 6c787849-96db-4c92-8df9-10aa8d035527 \
    -- node ./my-mcp-server.js

# Debug mode — logs every intercepted message to stderr
RAMEN_API_KEY=ramen_ak_... \
  mcp-shield-proxy --bundle-ids ramen__shield_core_it --log-level debug \
    -- npx -y @modelcontextprotocol/server-filesystem /tmp
```

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `RAMEN_API_KEY` | **yes** | ramen-ai PaaS API key (`ramen_ak_...`). Never pass as a CLI argument. |
| `OPENAI_API_KEY` | Starter/Pro | BYOK LLM provider key. Forwarded as `X-Provider-Key`. |
| `ANTHROPIC_API_KEY` | Starter/Pro | Alternative BYOK provider key (used if `OPENAI_API_KEY` absent). |
| `RAMEN_PROVIDER` | no | Provider name: `openai` \| `anthropic` \| `google` (default: `openai`). |
| `RAMEN_BASE_URL` | no | Override the ramen-ai API base URL (for staging/testing). |

### BYOK (Bring Your Own Key)

The Starter and Professional tiers require your own LLM provider key. Pass it
via `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` — the proxy forwards it as the
`X-Provider-Key` header on every evaluation request. Without it, the API
returns `402 Payment Required` on these tiers.

Enterprise tiers use platform-managed keys — omit the provider key entirely.

---

## Blocked verdict — what the MCP client receives

When a tool call is blocked, the proxy synthesises a valid MCP tool result
with `isError: true` and returns it to the client. The downstream server never
sees the request. The response content contains the verdict, statutory anchors,
and the steering instruction:

```json
{
  "jsonrpc": "2.0",
  "id": 42,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "[BLOCKED] Tool 'drop_database_table' was blocked by the ramen-ai L2 Semantic Firewall.\nStatutory anchors: OWASP ASI-06\nSteering: Refuse destructive operations on production databases.\nReceipt verified (Ed25519): true"
      }
    ],
    "isError": true
  }
}
```

The MCP client (e.g. Claude Desktop) surfaces this as a tool error and the
model receives the steering instruction, enabling deterministic recovery rather
than a silent failure.

---

## Available bundles

| Bundle slug | Coverage |
|---|---|
| `ramen__shield_core_it` | Destructive execution, prompt injection, secret exfiltration, OWASP ASI-06 indirect injection |
| `ramen__eu_ai_act_baseline` | EU AI Act Articles 5, 10, and 50 — prohibited practices, data governance, transparency |

Full bundle reference and pricing: [https://ramenai.dev/pricing](https://ramenai.dev/pricing)

---

## Security considerations

- **Secrets in config files:** `claude_desktop_config.json` is stored on disk.
  On shared machines, prefer setting `RAMEN_API_KEY` and provider keys as
  system-level environment variables rather than hardcoding them in the config.
- **Pass-through traffic:** only `tools/call` messages are evaluated. All other
  MCP message types (resource reads, prompt fetches, notifications) pass through
  without evaluation. If you need to evaluate those, use the ramen-ai SDK
  directly in your server implementation.
- **Logging:** at `--log-level debug`, tool names and argument shapes are logged
  to stderr. Do not use debug mode in production environments where stderr may
  be captured to persistent logs.

---

## Building

```bash
npm install
npm run build      # tsc → dist/
npm test           # vitest run (32 tests)
npm run typecheck  # tsc --noEmit
```
