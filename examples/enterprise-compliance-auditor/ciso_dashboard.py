from __future__ import annotations

import json
import os
import sys
from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from ramen_ai import RamenClient
from rich.align import Align
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

BASE_DIR = Path(__file__).resolve().parent
LOG_PATH = BASE_DIR / "ciso_logs.jsonl"
DEFAULT_BUNDLE_ID = "ramen__shield_core_it"
POLICY_UUID_PLACEHOLDER = "<YOUR_POLICY_UUID>"
EXPECTED_LOG_COUNT = 1_000
EXPECTED_MALICIOUS_COUNT = 50
DEFAULT_MAX_WORKERS = 5
DEFAULT_MAX_EVALUATIONS = 200


def _provider_credentials() -> tuple[str | None, str | None]:
    provider_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not provider_key or provider_key == "sk-...":
        return None, None
    return provider_key, "openai"


@dataclass(frozen=True)
class ToolCall:
    log_id: str
    timestamp: str
    source: str
    tool_name: str
    payload: str
    malicious: bool
    expected_rule_set: str | None


@dataclass(frozen=True)
class EvaluationResult:
    tool_call: ToolCall
    allowed: bool | None
    triggered_rules: tuple[str, ...]
    steering: str | None
    verified_receipt_kid: str | None
    evidence_error: str | None


@dataclass
class DashboardState:
    total: int
    scope_label: str
    completed: int = 0
    allowed: int = 0
    blocked: int = 0
    evidence_failures: int = 0
    triggered_rule_counts: Counter[str] = field(default_factory=Counter)
    latest_threat: EvaluationResult | None = None

    def record(self, result: EvaluationResult) -> None:
        self.completed += 1
        if result.allowed is True:
            self.allowed += 1
        elif result.allowed is False:
            self.blocked += 1
            for rule in result.triggered_rules or ("Unspecified policy rule",):
                self.triggered_rule_counts[rule] += 1
            self.latest_threat = result
        if result.evidence_error:
            self.evidence_failures += 1


def load_tool_calls(path: Path = LOG_PATH) -> list[ToolCall]:
    tool_calls: list[ToolCall] = []
    seen_ids: set[str] = set()

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                raw: dict[str, Any] = json.loads(line)
                tool_call = ToolCall(
                    log_id=str(raw["log_id"]),
                    timestamp=str(raw["timestamp"]),
                    source=str(raw["source"]),
                    tool_name=str(raw["tool_name"]),
                    payload=str(raw["payload"]),
                    malicious=raw["malicious"],
                    expected_rule_set=(
                        str(raw["expected_rule_set"])
                        if raw.get("expected_rule_set") is not None
                        else None
                    ),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"Invalid JSONL record on line {line_number}: {exc}") from exc

            if not isinstance(tool_call.malicious, bool):
                raise ValueError(f"Record {tool_call.log_id!r} has a non-boolean malicious flag.")
            if not tool_call.payload.strip():
                raise ValueError(f"Record {tool_call.log_id!r} has an empty payload.")
            if tool_call.log_id in seen_ids:
                raise ValueError(f"Duplicate log_id: {tool_call.log_id}")
            seen_ids.add(tool_call.log_id)
            tool_calls.append(tool_call)

    malicious_count = sum(tool_call.malicious for tool_call in tool_calls)
    if len(tool_calls) != EXPECTED_LOG_COUNT:
        raise ValueError(f"Expected {EXPECTED_LOG_COUNT} logs, found {len(tool_calls)}.")
    if malicious_count != EXPECTED_MALICIOUS_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_MALICIOUS_COUNT} malicious logs, found {malicious_count}."
        )
    return tool_calls


def _normalise_rule_label(label: str) -> str:
    compact = " ".join(label.split())
    lowered = compact.lower().replace("-", "").replace("_", "").replace(" ", "")
    if "asi06" in lowered or "indirectpromptinjection" in lowered:
        return "OWASP ASI06"
    if "secretexfiltration" in lowered or "credentialexfiltration" in lowered:
        return "Secret Exfiltration"
    if "destructiveexecution" in lowered or "infrastructureabuse" in lowered:
        return "Destructive Execution"
    return compact


def _triggered_rules(data: dict[str, Any]) -> tuple[str, ...]:
    labels: list[str] = []
    anchors = data.get("statutory_anchors")
    if isinstance(anchors, list):
        labels.extend(str(anchor) for anchor in anchors if anchor)

    raw_results = data.get("results")
    if isinstance(raw_results, list):
        for raw_result in raw_results:
            if not isinstance(raw_result, dict):
                continue
            violations = raw_result.get("violations")
            if raw_result.get("allowed") is not False and not violations:
                continue
            policy_name = raw_result.get("policy_name")
            policy_id = raw_result.get("policy_id")
            if policy_name:
                labels.append(str(policy_name))
            elif policy_id:
                labels.append(str(policy_id))

    normalised = (_normalise_rule_label(label) for label in labels if label.strip())
    return tuple(dict.fromkeys(normalised))


def evaluate_tool_call(
    client: RamenClient,
    scope: dict[str, list[str]],
    tool_call: ToolCall,
    *,
    provider_key: str | None = None,
    provider_name: str | None = None,
) -> EvaluationResult:
    try:
        response = client.evaluate_compliance(
            tool_call.payload,
            context={
                "log_id": tool_call.log_id,
                "timestamp": tool_call.timestamp,
                "source": tool_call.source,
                "tool_name": tool_call.tool_name,
            },
            provider_key=provider_key,
            provider_name=provider_name,
            **scope,
        )
        allowed = response.get("allowed")
        if not isinstance(allowed, bool):
            raise ValueError("SDK response did not contain a boolean allowed verdict.")

        data = response.get("data")
        if not isinstance(data, dict):
            raise ValueError("SDK response did not contain an evaluation data object.")

        receipt = data.get("receipt")
        verified_receipt_kid: str | None = None
        evidence_error: str | None = None
        if response.get("receipt_verified") is True and isinstance(receipt, dict):
            raw_kid = receipt.get("kid")
            if raw_kid:
                verified_receipt_kid = str(raw_kid)
            else:
                evidence_error = "Verified receipt is missing its kid."
        elif not isinstance(receipt, dict):
            alert = response.get("receipt_alert") or data.get("receipt_alert")
            evidence_error = f"Receipt absent{f': {alert}' if alert else '.'}"
        else:
            reason = response.get("receipt_reason") or "SDK receipt verification failed."
            evidence_error = str(reason)

        raw_steering = response.get("steering")
        steering = str(raw_steering) if raw_steering else None
        return EvaluationResult(
            tool_call=tool_call,
            allowed=allowed,
            triggered_rules=_triggered_rules(data) if not allowed else (),
            steering=steering,
            verified_receipt_kid=verified_receipt_kid,
            evidence_error=evidence_error,
        )
    except Exception as exc:
        return EvaluationResult(
            tool_call=tool_call,
            allowed=None,
            triggered_rules=(),
            steering=None,
            verified_receipt_kid=None,
            evidence_error=f"{type(exc).__name__}: {exc}",
        )


def _progress_panel(state: DashboardState) -> Panel:
    progress = Progress(
        TextColumn("[bold cyan]Evaluations"),
        BarColumn(bar_width=None, complete_style="bright_cyan", finished_style="green"),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        expand=True,
    )
    task_id = progress.add_task("CISO audit", total=state.total, completed=state.completed)
    progress.update(task_id, completed=state.completed)
    summary = Text(
        f"{state.completed:,}/{state.total:,} complete  •  "
        f"{state.total - state.completed:,} in flight or queued",
        style="dim",
    )
    return Panel(Group(progress, Align.center(summary)), title="Progress Panel", border_style="cyan")


def _threat_matrix_panel(state: DashboardState) -> Panel:
    table = Table(expand=True, box=None, show_header=True, header_style="bold white")
    table.add_column("Decision / Trigger", ratio=4)
    table.add_column("Count", justify="right", ratio=1)
    table.add_row("[green][ALLOWED][/green]", f"[green]{state.allowed:,}[/green]")
    table.add_row("[bold red][BLOCKED][/bold red]", f"[bold red]{state.blocked:,}[/bold red]")
    table.add_row("[yellow]Evidence failures[/yellow]", f"[yellow]{state.evidence_failures:,}[/yellow]")
    table.add_section()
    if state.triggered_rule_counts:
        for rule, count in state.triggered_rule_counts.most_common():
            table.add_row(f"  [red]↳ {rule}[/red]", f"[red]{count:,}[/red]")
    else:
        table.add_row("[dim]  Awaiting first intercepted threat[/dim]", "[dim]—[/dim]")
    return Panel(table, title="Threat Matrix", border_style="bright_red")


def _intercept_feed_panel(state: DashboardState) -> Panel:
    threat = state.latest_threat
    if threat is None:
        content = Align.center(
            Text("Scanning agent tool calls — no threats intercepted yet.", style="dim"),
            vertical="middle",
        )
        return Panel(content, title="Live Intercept Feed", border_style="yellow")

    kid = threat.verified_receipt_kid or "UNVERIFIED RECEIPT"
    steering = threat.steering or "No steering instruction returned."
    rules = ", ".join(threat.triggered_rules) or "Unspecified policy rule"
    content = Text()
    content.append("LATEST THREAT CAUGHT\n", style="bold white on red")
    content.append(f"Payload: {threat.tool_call.payload}\n", style="bold red")
    content.append(f"Steering: {steering}\n", style="red")
    content.append(f"Triggered: {rules}\n", style="bright_red")
    content.append(f"Verified Ed25519 kid: {kid}", style="bold red")
    if threat.evidence_error:
        content.append(f"\nEvidence alert: {threat.evidence_error}", style="bold yellow")
    return Panel(content, title="Live Intercept Feed", border_style="bold red")


def render_dashboard(state: DashboardState) -> Layout:
    layout = Layout()
    header = Text(
        f"CISO THREAT MATRIX  •  {state.scope_label}  •  LIVE",
        justify="center",
        style="bold white on dark_red",
    )
    layout.split_column(Layout(header, name="header", size=1), Layout(name="main"))
    layout["main"].split_column(Layout(name="telemetry", ratio=2), Layout(name="feed", ratio=1))
    layout["telemetry"].split_row(Layout(name="progress"), Layout(name="matrix"))
    layout["progress"].update(_progress_panel(state))
    layout["matrix"].update(_threat_matrix_panel(state))
    layout["feed"].update(_intercept_feed_panel(state))
    return layout


def run_evaluations(
    client: RamenClient,
    scope: dict[str, list[str]],
    tool_calls: list[ToolCall],
    max_workers: int,
    on_result: Callable[[EvaluationResult], None],
    *,
    provider_key: str | None = None,
    provider_name: str | None = None,
) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ciso-audit") as executor:
        futures: dict[Future[EvaluationResult], ToolCall] = {
            executor.submit(
                evaluate_tool_call,
                client,
                scope,
                tool_call,
                provider_key=provider_key,
                provider_name=provider_name,
            ): tool_call
            for tool_call in tool_calls
        }
        for future in as_completed(futures):
            tool_call = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = EvaluationResult(
                    tool_call=tool_call,
                    allowed=None,
                    triggered_rules=(),
                    steering=None,
                    verified_receipt_kid=None,
                    evidence_error=f"Worker failure: {type(exc).__name__}: {exc}",
                )
            results.append(result)
            on_result(result)
    return results


def _evaluation_scope() -> tuple[dict[str, list[str]], str]:
    policy_uuid = os.environ.get("RAMEN_POLICY_UUID", "").strip()
    if policy_uuid and policy_uuid != POLICY_UUID_PLACEHOLDER:
        return {"policy_ids": [policy_uuid]}, "configured proxy policy"
    return {"bundle_ids": [DEFAULT_BUNDLE_ID]}, DEFAULT_BUNDLE_ID


def _max_workers() -> int:
    raw_value = os.environ.get("CISO_MAX_WORKERS", str(DEFAULT_MAX_WORKERS))
    try:
        workers = int(raw_value)
    except ValueError as exc:
        raise ValueError("CISO_MAX_WORKERS must be an integer.") from exc
    if not 1 <= workers <= 128:
        raise ValueError("CISO_MAX_WORKERS must be between 1 and 128.")
    return workers


def _max_evaluations() -> int:
    raw_value = os.environ.get("CISO_MAX_EVALUATIONS", str(DEFAULT_MAX_EVALUATIONS))
    try:
        evaluations = int(raw_value)
    except ValueError as exc:
        raise ValueError("CISO_MAX_EVALUATIONS must be an integer.") from exc
    if not 1 <= evaluations <= EXPECTED_LOG_COUNT:
        raise ValueError(
            f"CISO_MAX_EVALUATIONS must be between 1 and {EXPECTED_LOG_COUNT}."
        )
    return evaluations


def main() -> int:
    load_dotenv(dotenv_path=BASE_DIR / ".env", override=False)
    api_key = os.environ.get("RAMEN_API_KEY", "").strip()
    provider_key, provider_name = _provider_credentials()
    if not api_key:
        print("RAMEN_API_KEY must be set in examples/enterprise-compliance-auditor/.env.", file=sys.stderr)
        return 2

    try:
        tool_calls = load_tool_calls()
        max_evaluations = _max_evaluations()
        tool_calls = tool_calls[:max_evaluations]
        max_workers = _max_workers()
    except (OSError, ValueError) as exc:
        print(f"Unable to start CISO dashboard: {exc}", file=sys.stderr)
        return 2

    scope, scope_label = _evaluation_scope()
    state = DashboardState(total=len(tool_calls), scope_label=scope_label)
    console = Console()

    with RamenClient(api_key) as client:
        with Live(
            render_dashboard(state),
            console=console,
            refresh_per_second=12,
            transient=False,
        ) as live:
            def update_dashboard(result: EvaluationResult) -> None:
                state.record(result)
                live.update(render_dashboard(state), refresh=True)

            run_evaluations(
                client,
                scope,
                tool_calls,
                max_workers,
                update_dashboard,
                provider_key=provider_key,
                provider_name=provider_name,
            )

    console.print(
        f"[bold]Audit complete:[/bold] {state.allowed:,} allowed, "
        f"[red]{state.blocked:,} blocked[/red], "
        f"[yellow]{state.evidence_failures:,} evidence failures[/yellow]."
    )
    return 1 if state.evidence_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
