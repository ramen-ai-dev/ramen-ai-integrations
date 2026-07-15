# GitHub Marketplace Action Teardown
### Blueprint for `ramen-ai-action` listing optimisation
*Research date: July 2026 — based on direct README/action.yml inspection of live repos*

---

## Subjects analysed

| # | Action | Repo | Stars (tool) | What it does |
|---|---|---|---|---|
| 1 | **TruffleHog OSS** | `trufflesecurity/trufflehog` | ~26.9k ⭐ | Secrets detection + live API verification |
| 2 | **Trivy Action** | `aquasecurity/trivy-action` | ~1.3k action / ~32k tool | Container/IaC/filesystem vuln + SBOM scan |
| 3 | **Gitleaks Action** | `gitleaks/gitleaks-action` | ~18k tool | Git secrets scan, PR comments, SARIF upload |
| 4 | **Bearer Action** | `Bearer/bearer-action` | ~2k action | SAST + data-flow privacy risk, diff-mode PR scan |

None are unicorn-owned. TruffleHog and Gitleaks are indie/startup founders. Trivy is Aqua Security (mid-size). Bearer was acquired by Cycode but the action remains community-maintained.

---

## 1. TruffleHog OSS

**Repo:** `trufflesecurity/trufflehog`
**Marketplace listing:** `trufflehog-oss`
**Stars:** 26.9k (tool repo) — action embedded in the same repo

### Visual assets

| Asset | Type | Placement |
|---|---|---|
| Pixel pig logo `pixel_pig.png` | Static PNG, 140px tall | Top of README — centred H2 title block, before any text |
| `scanning_logos.svg` | SVG grid of logos | Immediately below tagline, before installation — "Now Scanning" section with icons of all 800+ credential sources |
| Animated SVG demo `non-interactive.svg` | Live terminal animation (SVG) | Early in README — "Demo" section, directly after installation options |
| GitHub canary detection screenshot | PNG | In-line in CI/Actions section |
| Contributors image from `contrib.rocks` | Auto-generated PNG | Bottom of README |

**Key observation:** TruffleHog leads with a terminal animation in SVG format — not a static screenshot. The `non-interactive.svg` shows a real scan running, complete with `🐷🔑🐷` emoji output and an AWS key being found. This is the single most copied pattern — an animated demo that requires zero user imagination.

### Copy structure

```
1. Logo + tagline (one line: "Find leaked credentials.")
2. Badges (Go report, licence, detector count)
3. "Now Scanning" — logo grid of credential source integrations
4. Enterprise upsell (2 sentences)
5. What is TruffleHog — 4 sub-sections with emoji headers:
   Discovery 🔍 / Classification 📁 / Validation ✅ / Analysis 🔬
6. Community join (Slack/Discord)
7. Demo (animated SVG)
8. Installation (6 methods: brew, Docker, binary, source, script, verified script)
9. Quick Start (numbered: 1-19 examples, each a code block)
10. GitHub Action section — minimal quickstart YAML, then "Advanced Usage"
11. Inputs table (inline with the action section)
12. FAQ
```

### Quickstart YAML pattern

Placed **inside the main README** under `## TruffleHog Github Action`, not in a separate file. The minimal version is 10 lines. The `extra_args` pattern lets them keep the inputs table short while still showing power users the flags.

```yaml
- name: Secret Scanning
  uses: trufflesecurity/trufflehog@main
  with:
    extra_args: --results=verified,unknown
```

### Inputs table

Not exposed via `action.yml` — kept minimal (`path`, `base`, `head`, `extra_args`, `version`, `image`). The power is in the CLI flags passed via `extra_args`, which lets them show CLI depth without bloating the action inputs table. This is a deliberate pattern to keep the action surface small.

---

## 2. Trivy Action

**Repo:** `aquasecurity/trivy-action`
**Marketplace listing:** `aqua-security-trivy`
**Stars:** ~1.3k (action) / ~32k (trivy tool)

### Visual assets

| Asset | Type | Placement |
|---|---|---|
| `docs/images/trivy-action.png` | Static PNG, full-width | Immediately after the H1 title + badges, before Table of Contents |
| No GIFs or animated SVGs | — | — |
| Badges: Release, Marketplace, Licence | Shield.io badges | H2 header row, top of README |

**Key observation:** Trivy Action uses exactly one image — a banner-style diagram (`trivy-action.png`, width unspecified but renders full-width) placed in the first visible scroll position after the headline badges. Everything below is YAML code blocks with inline prose. No screenshots of output. The image appears to be an architecture/flow diagram showing what Trivy scans.

The **Table of Contents** (with anchor links) immediately follows the banner image and is the second structural element. This is unusual for a security action but makes sense for a README with 15+ named use case sections.

### Copy structure

```
1. H1 title + release/marketplace/licence badges
2. Banner image (docs/images/trivy-action.png)
3. Table of Contents (anchor links to 15 sub-sections)
4. ## Usage
   — Sub-sections: Scan CI Pipeline / with Config / Cache / Trivy Setup / Tarball /
     Templates / GitHub Code Scanning / Git repo / rootfs / IaC / SBOM /
     Private registry (Docker Hub, ECR, GCR, self-hosted) / No code scanning
5. ## Customizing
   — Inputs table (30 rows with Name / Type / Default / Description)
   — Environment variables (link out)
   — Trivy config file (link out)
```

### Quickstart YAML pattern

Two YAML blocks are shown back-to-back at the top of the Usage section — one minimal (image scan), one with config file. This "minimal then advanced" pairing is a conversion pattern: the minimal block is copy-pasteable in under a minute; the config file version signals extensibility.

```yaml
# Minimal
- name: Run Trivy vulnerability scanner
  uses: aquasecurity/trivy-action@v0.36.0
  with:
    image-ref: 'docker.io/my-organization/my-app:${{ github.sha }}'
    format: 'table'
    exit-code: '1'
    ignore-unfixed: true
    vuln-type: 'os,library'
    severity: 'CRITICAL,HIGH'
```

### Inputs table

**30 inputs** exposed in `action.yml` and mirrored as a table in the README. Columns: `Name | Type | Default | Description`. The Default column is particularly effective — developers can read only the Name and Default columns to understand what happens with zero configuration.

---

## 3. Gitleaks Action

**Repo:** `gitleaks/gitleaks-action`
**Marketplace listing:** `gitleaks`
**Stars:** ~18k (gitleaks CLI tool)

### Visual assets

| Asset | Type | Placement |
|---|---|---|
| ASCII art "logo" in code block | Monospace text art | Top of README, before any badges |
| `protected by gitleaks` badge SVG | Shield.io badge | Below ASCII art — the badge is itself a marketing asset |
| GIF demo link | Hosted on GitHub assets | Linked (not embedded) in the intro paragraph |
| PNG screenshot link | Hosted on GitHub assets | Linked (not embedded) in the intro paragraph |

**Key observation:** Gitleaks does NOT embed images directly in the README — they link to a GIF and a PNG hosted on `user-images.githubusercontent.com`. This is a weaker visual pattern than TruffleHog's embedded SVG but the **badge-as-social-proof** pattern is worth copying: the `![gitleaks badge]` snippet in the README invites users to display "protected by gitleaks" on their own READMEs, which creates viral distribution.

The ASCII art at the top is a distinctive brand device — no one mistakes this for a corporate tool.

### Copy structure

```
1. ASCII art logo (in a code block)
2. "protected by gitleaks" badge + link to badge copy snippet
3. Paragraph: what it is + links to demos (GIF + PNG external) + blog
4. ## Usage Example (YAML — minimal, 15 lines)
5. Horizontal rule
6. ### Environment Variables (bullet list, 6 variables)
7. Horizontal rule
8. ## Questions (FAQ — 6 questions as H3 headers)
9. ## License Change
10. ## Contributing
```

**What's missing:** No inputs table, no explicit outputs section, no architecture diagram. This is the leanest README of the four — a deliberate choice for a tool that should feel "simple" vs enterprise.

### Quickstart YAML pattern

The most minimal of all four — just 16 lines including a nightly schedule cron. The `env` block with `GITHUB_TOKEN` and `GITLEAKS_LICENSE` is the entire configuration surface.

```yaml
- uses: gitleaks/gitleaks-action@v2
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    GITLEAKS_LICENSE: ${{ secrets.GITLEAKS_LICENSE}}
```

Note: inputs are controlled via `env:` not `with:`, which is atypical. They explicitly document each `env` variable rather than `inputs`.

---

## 4. Bearer Action

**Repo:** `Bearer/bearer-action`
**Marketplace listing:** `bearer`
**Stars:** ~2k (action repo)

### Visual assets

None. The Bearer Action README has zero images. No banner, no GIF, no diagram.

**Key observation:** Bearer compensates with code density — the README is almost entirely YAML examples. There are 5 different named workflow variants (basic, custom values, full reporting, PR diff, Reviewdog integration, Defect Dojo integration). The quantity of named examples serves as a proxy for credibility.

### Copy structure

```
1. H1 title + one-line description
2. ## Example usage
   — Using defaults (2-line YAML)
   — Using custom values for inputs (multi-parameter YAML)
   — Full Reporting Example (full job YAML)
   — Pull Request Diff (diff: true pattern)
   — Using Reviewdog for PR review comments
   — Using Defect Dojo to monitor findings
3. ## Inputs (bullet list, one per input with description)
4. ## Outputs (2 outputs: rule_breaches, exit_code)
```

### Quickstart YAML pattern

Two-line. The fastest first-run pattern of all four:

```yaml
- uses: actions/checkout@v3
- uses: bearer/bearer-action@v2
```

No required inputs. This is the "zero-config" conversion hook — you can add the action in 30 seconds and it works. Advanced configuration is shown after.

### Inputs/outputs format

Bearer uses a **prose bullet list**, not a table, for inputs. Each input is `### input-name` + description paragraph. The Outputs section is the only place they use a `###` header per item rather than a table — this makes outputs easy to reference but slightly harder to scan than Trivy's table format.

---

## Cross-cutting patterns to replicate

### Pattern 1: The animated terminal demo is the highest-converting visual asset

TruffleHog's `non-interactive.svg` embedded directly in the README is the single most effective asset across all four. It shows the tool running, shows a real finding, and requires no explanation. GIFs are second-best (Gitleaks links to one but doesn't embed it). Trivy's static banner image is weakest.

**Instruction for ramen-ai-action:** Create an animated SVG or high-quality GIF showing a real ramen-ai scan running in a terminal — include a before/after or finding+block output. Embed it directly in the README (not linked). Place it in the first screen below the headline and badge row.

### Pattern 2: Lead with outcome, then mechanism

Every strong README in this set opens with a 1-line value proposition before any technical detail:
- TruffleHog: *"Find leaked credentials."*
- Gitleaks: *"detecting and preventing hardcoded secrets"*
- Trivy: *"Scans container images for vulnerabilities"*
- Bearer: *"Run Bearer as a GitHub Action"* (weakest — process, not outcome)

**Instruction:** The ramen-ai-action hook line should state what bad thing is prevented (the outcome), not what the action does (the mechanism). E.g. *"Block unsafe AI outputs before they reach users."*

### Pattern 3: Two-tier quickstart — minimal then advanced

All four show a ~5-10 line minimal YAML first, followed by an expanded "Advanced Usage" or named examples. The minimal block should work with only `GITHUB_TOKEN` — no other required secrets.

**Instruction:** Write the minimal quickstart so it runs with zero `with:` inputs (use sensible defaults in `action.yml`). Then add 3-4 named scenarios (PR diff, full report, SARIF upload, fail-on-critical) as separate named H3 sections.

### Pattern 4: The inputs table structure (Trivy model is the gold standard)

Trivy's `Name | Type | Default | Description` table with 30 rows is the most scannable format. The Default column is critical — it communicates what happens with zero configuration, which reduces friction.

**Instruction:** Every input in ramen-ai-action's `action.yml` should have a description, a sensible default, and `required: false` wherever possible. Mirror the table in the README with exactly four columns: `Name | Type | Default | Description`.

### Pattern 5: The badge-as-social-proof and SARIF integration as trust signal

Gitleaks offers a copyable badge snippet. TruffleHog integrates with GitHub Code Scanning (SARIF). Trivy uploads to the GitHub Security tab. These patterns serve the same function: they embed the action's output into GitHub's own security infrastructure, which increases perceived legitimacy.

**Instruction:** Ensure ramen-ai-action outputs SARIF and document `github/codeql-action/upload-sarif` integration explicitly. Optionally offer a `protected by ramen-ai` badge snippet.

### Pattern 6: Env vars vs inputs — document whichever the action uses, not both

Gitleaks uses `env:` not `with:`, and documents this clearly. TruffleHog uses `extra_args` to expose CLI flags without adding action inputs. Choose one pattern and make it visually consistent in every YAML example in the README — mixing `env:` and `with:` in the same example is the fastest way to create support tickets.

---

## Proposed README structure for `ramen-ai-action`

Based on the above, here is the section order to use:

```
1. Logo (if exists) — centred, 120-140px tall
2. H1 title — the action name
3. Tagline — one sentence, outcome-first
4. Badges row: version / licence / marketplace / used-by count
5. [HERO ASSET] Animated SVG or GIF of a real scan — full-width embed
6. ## What it does — 3-4 bullet points using emoji headers, one per capability
7. ## Quick Start (minimal YAML, copy-pasteable, ~10 lines, zero required secrets)
8. ## Usage scenarios
   — PR diff mode
   — SARIF / GitHub Security tab upload
   — Fail on HIGH/CRITICAL
   — Full report as artifact
9. ## Inputs (table: Name | Type | Default | Description)
10. ## Outputs (table or bullet: name + description)
11. ## Configuration (link to extended docs or config file format)
12. ## FAQ (3-5 Q&As as H3s — most common "why is my job failing?" type questions)
13. ## Licence
```

Do not add: architecture diagrams (no one reads them), long "how it works" explainers before the quickstart, or more than 2 levels of nested YAML comments.

---

## Star/adoption benchmarks

For context when evaluating post-launch traction:

| Action | Stars (action repo) | Used by estimate |
|---|---|---|
| trivy-action | ~1.3k | 10,000+ workflow files (per supply chain compromise report) |
| gitleaks-action | ~800 (action repo) / 18k tool | High — nightly scan pattern is widely replicated |
| bearer-action | ~150 | Smaller but growing |
| trufflehog (embedded action) | N/A (same repo) | Used by 10k+ based on marketplace "used by" count |

A security action with 200+ stars and 500+ "used by" repos is considered traction in this space. The first 100 stars typically come from: launch post on Security subreddits / HN / BluePost, listing on awesome-security repos, and appearing in comparison posts like the AppSecSanta comparison above.
