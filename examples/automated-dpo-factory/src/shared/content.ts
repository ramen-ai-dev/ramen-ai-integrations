import rawDemoConfig from "../../demo/demo.config.json";
import rawScenarios from "../../demo/scenarios.json";
import {
  demoConfigSchema,
  scenarioCatalogSchema,
  type DemoScenario,
} from "./schemas";

export const demoConfig = demoConfigSchema.parse(rawDemoConfig);
const scenarioCatalog = scenarioCatalogSchema.parse(rawScenarios);
export const scenarios = scenarioCatalog.scenarios;

const scenariosById = new Map(scenarios.map((scenario) => [scenario.id, scenario]));

export function getScenario(scenarioId: string): DemoScenario | undefined {
  return scenariosById.get(scenarioId);
}

export function buildScenarioPrompt(scenario: DemoScenario): string {
  const profiles = scenario.entities
    .map((entity) => {
      const attributes = entity.attributes
        .map((attribute) => `- ${attribute.label}: ${attribute.value}`)
        .join("\n");
      return `${entity.label} (${demoConfig.comparison.scoreLabel} ${entity.score}/100):\n${attributes}`;
    })
    .join("\n\n");

  return [
    demoConfig.prompt.preamble,
    `Context: ${scenario.context}`,
    profiles,
    `Adversarial decision request: ${scenario.adversarialPrompt}`,
    demoConfig.prompt.responseInstruction,
  ].join("\n\n");
}
