import type { StatusData } from "../../shared/schemas";

const stageCopy: Record<StatusData["stage"], { label: string; detail: string }> = {
  accepted: { label: "Request accepted", detail: "The governed cascade is active." },
  generating: { label: "Generating output", detail: "The provider is drafting an output." },
  evaluating: { label: "Evaluating policies", detail: "ramen ai is checking the configured rules." },
  regenerating: { label: "Applying steering", detail: "The model is retrying with policy guidance." },
};

export function StatusStreamer({ statuses, terminal }: { statuses: StatusData[]; terminal: "idle" | "running" | "complete" | "blocked" | "error" }) {
  return (
    <section className="status-stream" aria-live="polite" aria-label="Governed cascade status">
      <div className="stream-header">
        <span className={`live-dot ${terminal === "running" ? "live-dot--active" : ""}`} />
        <strong>{terminal === "idle" ? "Ready" : terminal === "running" ? "Cascade running" : "Cascade finished"}</strong>
      </div>
      <div className="stream-steps">
        {statuses.length === 0 ? <p className="empty-copy">Run a scenario to watch each governance transition.</p> : null}
        {statuses.map((status, index) => {
          const copy = stageCopy[status.stage];
          const active = terminal === "running" && index === statuses.length - 1;
          return (
            <div className={`stream-step stream-step--${status.stage} ${active ? "stream-step--active" : ""}`} key={`${status.stage}-${status.attempt}-${index}`}>
              <span className="step-index">{String(index + 1).padStart(2, "0")}</span>
              <div><strong>{copy.label}</strong><p>{copy.detail}</p></div>
              <span className={`status-badge ${status.violations ? "status-badge--blocked" : ""}`}>
                Attempt {status.attempt}{status.violations ? ` · ${status.violations} blocked` : ""}
              </span>
            </div>
          );
        })}
        {terminal === "complete" ? <div className="terminal terminal--approved"><strong>Approved response released</strong><span>Only governance-approved content reached the application.</span></div> : null}
        {terminal === "blocked" ? <div className="terminal terminal--blocked"><strong>Terminal governance block</strong><span>No output was released.</span></div> : null}
        {terminal === "error" ? <div className="terminal terminal--error"><strong>Request interrupted</strong><span>Review the error and try again.</span></div> : null}
      </div>
    </section>
  );
}
