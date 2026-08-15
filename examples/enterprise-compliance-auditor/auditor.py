from __future__ import annotations

import json
import os
import sys
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from ramen_ai import RamenClient

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=False)

LOG_PATH = BASE_DIR / "historical_logs.jsonl"
REPORT_PATH = BASE_DIR / "AUDIT_REPORT.md"
POLICY_UUID_PLACEHOLDER = "<YOUR_POLICY_UUID>"
EXPECTED_LOG_COUNT = 20
EXPECTED_VIOLATION_COUNT = 5
MAX_WORKERS = 5

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


@dataclass(frozen=True)
class HistoricalLog:
    log_id: str
    timestamp: str
    source: str
    channel: str
    user_message: str
    assistant_output: str
    expected_violation: bool


@dataclass(frozen=True)
class AuditResult:
    log: HistoricalLog
    allowed: bool | None
    triggered_policies: tuple[str, ...]
    receipt_kid: str | None
    signature_snippet: str | None
    evidence_error: str | None

    @property
    def status(self) -> str:
        if self.evidence_error:
            return "EVIDENCE FAILURE"
        if self.allowed is False:
            return "VIOLATION DETECTED"
        return "CLEAN"


def load_logs(path: Path = LOG_PATH) -> list[HistoricalLog]:
    logs: list[HistoricalLog] = []
    seen_ids: set[str] = set()

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                raw: dict[str, Any] = json.loads(line)
                log = HistoricalLog(
                    log_id=str(raw["log_id"]),
                    timestamp=str(raw["timestamp"]),
                    source=str(raw["source"]),
                    channel=str(raw["channel"]),
                    user_message=str(raw["user_message"]),
                    assistant_output=str(raw["assistant_output"]),
                    expected_violation=raw["expected_violation"],
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"Invalid JSONL record on line {line_number}: {exc}") from exc

            if not isinstance(log.expected_violation, bool):
                raise ValueError(
                    f"Record {log.log_id!r} has a non-boolean expected_violation value."
                )
            if not log.assistant_output.strip():
                raise ValueError(f"Record {log.log_id!r} has an empty assistant_output.")
            if log.log_id in seen_ids:
                raise ValueError(f"Duplicate log_id: {log.log_id}")

            seen_ids.add(log.log_id)
            logs.append(log)

    expected_violations = sum(log.expected_violation for log in logs)
    if len(logs) != EXPECTED_LOG_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_LOG_COUNT} logs, found {len(logs)} in {path.name}."
        )
    if expected_violations != EXPECTED_VIOLATION_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_VIOLATION_COUNT} simulated violations, "
            f"found {expected_violations}."
        )

    return logs


def _signature_snippet(signature: str | None) -> str | None:
    if not signature:
        return None
    if len(signature) <= 24:
        return signature
    return f"{signature[:14]}…{signature[-8:]}"


def _triggered_policy_labels(data: dict[str, Any]) -> tuple[str, ...]:
    labels: list[str] = []
    raw_results = data.get("results", [])
    if isinstance(raw_results, list):
        for raw_result in raw_results:
            if not isinstance(raw_result, dict):
                continue
            violations = raw_result.get("violations", [])
            if raw_result.get("allowed") is not False and not violations:
                continue
            policy_name = raw_result.get("policy_name")
            policy_id = raw_result.get("policy_id")
            if policy_name and policy_id:
                labels.append(f"{policy_name} ({policy_id})")
            elif policy_name or policy_id:
                labels.append(str(policy_name or policy_id))

    if labels:
        return tuple(dict.fromkeys(labels))

    raw_policy_ids = data.get("policy_ids", [])
    if isinstance(raw_policy_ids, list):
        return tuple(str(policy_id) for policy_id in raw_policy_ids)
    return ()


def evaluate_log(
    client: RamenClient,
    policy_uuid: str,
    log: HistoricalLog,
) -> AuditResult:
    try:
        response = client.evaluate_compliance(
            log.assistant_output,
            policy_ids=[policy_uuid],
            context={
                "log_id": log.log_id,
                "timestamp": log.timestamp,
                "source": log.source,
                "channel": log.channel,
            },
        )

        allowed = response.get("allowed")
        if not isinstance(allowed, bool):
            raise ValueError("SDK response did not contain a boolean allowed verdict.")

        data = response.get("data")
        if not isinstance(data, dict):
            raise ValueError("SDK response did not contain an evaluation data object.")

        receipt = data.get("receipt")
        receipt_kid: str | None = None
        signature: str | None = None
        if isinstance(receipt, dict):
            raw_kid = receipt.get("kid")
            raw_signature = receipt.get("signature")
            receipt_kid = str(raw_kid) if raw_kid else None
            signature = str(raw_signature) if raw_signature else None

        evidence_error: str | None = None
        if not isinstance(receipt, dict):
            alert = response.get("receipt_alert") or data.get("receipt_alert")
            evidence_error = f"Receipt absent{f': {alert}' if alert else '.'}"
        elif response.get("receipt_verified") is not True:
            reason = response.get("receipt_reason") or "SDK receipt verification failed."
            evidence_error = str(reason)
        elif not receipt_kid or not signature:
            evidence_error = "Verified receipt is missing kid or signature evidence."

        return AuditResult(
            log=log,
            allowed=allowed,
            triggered_policies=_triggered_policy_labels(data) if not allowed else (),
            receipt_kid=receipt_kid,
            signature_snippet=_signature_snippet(signature),
            evidence_error=evidence_error,
        )
    except Exception as exc:  # Continue the batch and preserve the row-level failure.
        return AuditResult(
            log=log,
            allowed=None,
            triggered_policies=(),
            receipt_kid=None,
            signature_snippet=None,
            evidence_error=f"{type(exc).__name__}: {exc}",
        )


def _status_line(result: AuditResult, completed: int, total: int) -> str:
    colours = {
        "CLEAN": GREEN,
        "VIOLATION DETECTED": RED,
        "EVIDENCE FAILURE": YELLOW,
    }
    status = result.status
    prefix = colours[status] if sys.stdout.isatty() and "NO_COLOR" not in os.environ else ""
    suffix = RESET if prefix else ""
    return (
        f"[{completed:02d}/{total:02d}] "
        f"{prefix}[{status}]{suffix} {result.log.log_id} "
        f"({result.log.source}/{result.log.channel})"
    )


def run_audit(
    client: RamenClient,
    policy_uuid: str,
    logs: list[HistoricalLog],
) -> list[AuditResult]:
    results: list[AuditResult] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures: dict[Future[AuditResult], HistoricalLog] = {
            executor.submit(evaluate_log, client, policy_uuid, log): log for log in logs
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            log = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # Defensive: evaluate_log already contains failures.
                result = AuditResult(
                    log=log,
                    allowed=None,
                    triggered_policies=(),
                    receipt_kid=None,
                    signature_snippet=None,
                    evidence_error=f"Worker failure: {type(exc).__name__}: {exc}",
                )
            results.append(result)
            print(_status_line(result, completed, len(logs)), flush=True)

    log_order = {log.log_id: index for index, log in enumerate(logs)}
    return sorted(results, key=lambda result: log_order[result.log.log_id])


def _markdown_cell(value: str, limit: int | None = None) -> str:
    compact = " ".join(value.split())
    if limit is not None and len(compact) > limit:
        compact = f"{compact[: limit - 1]}…"
    return compact.replace("|", "\\|").replace("`", "\\`")


def _receipt_evidence(result: AuditResult) -> str:
    if result.evidence_error:
        return f"EVIDENCE FAILURE: {_markdown_cell(result.evidence_error, 100)}"
    return f"kid={result.receipt_kid}; signature={result.signature_snippet}"


def build_report(results: list[AuditResult]) -> str:
    blocked = [result for result in results if result.allowed is False]
    evidence_failures = [result for result in results if result.evidence_error]
    false_positives = sum(
        result.allowed is False and not result.log.expected_violation for result in results
    )
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    lines = [
        "# Enterprise Compliance Audit Report",
        "",
        "> **Classification:** Internal Compliance Evidence",
        f"> **Generated:** {generated_at}",
        "> **Evaluation mode:** Concurrent historical-log review via ramen-ai-core",
        "",
        "## Executive Summary",
        "",
        (
            f"**Total Logs:** {len(results)} | "
            f"**Violations Found:** {len(blocked)} | "
            f"**False Positives:** {false_positives}"
        ),
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Total Logs | {len(results)} |",
        f"| Violations Found | {len(blocked)} |",
        f"| False Positives | {false_positives} |",
        f"| Evidence Failures | {len(evidence_failures)} |",
        "",
        "## Blocked Payloads",
        "",
        "| Log ID | Timestamp | Blocked payload | Triggered policy | Ed25519 receipt evidence |",
        "|---|---|---|---|---|",
    ]

    if blocked:
        for result in blocked:
            policies = "; ".join(result.triggered_policies) or "Policy details unavailable"
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_cell(result.log.log_id),
                        _markdown_cell(result.log.timestamp),
                        _markdown_cell(result.log.assistant_output, 180),
                        _markdown_cell(policies, 120),
                        _receipt_evidence(result),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| None | — | No blocked payloads detected. | — | — |")

    lines.extend(
        [
            "",
            "## Evidence Failures",
            "",
            (
                "Rows in this section completed without verifiable Ed25519 evidence. "
                "They were retained rather than terminating the batch."
            ),
            "",
            "| Log ID | Verdict | Failure |",
            "|---|---|---|",
        ]
    )
    if evidence_failures:
        for result in evidence_failures:
            verdict = (
                "Blocked" if result.allowed is False else "Allowed" if result.allowed else "Unknown"
            )
            lines.append(
                f"| {_markdown_cell(result.log.log_id)} | {verdict} | "
                f"{_markdown_cell(result.evidence_error or 'Unknown evidence failure', 180)} |"
            )
    else:
        lines.append("| None | — | All rows carried SDK-verified receipts. |")

    lines.extend(
        [
            "",
            "## Methodology and Attestation",
            "",
            (
                f"The auditor submitted {len(results)} historical assistant outputs to a single "
                f"ramen-ai client shared across {MAX_WORKERS} concurrent workers. Each verdict was "
                "evaluated against the configured policy UUID. Receipt evidence was accepted only "
                "when the SDK reported successful local verification."
            ),
            "",
            (
                "The `kid` identifies the Ed25519 verification key and the signature snippet "
                "provides a compact reference to the signed receipt. Full receipt material remains "
                "available in the API evaluation record."
            ),
            "",
            "---",
            "",
            "*End of report.*",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(results: list[AuditResult], path: Path = REPORT_PATH) -> None:
    path.write_text(build_report(results), encoding="utf-8")


def main() -> int:
    api_key = os.environ.get("RAMEN_API_KEY", "")
    policy_uuid = os.environ.get("RAMEN_POLICY_UUID", POLICY_UUID_PLACEHOLDER)

    if not api_key:
        print("RAMEN_API_KEY must be set in the environment.", file=sys.stderr)
        return 2
    if policy_uuid == POLICY_UUID_PLACEHOLDER:
        print(
            "Set RAMEN_POLICY_UUID or replace <YOUR_POLICY_UUID> before running the audit.",
            file=sys.stderr,
        )
        return 2

    try:
        logs = load_logs()
    except (OSError, ValueError) as exc:
        print(f"Unable to load historical logs: {exc}", file=sys.stderr)
        return 2

    print(
        f"Starting enterprise compliance audit: {len(logs)} logs, "
        f"{MAX_WORKERS} concurrent workers."
    )
    with RamenClient(api_key) as client:
        results = run_audit(client, policy_uuid, logs)

    write_report(results)
    violations = sum(result.allowed is False for result in results)
    evidence_failures = sum(bool(result.evidence_error) for result in results)
    print(
        f"Audit complete: {violations} violation(s), "
        f"{evidence_failures} evidence failure(s)."
    )
    print(f"Report saved to {REPORT_PATH}")
    return 1 if evidence_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
