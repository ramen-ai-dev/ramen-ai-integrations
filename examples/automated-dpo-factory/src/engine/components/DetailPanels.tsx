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

export function HealingTrail({ result }: { result?: GovernedCompleteData | GovernedBlockedData }) {
  const rejected = attemptsFrom(result).filter((attempt) => !attempt.allowed && attempt.rejected_content);
  if (rejected.length === 0) return <p className="empty-panel">No exposed rejected attempt. Clean approvals do not require healing.</p>;
  return (
    <div className="healing-list">
      {rejected.map((attempt) => (
        <article className="healing-card" key={attempt.attempt}>
          <span className="kicker">Rejected attempt {attempt.attempt}</span>
          <blockquote>{attempt.rejected_content}</blockquote>
          <div className="steering-box">
            <strong>Policy steering</strong>
            {(attempt.steering_rationale ?? []).length > 0 ? (
              <ul>{attempt.steering_rationale?.map((item) => <li key={item}>{item}</li>)}</ul>
            ) : <p>Steering rationale was not exposed by the endpoint.</p>}
          </div>
        </article>
      ))}
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
              <summary><span>Pair {index + 1}</span><strong>{record.metadata.scenario_id}</strong><em>{record.metadata.source.replace("_", " ")}</em></summary>
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

export function ResponseComparison({ result }: { result?: GovernedCompleteData | GovernedBlockedData }) {
  if (!result) return null;
  const rejected = result.attempt_metadata.find((attempt) => !attempt.allowed && attempt.rejected_content)?.rejected_content;
  const approved = "content" in result ? result.content : undefined;
  return (
    <section className="response-comparison" aria-labelledby="response-heading">
      <div className="section-heading"><div><span className="kicker">Decision outcome</span><h2 id="response-heading">Before governance. After governance.</h2></div></div>
      <div className="response-grid">
        <article className="response-card response-card--rejected"><span>Raw model attempt</span><p>{rejected ?? "No rejected content was exposed."}</p></article>
        <div className="transform-arrow" aria-hidden="true">→</div>
        <article className={`response-card ${approved ? "response-card--approved" : "response-card--blocked"}`}><span>{approved ? "Approved output" : "Release blocked"}</span><p>{approved ?? "Governance did not release a final response."}</p></article>
      </div>
    </section>
  );
}
