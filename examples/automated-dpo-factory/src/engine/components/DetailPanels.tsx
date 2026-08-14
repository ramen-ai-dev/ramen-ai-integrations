import { useEffect, useState } from "react";
import type { AttemptMetadata, DpoRecord, GovernedBlockedData, GovernedCompleteData } from "../../shared/schemas";

function attemptsFrom(result?: GovernedCompleteData | GovernedBlockedData): AttemptMetadata[] {
  return result?.attempt_metadata ?? [];
}

export function AttemptTrace({ result }: { result?: GovernedCompleteData | GovernedBlockedData }) {
  const attempts = attemptsFrom(result);
  if (attempts.length === 0) return <p className="empty-panel">Attempt metadata will appear after a run completes.</p>;
  return (
    <div className="trace-list">
      {attempts.map((attempt) => (
        <article className="trace-card" key={attempt.attempt}>
          <div className="trace-card__header">
            <span>Attempt {attempt.attempt}</span>
            <strong className={attempt.allowed ? "allowed" : "denied"}>{attempt.allowed ? "Approved" : "Rejected"}</strong>
          </div>
          <div className="metric-row">
            <span><small>Generation</small>{attempt.generation_duration_ms} ms</span>
            <span><small>Evaluation</small>{attempt.evaluation_duration_ms} ms</span>
            <span><small>Policies</small>{attempt.policies_evaluated}</span>
          </div>
          <p>{attempt.provider} · {attempt.model}</p>
        </article>
      ))}
    </div>
  );
}

function steeringFrom(attempts: AttemptMetadata[]): string[] {
  return [...new Set(attempts.flatMap((attempt) => attempt.steering_rationale ?? []))];
}

function SteeringBanner({ rationale, visible }: { rationale: string[]; visible: boolean }) {
  return (
    <aside
      className={`glass-steering ${visible ? "glass-steering--visible" : ""}`}
      role="status"
      aria-label="Firewall steering rationale"
    >
      <strong>Firewall intent detected</strong>
      {rationale.length > 0 ? <ul>{rationale.map((item) => <li key={item}>{item}</li>)}</ul> : <p>The endpoint reported a rejected attempt without an exposed rationale.</p>}
    </aside>
  );
}

export function HealingTrail({ result }: { result?: GovernedCompleteData | GovernedBlockedData }) {
  const rejected = attemptsFrom(result).filter((attempt) => !attempt.allowed);
  if (rejected.length === 0) return <p className="empty-panel">No rejected attempt. Clean approvals do not require healing.</p>;
  return (
    <div className="healing-list">
      {rejected.map((attempt) => {
        const rationale = attempt.steering_rationale ?? [];
        return (
          <article className="healing-card" key={attempt.attempt}>
            <span className="kicker">Rejected attempt {attempt.attempt}</span>
            <blockquote>{attempt.rejected_content ?? "The rejected model output was not exposed by the endpoint."}</blockquote>
            <div className="steering-box" role="status" aria-label="Firewall steering rationale">
              <strong>Firewall intent detected</strong>
              {rationale.length > 0 ? <ul>{rationale.map((item) => <li key={item}>{item}</li>)}</ul> : <p>Steering rationale was not exposed by the endpoint.</p>}
            </div>
          </article>
        );
      })}
    </div>
  );
}

function downloadJsonl(records: DpoRecord[]) {
  const jsonl = records.map((record) => JSON.stringify(record)).join("\n") + "\n";
  const url = URL.createObjectURL(new Blob([jsonl], { type: "application/x-ndjson;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "ramen-ai-governed-preferences.jsonl";
  anchor.click();
  URL.revokeObjectURL(url);
}

export function DatasetLab({ records, onClear }: { records: DpoRecord[]; onClear: () => void }) {
  return (
    <div className="dataset-lab">
      <div className="dataset-summary">
        <div><strong>{records.length}</strong><span>preference pair{records.length === 1 ? "" : "s"} in browser memory</span></div>
        <div className="button-row">
          <button className="button button--quiet" type="button" disabled={records.length === 0} onClick={onClear}>Clear</button>
          <button className="button button--primary" type="button" disabled={records.length === 0} onClick={() => downloadJsonl(records)}>Download JSONL</button>
        </div>
      </div>
      <p className="privacy-note">Nothing is uploaded or persisted. Refreshing the page clears this dataset.</p>
      {records.length === 0 ? <p className="empty-panel">A preference pair appears when an exposed rejected attempt is followed by an approved response.</p> : (
        <div className="record-list">
          {records.map((record, index) => (
            <details key={`${record.metadata.scenario_id}-${record.metadata.source_attempt}-${index}`}>
              <summary><span>Pair {index + 1}</span><strong>{record.metadata.scenario_id}</strong><em>{record.metadata.source}</em></summary>
              <div className="record-grid">
                <div><span>Rejected</span><p>{record.rejected}</p></div>
                <div><span>Chosen</span><p>{record.chosen}</p></div>
              </div>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}

const TERMINAL_BLOCK_MESSAGE = "Terminal Block: Model failed to heal within retry limits.";

export function GlassBreakCascade({ result }: { result?: GovernedCompleteData | GovernedBlockedData }) {
  const deniedAttempts = attemptsFrom(result).filter((attempt) => !attempt.allowed);
  const rejectedAttempt = deniedAttempts.find((attempt) => attempt.rejected_content) ?? deniedAttempts[0];
  const rejectedContent = rejectedAttempt?.rejected_content ?? "The rejected model output was not exposed by the endpoint.";
  const steering = steeringFrom(deniedAttempts);
  const isBlocked = Boolean(result && !("content" in result));
  const chosenContent = result && "content" in result ? result.content : "";
  const glassBreakTriggered = Boolean(result && result.attempts > 1);
  const [visibleCharacters, setVisibleCharacters] = useState(0);
  const [glassBroken, setGlassBroken] = useState(false);

  useEffect(() => {
    setVisibleCharacters(0);
    setGlassBroken(false);
    if (!glassBreakTriggered) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setVisibleCharacters(rejectedContent.length);
      setGlassBroken(true);
      return;
    }

    const characterStep = Math.max(1, Math.ceil(rejectedContent.length / 90));
    const interval = window.setInterval(() => {
      setVisibleCharacters((current) => {
        const next = Math.min(rejectedContent.length, current + characterStep);
        if (next === rejectedContent.length) window.clearInterval(interval);
        return next;
      });
    }, 18);
    return () => window.clearInterval(interval);
  }, [glassBreakTriggered, rejectedContent]);

  useEffect(() => {
    if (!glassBreakTriggered || visibleCharacters < rejectedContent.length || glassBroken) return;
    const timer = window.setTimeout(() => setGlassBroken(true), 140);
    return () => window.clearTimeout(timer);
  }, [glassBreakTriggered, glassBroken, rejectedContent.length, visibleCharacters]);

  if (!result) return null;

  if (!glassBreakTriggered) {
    return (
      <section className="glass-break" aria-labelledby="glass-heading">
        <div className="section-heading"><div><span className="kicker">Governed result</span><h2 id="glass-heading">{isBlocked ? "Terminal governance block." : "No intervention required."}</h2></div></div>
        <article className={`glass-card ${isBlocked ? "glass-card--terminal-block" : "glass-card--chosen"}`} role={isBlocked ? "alert" : undefined}>
          <span>{isBlocked ? "Retry limit reached" : "Verified on first attempt"}</span>
          <p>{isBlocked ? TERMINAL_BLOCK_MESSAGE : chosenContent || "The governed endpoint returned an empty final response."}</p>
        </article>
        {isBlocked ? <SteeringBanner rationale={steering} visible /> : null}
      </section>
    );
  }

  const pairCount = deniedAttempts.filter((attempt) => attempt.rejected_content).length;
  return (
    <section className="glass-break" aria-labelledby="glass-heading">
      <div className="section-heading"><div><span className="kicker">L2 interception replay</span><h2 id="glass-heading">{isBlocked ? "Rejected. Steered. Terminal block." : "Rejected. Steered. Chosen."}</h2></div></div>
      <div className="glass-cascade" aria-live="polite">
        <div className="glass-step-label"><b>01</b><span>Rejected model output</span></div>
        <article className={`glass-card glass-card--rejected ${glassBroken ? "glass-card--broken" : "glass-card--typing"}`}>
          <span>Intercepted before release</span>
          <p aria-hidden="true">{rejectedContent.slice(0, visibleCharacters)}<i className="typewriter-caret" /></p>
          <p className="sr-only">{rejectedContent}</p>
          <div className="glass-fracture" aria-hidden="true" />
        </article>

        <div className="glass-step-label"><b>02</b><span>Policy steering</span></div>
        <SteeringBanner rationale={steering} visible={glassBroken} />

        <div className="glass-step-label"><b>03</b><span>{isBlocked ? "Terminal outcome" : "Governed response"}</span></div>
        <article
          className={`glass-card ${isBlocked ? "glass-card--terminal-block" : "glass-card--chosen"} ${glassBroken ? "glass-card--released" : "glass-card--pending"}`}
          role={isBlocked ? "alert" : undefined}
        >
          <span>{isBlocked ? "Retry limit reached" : "Verified output released"}</span>
          <p>{isBlocked ? TERMINAL_BLOCK_MESSAGE : chosenContent || "The governed endpoint returned an empty final response."}</p>
        </article>

        {!isBlocked ? (
          <div className={`alignment-log ${glassBroken ? "alignment-log--visible" : ""}`}>
            <strong>DPO alignment log updated</strong>
            <span>{pairCount} rejected/chosen preference pair{pairCount === 1 ? "" : "s"} captured in browser memory from live attempt metadata.</span>
          </div>
        ) : null}
      </div>
    </section>
  );
}
