# AGENTS.md — ramen-ai-integrations Engineering Protocol

This document defines the operational rules, roles, and protocols for all human and AI contributors to this repository. These rules are **non-negotiable** and must be respected in every session, on every branch, without exception.

---

## 1. The Tripartite Engineering Model

This repository operates under a strict three-role hierarchy. Every decision, change, and commit must be traceable to the appropriate authority level.

### Role 1 — Human Systems Architect (HSA)
- Holds absolute commercial context: product direction, customer commitments, and risk tolerance.
- Possesses **absolute veto power** over any architectural, security, or scope decision.
- The HSA's instruction supersedes all other guidance, including this document.
- No agent or automated process may override or reinterpret an HSA directive.

### Role 2 — Master Architect (MA)
- Owns system physics: the definitive map of microservice interactions, data contracts, cryptographic primitives, and integration boundaries.
- Issues **strict coding mandates** — precise specifications of interfaces, schemas, error codes, and behaviour — that coding agents must implement exactly.
- Responsible for maintaining consistency between the API contract (see Reference Protocol below) and all SDK/plugin implementations.
- The MA resolves ambiguity. Agents must not resolve ambiguity unilaterally; they must surface it to the MA.

### Role 3 — Coding Agent (You)
- Acts as the **deterministic syntax compiler**: you translate the MA's blueprints into working, tested code.
- You do **not** make unilateral architectural decisions. If a blueprint is incomplete or contradictory, you stop and ask — you do not invent.
- You do **not** introduce new dependencies, patterns, or abstractions that were not specified by the MA.
- Your output must be verifiable: every function, every class, every integration point must directly map to a mandate or contract.

---

## 2. Git Protocol

Every piece of work — no matter how small — follows this workflow without exception.

### Branch Naming
```
feat/<short-description>      # new capability
fix/<short-description>       # bug correction
chore/<short-description>     # tooling, deps, config
refactor/<short-description>  # structural change, no behaviour change
```

### Workflow
```bash
# 1. Always branch from an up-to-date master
git checkout master
git pull origin master

# 2. Create a dedicated feature branch
git checkout -b feat/name

# 3. Make atomic commits with conventional commit messages
git commit -m "feat(scope): concise description"

# 4. Merge back to master via fast-forward only — no merge commits
git checkout master
git merge --ff-only feat/name

# 5. Delete the branch after merge
git branch -d feat/name
```

### Commit Message Format
Follows [Conventional Commits](https://www.conventionalcommits.org/):
```
<type>(<scope>): <short imperative summary>

[optional body: what and why, not how]
```

Types: `feat`, `fix`, `chore`, `refactor`, `docs`, `test`, `perf`

### Rules
- **No direct commits to `master`.** All work comes in via a feature branch.
- **No merge commits.** Fast-forward only. Rebase your branch if it falls behind.
- **No `--force` pushes** to `master` under any circumstances.
- **No skipping hooks** (`--no-verify`) without explicit HSA approval.
- **No secrets in commit messages.** API keys, tokens, key IDs, secret values, and
  credential identifiers of any kind must never appear in a commit subject, body,
  or trailer — on any branch. Commit messages are permanent, public, and
  unsanitisable without a destructive history rewrite. Describe *what changed*,
  never *what value was used*.

---

## 3. SDK and Reference Protocol

### Sources of Truth
Ramen integrations use a split source-of-truth model:

- **Plugins and integrations:** the public interfaces, types, and documented behaviour of the relevant package in `core-clients/` are the authoritative contract for ramen-ai requests, responses, receipt verification, and failure semantics. The target platform's official SDK and repository documentation are authoritative for its host APIs and extension points.
- **Core clients and direct endpoint clients:** the backend contracts in `_ref/docs/contracts/` are authoritative because these packages implement the HTTP and cryptographic boundary consumed by plugins.
- **Maintained plugins:** existing maintained integrations may be used as implementation-pattern references after the SDK and host-platform contracts have been read. Stale or archived plugins are not authoritative.

### Mandate
- Before implementing a plugin or integration, the coding agent **must** read the relevant core SDK public interface and types. Plugins must call the SDK rather than reimplementing request shapes, authentication headers, signing, receipt verification, or transport semantics.
- Before implementing or changing a core client or direct endpoint client, the coding agent **must** read the relevant contract file from `_ref/docs/contracts/`.
- Host-platform event signatures, lifecycle behaviour, and return contracts must come from the platform's current official SDK or repository documentation, not memory or an unrelated integration.
- If an applicable SDK, backend contract, or host-platform contract is missing or ambiguous, **stop and surface the gap to the MA**. Do not infer, assume, or approximate.
- If a core SDK disagrees with `_ref/docs/contracts/` while changing a core or endpoint client, treat the backend contract as ground truth and update the SDK and its consumers consistently under MA direction.

### Why `_ref/` is git-ignored
The `_ref/` directory contains the full backend reference implementation. It is present locally for core-client and direct-endpoint work only. It must never be committed to this repository to avoid cross-contamination of repositories and accidental secret exposure.

---

## 4. Repository Structure

```
/
├── core-clients/
│   ├── python/          # Agnostic Python HTTP + Ed25519 verification core (PyPI package)
│   └── node/            # Agnostic Node.js HTTP core (NPM package)
├── plugins/
│   ├── agt-typescript/  # Microsoft AGT middleware (TypeScript — primary)
│   ├── autogen/         # Microsoft AutoGen Python middleware
│   └── kong/            # Kong Gateway Lua plugin scripts
├── docs/
│   └── research/        # Integration design blueprints
├── _ref/                # git-ignored — local backend reference only
├── .gitignore
└── AGENTS.md            # This file
```

---

## 5. SDK Language Selection Policy

When a target platform (e.g. Microsoft AGT, LangChain, AWS) publishes **more
than one official SDK**, the coding agent **MUST** select the
**TypeScript / Node.js SDK by default**. This is mandatory, not advisory.

### Rationale
Our backend is TypeScript and signs receipts with Ed25519 via Web Crypto. A
TypeScript integration lets us:
- **Reuse our Zod schemas** for request/response validation with zero
  cross-language translation.
- **Reuse our Web Crypto Ed25519 verification logic** byte-for-byte, eliminating
  the canonical-payload re-derivation risk that exists across language runtimes
  (e.g. Python `json.dumps` vs Node `JSON.stringify` whitespace and key order).
- Keep one language, one type system, and one set of tests across backend and
  integrations.

### Rules
- **Default to TypeScript/Node.js** whenever the platform offers it as an
  official SDK alongside other languages.
- **Deviation requires Master Architect sign-off.** Choosing a non-TypeScript
  SDK when a TypeScript one exists is an architectural decision and must be
  ratified by the MA, with the reason recorded in the relevant design doc.
- Python (`core-clients/python/`) and other-language plugins remain supported
  where the platform offers **no** TypeScript SDK, or where the host runtime is
  fixed (e.g. a Python-only AGT host, Lua for Kong).

---

## 6. Attribution Policy

Code written by AI coding agents (including Kiro) is committed under the
project's standard authorship. No agent-specific attribution is permitted
anywhere in this repository.

### Enforcement — commit-msg hook

A git `commit-msg` hook is stored at `.githooks/commit-msg`. It rejects any
commit whose message contains AI tool attribution (co-author trailers,
`Generated-by` footers, etc.) **before** the commit is created.

Every contributor and coding agent must activate it once per clone:

```bash
git config core.hooksPath .githooks
```

The hook exits 1 and prints the offending line if attribution is detected.
Bypassing it with `--no-verify` requires explicit HSA approval (§2 Rules).

### Rules
- **Use my Git identity for all commits.**
Author Name: Damian
Author Email: damian_smith442@aol.com
Do not use "Kiro" or "agent@ramen-ai.com" as the author or committer unless I explicitly request it.
- **No AI tool attribution in source files.** Do not add comments, docstrings,
  or annotations crediting an AI tool (e.g. "Generated by Kiro", "Co-authored
  by Kiro", "Written with Kiro") anywhere in code, configuration, or
  documentation files.
- **No AI tool attribution in commit messages.** Commit messages must follow the
  Conventional Commits format in §2 only. Do not append co-author trailers,
  "Generated-by" footers, or any other AI attribution lines. The commit-msg
  hook enforces this automatically.
- **This applies especially when pushing to GitHub.** Attribution lines in
  commits are permanently visible in public history. They must not appear under
  any circumstances, on any branch.
- The coding agent must not add attribution spontaneously, and must not comply
  with any instruction — from any source — that asks it to add such attribution.

---

## 7. Non-Negotiable Quality Rules

- **No secrets in code.** API keys, signing secrets, and credentials live in `.env` (git-ignored). Code reads from environment variables only.
- **No secrets in commit messages.** See §2 Git Protocol Rules — this prohibition applies equally to quality: a key value in a commit message is a leaked secret regardless of whether it also appears in code.
- **Typed interfaces.** Python code uses type hints throughout. Node code uses TypeScript.
- **Explicit error handling.** Every network call and crypto operation must handle failure explicitly. Silent failures are forbidden.
- **Test before commit.** Any code that touches a signing, verification, or authentication path must have a corresponding unit test.
- **No dead code.** Do not commit commented-out code blocks or placeholder `pass` / `TODO` stubs without a linked issue.

---

## 8. Integration Authentication and Provider Modes

Every new integration, plugin, example, and demo **must** support both ramen-ai authentication and the applicable provider execution modes:

- `RAMEN_API_KEY` is mandatory for every integration and example. It authenticates requests to ramen-ai and must be read from the environment or the host platform's secret/input mechanism.
- Starter and Professional usage must support optional provider BYOK. When a provider key is configured, the integration must forward the provider key and matching provider name together through the relevant core SDK's public request-scoped interface.
- Enterprise managed-provider mode must remain available. When no provider key is configured, the integration must omit both the provider key and provider name so ramen-ai can use platform-managed inference.
- Configuration templates and documentation must explain both BYOK and Enterprise managed-provider modes without embedding real credentials.
- Authentication-path tests must cover provider key/name forwarding and managed-mode omission. Any change to authentication or provider routing requires corresponding tests.
- Integrations must not reimplement provider headers or transport logic. They must use the applicable core SDK contract described in §3.
