import { demoConfig } from "../../shared/content";
import type { ComparisonEntity, DemoScenario } from "../../shared/schemas";

function EntityCard({ entity, position }: { entity: ComparisonEntity; position: string }) {
  const proxyCount = entity.attributes.filter((attribute) => attribute.category === "proxy").length;
  return (
    <article className="candidate-card">
      <div className="candidate-card__topline">
        <span className="position-label">{position}</span>
        <span className="score-pill">
          <strong>{entity.score}</strong>/100 {demoConfig.comparison.scoreLabel}
        </span>
      </div>
      <h3>{entity.label}</h3>
      <div className="attribute-list">
        {entity.attributes.map((attribute) => (
          <div className={`attribute attribute--${attribute.category}`} key={`${entity.id}-${attribute.label}`}>
            <div>
              <span className="attribute__kind">
                {attribute.category === "proxy" ? demoConfig.comparison.proxyLabel : demoConfig.comparison.relevantLabel}
              </span>
              <span className="attribute__label">{attribute.label}</span>
            </div>
            <strong>{attribute.value}</strong>
          </div>
        ))}
      </div>
      {proxyCount > 0 ? (
        <p className="proxy-notice"><span aria-hidden="true">◆</span> {proxyCount} {demoConfig.comparison.riskSignalLabel}{proxyCount === 1 ? "" : "s"} present</p>
      ) : (
        <p className="clean-notice"><span aria-hidden="true">✓</span> {demoConfig.comparison.cleanEvidenceLabel}</p>
      )}
    </article>
  );
}

export function ComparisonCards({ scenario, swapped, onSwap }: { scenario: DemoScenario; swapped: boolean; onSwap: () => void }) {
  const [first, second] = swapped
    ? [scenario.entities[1], scenario.entities[0]]
    : [scenario.entities[0], scenario.entities[1]];
  return (
    <section className="comparison-section" aria-labelledby="comparison-heading">
      <div className="section-heading">
        <div>
          <span className="kicker">Input evidence</span>
          <h2 id="comparison-heading">{demoConfig.comparison.sectionTitle}</h2>
        </div>
        <button className="button button--quiet" type="button" onClick={onSwap}>Swap positions</button>
      </div>
      <div className="candidate-grid">
        <EntityCard entity={first} position="Left pane" />
        <div className="versus" aria-hidden="true">vs</div>
        <EntityCard entity={second} position="Right pane" />
      </div>
      <div className="decision-request">
        <span>Adversarial prompt</span>
        <p>{scenario.adversarialPrompt}</p>
      </div>
    </section>
  );
}
