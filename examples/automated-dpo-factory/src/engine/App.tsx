import { useEffect, useMemo, useRef, useState } from "react";
import { demoConfig, scenarios } from "../shared/content";
import type { DpoRecord, GovernedBlockedData, GovernedCompleteData, StatusData } from "../shared/schemas";
import { ComparisonCards } from "./components/ComparisonCards";
import { AttemptTrace, DatasetLab, GlassBreakCascade, HealingTrail } from "./components/DetailPanels";
import { StatusStreamer } from "./components/StatusStreamer";
import { extractDpoRecords, runLiveScenario } from "./run";

type Terminal = "idle" | "running" | "complete" | "blocked" | "error";
type DetailTab = "attempts" | "healing" | "dataset";
type WorkspaceTab = "compare" | "outcome" | "evidence";

interface RunState {
  terminal: Terminal;
  statuses: StatusData[];
  complete?: GovernedCompleteData;
  blocked?: GovernedBlockedData;
  error?: string;
}

const initialRun: RunState = { terminal: "idle", statuses: [] };

export function App() {
  const [scenarioId, setScenarioId] = useState(scenarios[0]?.id ?? "");
  const [swapped, setSwapped] = useState(false);
  const [runState, setRunState] = useState<RunState>(initialRun);
  const [records, setRecords] = useState<DpoRecord[]>([]);
  const [detailTab, setDetailTab] = useState<DetailTab>("attempts");
  const [workspaceTab, setWorkspaceTab] = useState<WorkspaceTab>("compare");
  const controllerRef = useRef<AbortController | undefined>(undefined);

  const scenario = useMemo(
    () => scenarios.find((item) => item.id === scenarioId) ?? scenarios[0],
    [scenarioId],
  );
  const result = runState.complete ?? runState.blocked;

  useEffect(() => () => controllerRef.current?.abort(), []);

  const chooseScenario = (nextId: string) => {
    if (runState.terminal === "running") return;
    setScenarioId(nextId);
    setRunState(initialRun);
    setSwapped(false);
    setWorkspaceTab("compare");
  };

  const resetRun = () => {
    const controller = controllerRef.current;
    controllerRef.current = undefined;
    controller?.abort();
    setRunState(initialRun);
    setWorkspaceTab("compare");
  };

  const startRun = async () => {
    if (!scenario || runState.terminal === "running") return;

    const controller = new AbortController();
    controllerRef.current = controller;
    setRunState({ terminal: "running", statuses: [] });
    setWorkspaceTab("compare");

    try {
      const stream = runLiveScenario(scenario.id, controller.signal);

      for await (const event of stream) {
        if (controllerRef.current !== controller) return;
        if (event.event === "heartbeat") continue;
        if (event.event === "status") {
          setRunState((current) => {
            const last = current.statuses.at(-1);
            const duplicate = last?.stage === event.data.stage && last.attempt === event.data.attempt && last.violations === event.data.violations;
            return duplicate ? current : { ...current, statuses: [...current.statuses, event.data] };
          });
          continue;
        }
        if (event.event === "complete") {
          const completion = event.data.data;
          setRunState((current) => ({ ...current, terminal: "complete", complete: completion }));
          const extracted = extractDpoRecords(scenario, completion);
          if (extracted.length > 0) {
            setRecords((current) => [...current, ...extracted]);
            setDetailTab("dataset");
          } else {
            setDetailTab("attempts");
          }
          setWorkspaceTab("outcome");
          continue;
        }
        if (event.event === "blocked") {
          setRunState((current) => ({ ...current, terminal: "blocked", blocked: event.data.data }));
          setDetailTab("healing");
          setWorkspaceTab("outcome");
          continue;
        }
        setRunState((current) => ({ ...current, terminal: "error", error: event.data.error.message }));
      }
    } catch (error) {
      if (controllerRef.current !== controller) return;
      const cancelled = error instanceof DOMException && error.name === "AbortError";
      setRunState((current) => ({
        ...current,
        terminal: "error",
        error: cancelled ? "Run cancelled before completion." : error instanceof Error ? error.message : "The governed run failed.",
      }));
    } finally {
      if (controllerRef.current === controller) controllerRef.current = undefined;
    }
  };

  if (!scenario) return <main className="fatal-state">No configured scenarios are available.</main>;

  const canRun = runState.terminal !== "running";
  const rejectedCount = result?.attempt_metadata.filter((item) => !item.allowed).length ?? 0;
  const terminalLabel = runState.terminal === "complete"
    ? "Approved"
    : runState.terminal === "blocked"
      ? "Blocked"
      : runState.terminal === "running"
        ? "Running"
        : runState.terminal === "error"
          ? "Interrupted"
          : "Ready";

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#workspace" aria-label="ramen ai demo home">
          <img src={demoConfig.brand.logoPath} alt="" />
          <span>{demoConfig.brand.name}</span>
        </a>
        <div className="topbar__meta"><span>Foundry Template</span><span className="topbar__dot" /><span>{demoConfig.showcaseLabel}</span></div>
        <a className="github-link" href="https://github.com/ramen-ai-dev/ramen-ai-integrations" target="_blank" rel="noreferrer">Open-source scaffold ↗</a>
      </header>

      <section className="intro-strip" aria-labelledby="demo-title">
        <div>
          <span className="kicker">{demoConfig.eyebrow}</span>
          <h1 id="demo-title">{demoConfig.title}</h1>
          <p>{demoConfig.description}</p>
        </div>
        <ul className="trust-list" aria-label="Security characteristics">
          <li>Server-side credentials</li>
          <li>Synthetic data</li>
          <li>No persistence</li>
          <li>Governed streaming</li>
        </ul>
      </section>

      <main className="workspace" id="workspace">
        <aside className="control-rail" aria-label="Demo controls">
          <div className="rail-section live-pipeline">
            <span className="rail-label">Execution</span>
            <div><span className="status-light status-light--live" /><strong>Live governed endpoint</strong></div>
            <small>No fixture or expected result is bundled.</small>
          </div>

          <div className="rail-section rail-section--scenarios">
            <div className="rail-heading"><span className="rail-label">Scenario</span><small>{scenarios.length} inputs</small></div>
            <div className="scenario-list">
              {scenarios.map((item, index) => (
                <button type="button" className={item.id === scenario.id ? "scenario-button scenario-button--active" : "scenario-button"} onClick={() => chooseScenario(item.id)} key={item.id}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <div><strong>{item.title}</strong><small>{item.context}</small></div>
                  <em className="path">live</em>
                </button>
              ))}
            </div>
            <p className="scenario-summary">{scenario.summary}</p>
          </div>

          <div className="rail-actions">
            {runState.terminal === "running" ? <button className="button button--danger" type="button" onClick={() => controllerRef.current?.abort()}>Cancel</button> : <button className="button button--quiet" type="button" onClick={resetRun} disabled={runState.terminal === "idle"}>Reset</button>}
            <button className="button button--run" type="button" disabled={!canRun} onClick={startRun}><span>{runState.terminal === "running" ? "Running…" : "Run live cascade"}</span><b aria-hidden="true">→</b></button>
          </div>
          <p className="rail-footnote">The Worker accepts only configured scenario IDs and fixed generation limits.</p>
        </aside>

        <section className="workspace-stage" aria-label="Governed comparison workspace">
          <div className="workspace-toolbar">
            <div className="workspace-tabs" aria-label="Workspace view">
              <button type="button" aria-pressed={workspaceTab === "compare"} className={workspaceTab === "compare" ? "active" : ""} onClick={() => setWorkspaceTab("compare")}>Compare</button>
              <button type="button" aria-pressed={workspaceTab === "outcome"} className={workspaceTab === "outcome" ? "active" : ""} onClick={() => setWorkspaceTab("outcome")}>Outcome {result ? <span>1</span> : null}</button>
              <button type="button" aria-pressed={workspaceTab === "evidence"} className={workspaceTab === "evidence" ? "active" : ""} onClick={() => setWorkspaceTab("evidence")}>Evidence <span>{records.length + rejectedCount}</span></button>
            </div>
            <div className={`run-state run-state--${runState.terminal}`}><i />{terminalLabel}</div>
          </div>

          <StatusStreamer statuses={runState.statuses} terminal={runState.terminal} />
          {runState.error ? <div className="error-banner" role="alert"><strong>Run failed</strong><span>{runState.error}</span></div> : null}

          <div className="workspace-content">
            {workspaceTab === "compare" ? (
              <ComparisonCards scenario={scenario} swapped={swapped} onSwap={() => setSwapped((value) => !value)} />
            ) : null}

            {workspaceTab === "outcome" ? (
              result ? <GlassBreakCascade result={result} /> : <div className="workspace-empty"><span>Live L2 interception</span><h2>Run the governed comparison.</h2><p>The rejected attempt, policy steering, and verified output will appear here directly from the terminal event.</p><button className="button button--primary" type="button" disabled={!canRun} onClick={startRun}>Run now</button></div>
            ) : null}

            {workspaceTab === "evidence" ? (
              <section className="detail-section" aria-labelledby="details-heading">
                <h2 id="details-heading" className="sr-only">Governance evidence</h2>
                <div className="tabs" aria-label="Governance evidence views">
                  <button type="button" aria-pressed={detailTab === "attempts"} className={detailTab === "attempts" ? "active" : ""} onClick={() => setDetailTab("attempts")}>Attempt Trace <span>{result?.attempt_metadata.length ?? 0}</span></button>
                  <button type="button" aria-pressed={detailTab === "healing"} className={detailTab === "healing" ? "active" : ""} onClick={() => setDetailTab("healing")}>Healing Trail <span>{rejectedCount}</span></button>
                  <button type="button" aria-pressed={detailTab === "dataset"} className={detailTab === "dataset" ? "active" : ""} onClick={() => setDetailTab("dataset")}>Dataset Lab <span>{records.length}</span></button>
                </div>
                <div className="tab-panel">
                  {detailTab === "attempts" ? <AttemptTrace result={result} /> : null}
                  {detailTab === "healing" ? <HealingTrail result={result} /> : null}
                  {detailTab === "dataset" ? <DatasetLab records={records} onClear={() => setRecords([])} /> : null}
                </div>
              </section>
            ) : null}
          </div>
        </section>
      </main>
    </div>
  );
}
