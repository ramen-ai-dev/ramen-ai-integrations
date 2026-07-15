/**
 * ramen-ai PR Compliance Interceptor — GitHub Action entry point.
 *
 * Flow:
 *   1. Read the pull request's changed files via the GitHub REST API.
 *   2. Extract added / modified text from prompt-bearing files
 *      (.md, .txt, .py by default — where system prompts & instructions live).
 *   3. Send each file's added text to the ramen-ai PaaS API through the
 *      Node core client (which verifies the V5 Ed25519 receipt locally).
 *   4. On a BLOCKED verdict, fail the CI build via `core.setFailed()`.
 *   5. Post a single PR comment stating the [BLOCKED] verdict, the statutory
 *      anchor, the steering instruction, and the Ed25519 receipt signature.
 *
 * Fail-closed: an evaluation/transport error is treated as a build failure,
 * never a silent pass — this is a security gate.
 */

import * as core from "@actions/core";
import * as github from "@actions/github";
import { RamenClient, type ComplianceVerdict } from "@ramen-ai/node-core";

/** A blocked finding for one changed file. */
interface BlockedFinding {
  file: string;
  verdict: ComplianceVerdict;
}

/** An evaluation that failed (transport/parse error) for one changed file. */
interface ErroredFinding {
  file: string;
  error: string;
}

/** Parse a comma-separated input into a trimmed, non-empty list. */
function parseCsv(raw: string): string[] {
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

/**
 * Extract added/modified text from a unified-diff `patch`. Returns only the
 * content of added lines (those starting with a single `+`), with the leading
 * `+` removed. Hunk headers (`+++`) are ignored.
 */
function extractAddedText(patch: string | undefined): string {
  if (!patch) return "";
  const added: string[] = [];
  for (const line of patch.split("\n")) {
    if (line.startsWith("+") && !line.startsWith("+++")) {
      added.push(line.slice(1));
    }
  }
  return added.join("\n").trim();
}

/** True when `filename` ends with one of the configured extensions. */
function isScannableFile(filename: string, extensions: string[]): boolean {
  const lower = filename.toLowerCase();
  return extensions.some((ext) => lower.endsWith(ext));
}

/** Render the aggregated block report as a Markdown PR comment. */
function renderComment(
  blocked: BlockedFinding[],
  errored: ErroredFinding[],
  failOnUnverifiedReceipt: boolean,
): string {
  const lines: string[] = [];
  lines.push("## 🛑 ramen-ai Compliance Firewall — **[BLOCKED]**");
  lines.push("");
  lines.push(
    "This pull request introduces changes that the ramen-ai L2 Semantic Firewall " +
      "evaluated as **non-compliant**. The CI build has been failed. Each finding " +
      "below is backed by a self-describing Ed25519 cryptographic receipt.",
  );
  lines.push("");

  for (const { file, verdict } of blocked) {
    const receipt = verdict.receipt;
    const anchors = verdict.statutoryAnchors.length
      ? verdict.statutoryAnchors.join(", ")
      : "_none reported_";
    const steering = verdict.steering ?? "_no steering instruction provided_";
    const verifiedBadge = verdict.receiptVerified
      ? "✅ verified"
      : `⚠️ UNVERIFIED (${verdict.receiptReason ?? verdict.receiptAlert ?? "no receipt"})`;

    lines.push(`### \`${file}\``);
    lines.push("");
    lines.push(`- **Verdict:** \`[BLOCKED]\``);
    lines.push(`- **Statutory anchor(s):** ${anchors}`);
    lines.push(`- **Steering instruction:**`);
    lines.push("");
    lines.push("  > " + steering.replace(/\n/g, "\n  > "));
    lines.push("");
    lines.push(`- **Ed25519 receipt:** ${verifiedBadge}`);
    if (receipt) {
      lines.push(
        `  - kid: \`${receipt.kid}\` · id: \`${receipt.id}\` · schema: \`${receipt.schema_version}\``,
      );
      lines.push("  - signature:");
      lines.push("");
      lines.push("    ```");
      lines.push("    " + receipt.signature);
      lines.push("    ```");
    } else {
      lines.push("  - _no receipt returned by the API for this evaluation_");
    }
    lines.push("");
  }

  if (errored.length) {
    lines.push("### ⚠️ Evaluations that could not complete (fail-closed)");
    lines.push("");
    for (const { file, error } of errored) {
      lines.push(`- \`${file}\`: ${error}`);
    }
    lines.push("");
    if (failOnUnverifiedReceipt) {
      lines.push(
        "_These files could not be evaluated and were treated as blocking failures._",
      );
      lines.push("");
    }
  }

  lines.push("---");
  lines.push(
    "<sub>Posted by the ramen-ai PR Compliance Interceptor. " +
      "Each receipt is independently verifiable against the published Ed25519 public key.</sub>",
  );
  return lines.join("\n");
}

async function run(): Promise<void> {
  const apiKey = core.getInput("ramen_api_key", { required: true });
  const bundleIds = parseCsv(core.getInput("bundle_ids"));
  const policyIds = parseCsv(core.getInput("policy_ids"));
  const githubToken =
    core.getInput("github_token") ||
    process.env.GITHUB_TOKEN ||
    "";

  if (!githubToken) {
    core.setFailed(
      "No GitHub token available. Pass `github_token: ${{ secrets.GITHUB_TOKEN }}` " +
        "explicitly in your workflow's `with:` block, or ensure the GITHUB_TOKEN " +
        "environment variable is present in the runner.",
    );
    return;
  }
  const baseUrl = core.getInput("base_url").trim();
  const providerKey = core.getInput("provider_key").trim() || undefined;
  const extensions = parseCsv(core.getInput("file_extensions")).map((e) =>
    e.startsWith(".") ? e.toLowerCase() : `.${e.toLowerCase()}`,
  );
  const failOnUnverifiedReceipt =
    (core.getInput("fail_on_unverified_receipt") || "true").toLowerCase() !== "false";

  if (bundleIds.length === 0 && policyIds.length === 0) {
    core.setFailed(
      "Configuration error: provide at least one of `bundle_ids` or `policy_ids`. " +
        "The ramen-ai evaluation cannot run without a policy target.",
    );
    return;
  }

  const { context } = github;
  const pr = context.payload.pull_request;
  if (!pr) {
    core.warning(
      `This action only runs on pull_request events (current event: ${context.eventName}). Skipping.`,
    );
    return;
  }

  const octokit = github.getOctokit(githubToken);
  const { owner, repo } = context.repo;
  const pullNumber = pr.number;

  core.info(`Scanning PR #${pullNumber} in ${owner}/${repo}`);

  // 1. Read the PR's changed files (paginated).
  const files = await octokit.paginate(octokit.rest.pulls.listFiles, {
    owner,
    repo,
    pull_number: pullNumber,
    per_page: 100,
  });

  // 2. Keep prompt-bearing files that have added text.
  const scanTargets: { file: string; text: string }[] = [];
  for (const f of files) {
    if (f.status === "removed") continue;
    if (!isScannableFile(f.filename, extensions)) continue;
    const text = extractAddedText(f.patch);
    if (text.length === 0) continue;
    scanTargets.push({ file: f.filename, text });
  }

  if (scanTargets.length === 0) {
    core.info(
      `No added/modified text in scannable files (${extensions.join(", ")}). Nothing to evaluate.`,
    );
    return;
  }
  core.info(`Evaluating ${scanTargets.length} changed file(s) against ramen-ai.`);

  // 3. Evaluate each target through the Node core client.
  const client = new RamenClient({
    apiKey,
    ...(baseUrl ? { baseUrl } : {}),
    ...(providerKey ? { providerKey } : {}),
  });

  const blocked: BlockedFinding[] = [];
  const errored: ErroredFinding[] = [];

  for (const { file, text } of scanTargets) {
    try {
      const verdict = await client.evaluateCompliance(text, {
        ...(bundleIds.length ? { bundleIds } : {}),
        ...(policyIds.length ? { policyIds } : {}),
      });

      // Fail-closed on evidence: a BLOCKED verdict whose receipt cannot be
      // verified is still a block; an allowed verdict with an unverifiable
      // receipt is escalated to a block only when configured to do so.
      const blockedByPolicy = !verdict.allowed;
      const blockedByEvidence =
        verdict.allowed &&
        failOnUnverifiedReceipt &&
        verdict.receipt !== undefined &&
        !verdict.receiptVerified;

      if (blockedByPolicy || blockedByEvidence) {
        core.error(
          `[BLOCKED] ${file} — anchors: ${
            verdict.statutoryAnchors.join(", ") || "none"
          } — receipt verified: ${verdict.receiptVerified}`,
        );
        blocked.push({ file, verdict });
      } else {
        core.info(`[ALLOWED] ${file}`);
      }
    } catch (err) {
      const message = (err as Error).message;
      core.error(`[ERROR] ${file} — evaluation failed: ${message}`);
      errored.push({ file, error: message });
    }
  }

  const hardFailures = errored.length > 0 && failOnUnverifiedReceipt;

  // 4 & 5. If anything blocked (or fail-closed errors), comment and fail.
  if (blocked.length > 0 || hardFailures) {
    const body = renderComment(blocked, errored, failOnUnverifiedReceipt);
    try {
      await octokit.rest.issues.createComment({
        owner,
        repo,
        issue_number: pullNumber,
        body,
      });
      core.info("Posted compliance verdict comment on the pull request.");
    } catch (err) {
      core.warning(`Could not post PR comment: ${(err as Error).message}`);
    }

    core.setOutput("blocked", "true");
    core.setOutput("blocked_count", String(blocked.length));
    core.setFailed(
      `ramen-ai firewall BLOCKED this pull request: ${blocked.length} non-compliant file(s)` +
        (hardFailures ? `, ${errored.length} file(s) could not be evaluated (fail-closed).` : "."),
    );
    return;
  }

  core.setOutput("blocked", "false");
  core.setOutput("blocked_count", "0");
  core.info("✅ ramen-ai firewall: all scanned changes are compliant.");
}

run().catch((err) => {
  core.setFailed(`ramen-ai PR Compliance Interceptor crashed: ${(err as Error).message}`);
});
