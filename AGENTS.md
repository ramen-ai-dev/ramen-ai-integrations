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

---

## 3. Reference Protocol

### Location
All authoritative API contracts, data schemas, and cryptographic specifications are located in:
```
_ref/docs/contracts/
```
This directory is **git-ignored** and exists on the developer's local machine only. It is never committed.

### Mandate
- Before implementing any integration, endpoint client, or plugin, the coding agent **must** read the relevant contract file from `_ref/docs/contracts/`.
- Implementation must be **contract-driven**: the contract is ground truth. If the code disagrees with the contract, the code is wrong.
- If a contract file is missing or ambiguous, **stop and surface the gap to the MA**. Do not infer, assume, or approximate.
- All request/response shapes, authentication headers, HMAC/Ed25519 signing procedures, error codes, and rate-limit semantics must be sourced from these contracts — never from memory or external documentation.

### Why `_ref/` is git-ignored
The `_ref/` directory contains the full backend reference implementation. It is present locally for context only. It must never be committed to this repository to avoid cross-contamination of repositories and accidental secret exposure.

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

## 6. Non-Negotiable Quality Rules

- **No secrets in code.** API keys, signing secrets, and credentials live in `.env` (git-ignored). Code reads from environment variables only.
- **Typed interfaces.** Python code uses type hints throughout. Node code uses TypeScript.
- **Explicit error handling.** Every network call and crypto operation must handle failure explicitly. Silent failures are forbidden.
- **Test before commit.** Any code that touches a signing, verification, or authentication path must have a corresponding unit test.
- **No dead code.** Do not commit commented-out code blocks or placeholder `pass` / `TODO` stubs without a linked issue.
