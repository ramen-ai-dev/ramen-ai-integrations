import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { demoConfig, scenarios } from "../shared/content";
import type { DpoRecord, GovernedBlockedData, GovernedCompleteData, StatusData } from "../shared/schemas";
import { ComparisonCards } from "./components/ComparisonCards";
import { AttemptTrace, DatasetLab, HealingTrail, ResponseComparison } from "./components/DetailPanels";
import { StatusStreamer } from "./components/StatusStreamer";
import { TurnstileGate } from "./components/TurnstileGate";
import {
  deleteSession,
  extractDpoRecords,
  getPublicConfig,
  getSession,
  runGuidedScenario,
  runLiveScenario,
  type PublicConfig,
  type RunMode,
  type SessionState,
} from "./run";

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
  const [mode, setMode] = useState<RunMode>("guided");
  const [swapped, setSwapped] = useState(false);
  const [session, setSession] = useState<SessionState>();
  const [publicConfig, setPublicConfig] = useState<PublicConfig>();
  const [configError, setConfigError] = useState<string>();
  const [runState, setRunState] = useState<RunState>(initialRun);
  const [records, setRecords] = useState<DpoRecord[]>([]);
  const [detailTab, setDetailTab] = useState<DetailTab>("attempts");
  const [workspaceTab, setWorkspaceTab] = useState<WorkspaceTab>("compare");
  const controllerRef = useRef<AbortController | undefined>(undefined);
  const suppressSessionRestoreRef = useRef(false);

  const scenario = useMemo(
    () => scenarios.find((item) => item.id === scenarioId) ?? scenarios[0],
    [scenarioId],
  );
  const result = runState.complete ?? runState.blocked;

  useEffect(() => {
    if (mode !== "live" || publicConfig || configError) return;
    let active = true;
    getPublicConfig()
      .then((config) => { if (active) setPublicConfig(config); })
      .catch((error: unknown) => { if (active) setConfigError(error instanceof Error ? error.message : "Live configuration is unavailable"); });
    return () => { active = false; };
  }, [configError, mode, publicConfig]);

  useEffect(() => {
    if (mode !== "live" || session || suppressSessionRestoreRef.current) return;
    let active = true;
    getSession()
      .then((restored) => { if (active && restored) setSession(restored); })
      .catch(() => { /* A failed status probe leaves the verification gate closed. */ });
    return () => { active = false; };
  }, [mode, session]);

  useEffect(() => {
    if (!session) return;
    const timer = window.setInterval(() => {
      if (Date.parse(session.expiresAt) <= Date.now()) setSession(undefined);
    }, 10_000);
    return () => window.clearInterval(timer);
  }, [session]);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const acceptSession = useCallback((next: SessionState) => {
    suppressSessionRestoreRef.current = false;
    setSession(next);
    setRunState(initialRun);
    setWorkspaceTab("compare");
  }, []);

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
    if (mode === "live" && !session) return;

    const controller = new AbortController();
    controllerRef.current = controller;
    setRunState({ terminal: "running", statuses: [] });
    setWorkspaceTab("compare");

    try {
      const stream = mode === "guided"
        ? runGuidedScenario(scenario, controller.signal)
        : runLiveScenario(scenario.id, controller.signal);

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
          const extracted = extractDpoRecords(scenario, completion, mode);
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

  const closeSession = async () => {
    suppressSessionRestoreRef.current = true;
    setSession(undefined);
    resetRun();
    try { await deleteSession(); } catch { /* Local state remains fail-closed; the cookie naturally expires. */ }
  };

  if (!scenario) return <main className="fatal-state">No configured scenarios are available.</main>;

  const canRun = runState.terminal !== "running" && (mode === "guided" || Boolean(session));
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
          <div className="rail-section">
            <span className="rail-label">Mode</span>
            <div className="mode-switch" role="group" aria-label="Run mode">
              <button type="button" className={mode === "guided" ? "active" : ""} onClick={() => setMode("guided")}><span>Guided</span><small>Fixture</small></button>
              <button type="button" className={mode === "live" ? "active" : ""} onClick={() => setMode("live")}><span>Live</span><small>Endpoint</small></button>
            </div>
          </div>

          <div className="rail-section rail-section--scenarios">
            <div className="rail-heading"><span className="rail-label">Scenario</span><small>{scenarios.length} paths</small></div>
            <div className="scenario-list">
              {scenarios.map((item, index) => (
                <button type="button" className={item.id === scenario.id ? "scenario-button scenario-button--active" : "scenario-button"} onClick={() => chooseScenario(item.id)} key={item.id}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <div><strong>{item.title}</strong><small>{item.context}</small></div>
                  <em className={`path path--${item.expectedPath}`}>{item.expectedPath}</em>
                </button>
              ))}
            </div>
            <p className="scenario-summary">{scenario.summary}</p>
          </div>

          <div className="rail-section session-summary">
            {mode === "guided" ? <><span className="session-light session-light--fixture" /><div><strong>Guided fixture</strong><small>No network credentials</small></div></> : session ? <><span className="session-light session-light--live" /><div><strong>Secure session</strong><small>{publicConfig?.burstLimit ?? 5} requests / {publicConfig?.burstWindowSeconds ?? 60}s</small></div><button type="button" onClick={closeSession}>End</button></> : <><span className="session-light" /><div><strong>Verification required</strong><small>Keys stay server-side</small></div></>}
          </div>

          <div className="rail-actions">
            {runState.terminal === "running" ? <button className="button button--danger" type="button" onClick={() => controllerRef.current?.abort()}>Cancel</button> : <button className="button button--quiet" type="button" onClick={resetRun} disabled={runState.terminal === "idle"}>Reset</button>}
            <button className="button button--run" type="button" disabled={!canRun} onClick={startRun}><span>{runState.terminal === "running" ? "Running…" : mode === "live" ? "Run live" : "Run showcase"}</span><b aria-hidden="true">→</b></button>
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
            {mode === "live" && !session ? (
              publicConfig ? <TurnstileGate config={publicConfig} onSession={acceptSession} /> : <div className="security-gate security-gate--loading"><p>{configError ?? "Loading secure session configuration…"}</p></div>
            ) : null}

            {(mode !== "live" || session) && workspaceTab === "compare" ? (
              <ComparisonCards scenario={scenario} swapped={swapped} onSwap={() => setSwapped((value) => !value)} />
            ) : null}

            {(mode !== "live" || session) && workspaceTab === "outcome" ? (
              result ? <ResponseComparison result={result} /> : <div className="workspace-empty"><span>Before / after</span><h2>Run the governed comparison.</h2><p>The blocked attempt and governance-approved output will appear here automatically when the cascade finishes.</p><button className="button button--primary" type="button" disabled={!canRun} onClick={startRun}>Run now</button></div>
            ) : null}

            {(mode !== "live" || session) && workspaceTab === "evidence" ? (
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
