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
  const controllerRef = useRef<AbortController | undefined>(undefined);

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
    if (mode !== "live" || session) return;
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
    setSession(next);
    setRunState(initialRun);
  }, []);

  const chooseScenario = (nextId: string) => {
    if (runState.terminal === "running") return;
    setScenarioId(nextId);
    setRunState(initialRun);
    setSwapped(false);
  };

  const startRun = async () => {
    if (!scenario || runState.terminal === "running") return;
    if (mode === "live" && !session) return;

    const controller = new AbortController();
    controllerRef.current = controller;
    setRunState({ terminal: "running", statuses: [] });

    try {
      const stream = mode === "guided"
        ? runGuidedScenario(scenario, controller.signal)
        : runLiveScenario(scenario.id, controller.signal);

      for await (const event of stream) {
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
          continue;
        }
        if (event.event === "blocked") {
          setRunState((current) => ({ ...current, terminal: "blocked", blocked: event.data.data }));
          setDetailTab("healing");
          continue;
        }
        setRunState((current) => ({ ...current, terminal: "error", error: event.data.error.message }));
      }
    } catch (error) {
      const cancelled = error instanceof DOMException && error.name === "AbortError";
      setRunState((current) => ({
        ...current,
        terminal: "error",
        error: cancelled ? "Run cancelled before completion." : error instanceof Error ? error.message : "The governed run failed.",
      }));
    } finally {
      controllerRef.current = undefined;
    }
  };

  const closeSession = async () => {
    try { await deleteSession(); } catch { /* Local state is still cleared; the cookie naturally expires. */ }
    setSession(undefined);
    setRunState(initialRun);
  };

  if (!scenario) return <main className="fatal-state">No configured scenarios are available.</main>;

  const canRun = runState.terminal !== "running" && (mode === "guided" || Boolean(session));

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="ramen ai home">
          <img src={demoConfig.brand.logoPath} alt="" />
          <span>{demoConfig.brand.name}</span>
        </a>
        <div className="topbar__meta"><span>Foundry Template</span><span className="topbar__dot" /> <span>{demoConfig.showcaseLabel}</span></div>
        <a className="github-link" href="https://github.com/ramen-ai" target="_blank" rel="noreferrer">Open-source scaffold ↗</a>
      </header>

      <main id="top">
        <section className="hero">
          <div className="hero__glow" />
          <div className="hero__copy">
            <span className="kicker">{demoConfig.eyebrow}</span>
            <h1>{demoConfig.title}</h1>
            <p>{demoConfig.description}</p>
            <div className="hero__proof">
              <span><strong>01</strong> Generate</span><i />
              <span><strong>02</strong> Evaluate</span><i />
              <span><strong>03</strong> Heal</span><i />
              <span><strong>04</strong> Release</span>
            </div>
          </div>
          <div className="hero__stat">
            <span>Policy-governed</span>
            <strong>Every output</strong>
            <p>Provider credentials remain inside the Cloudflare Worker.</p>
          </div>
        </section>

        <section className="control-deck" aria-label="Demo controls">
          <div className="mode-switch" role="group" aria-label="Run mode">
            <button type="button" className={mode === "guided" ? "active" : ""} onClick={() => setMode("guided")}><span>Guided Showcase</span><small>Deterministic fixture</small></button>
            <button type="button" className={mode === "live" ? "active" : ""} onClick={() => setMode("live")}><span>Live Endpoint</span><small>Real governed stream</small></button>
          </div>
          <div className="session-summary">
            {mode === "guided" ? <><span className="session-light session-light--fixture" /><div><strong>Fixture mode</strong><small>No network or credentials</small></div></> : session ? <><span className="session-light session-light--live" /><div><strong>Secure session active</strong><small>{publicConfig?.burstLimit ?? 5} requests per {publicConfig?.burstWindowSeconds ?? 60}s burst window</small></div><button type="button" onClick={closeSession}>End</button></> : <><span className="session-light" /><div><strong>Verification required</strong><small>Keys stay server-side</small></div></>}
          </div>
        </section>

        {mode === "guided" ? <div className="provenance-banner"><strong>Guided fixture</strong><span>This mode replays configured, synthetic events. Exported records are marked <code>guided_fixture</code>.</span></div> : null}
        {mode === "live" && !session ? (
          publicConfig ? <TurnstileGate config={publicConfig} onSession={acceptSession} /> : <div className="security-gate security-gate--loading"><p>{configError ?? "Loading secure session configuration…"}</p></div>
        ) : null}

        <section className="scenario-rail" aria-labelledby="scenario-heading">
          <div className="section-heading"><div><span className="kicker">Scenario library</span><h2 id="scenario-heading">Choose the pressure test.</h2></div><span className="scenario-count">{scenarios.length} configured paths</span></div>
          <div className="scenario-list">
            {scenarios.map((item, index) => (
              <button type="button" className={item.id === scenario.id ? "scenario-button scenario-button--active" : "scenario-button"} onClick={() => chooseScenario(item.id)} key={item.id}>
                <span>{String(index + 1).padStart(2, "0")}</span><div><strong>{item.title}</strong><small>{item.summary}</small></div><em className={`path path--${item.expectedPath}`}>{item.expectedPath}</em>
              </button>
            ))}
          </div>
        </section>

        <ComparisonCards scenario={scenario} swapped={swapped} onSwap={() => setSwapped((value) => !value)} />

        <section className="run-deck">
          <div><span className="kicker">{scenario.context}</span><h2>Run the governed cascade.</h2><p>The Worker accepts only this configured scenario ID. Prompts and generation limits cannot be overridden from the browser.</p></div>
          <div className="run-actions">
            {runState.terminal === "running" ? <button className="button button--danger" type="button" onClick={() => controllerRef.current?.abort()}>Cancel run</button> : null}
            <button className="button button--run" type="button" disabled={!canRun} onClick={startRun}><span>{runState.terminal === "running" ? "Cascade running" : mode === "live" ? "Run live governance" : "Replay governed path"}</span><b aria-hidden="true">→</b></button>
          </div>
        </section>

        {runState.error ? <div className="error-banner" role="alert"><strong>Run failed</strong><span>{runState.error}</span></div> : null}
        <StatusStreamer statuses={runState.statuses} terminal={runState.terminal} />
        <ResponseComparison result={result} />

        <section className="detail-section" aria-labelledby="details-heading">
          <div className="section-heading"><div><span className="kicker">Governance evidence</span><h2 id="details-heading">Inspect what happened.</h2></div></div>
          <div className="tabs" role="tablist" aria-label="Governance evidence views">
            <button role="tab" aria-selected={detailTab === "attempts"} className={detailTab === "attempts" ? "active" : ""} onClick={() => setDetailTab("attempts")}>Attempt Trace <span>{result?.attempt_metadata.length ?? 0}</span></button>
            <button role="tab" aria-selected={detailTab === "healing"} className={detailTab === "healing" ? "active" : ""} onClick={() => setDetailTab("healing")}>Healing Trail <span>{result?.attempt_metadata.filter((item) => !item.allowed).length ?? 0}</span></button>
            <button role="tab" aria-selected={detailTab === "dataset"} className={detailTab === "dataset" ? "active" : ""} onClick={() => setDetailTab("dataset")}>Dataset Lab <span>{records.length}</span></button>
          </div>
          <div className="tab-panel" role="tabpanel">
            {detailTab === "attempts" ? <AttemptTrace result={result} /> : null}
            {detailTab === "healing" ? <HealingTrail result={result} /> : null}
            {detailTab === "dataset" ? <DatasetLab records={records} onClear={() => setRecords([])} /> : null}
          </div>
        </section>
      </main>

      <footer><div className="brand brand--footer"><img src={demoConfig.brand.logoPath} alt="" /><span>{demoConfig.brand.name}</span></div><p>One engine. Replaceable scenarios. Governed by default.</p><span>MIT licensed Foundry Template</span></footer>
    </div>
  );
}
