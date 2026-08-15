import { z } from "zod";

const identifierSchema = z.string().regex(/^[a-z0-9][a-z0-9_-]{1,63}$/);
const boundedText = (max: number) => z.string().trim().min(1).max(max);

export const attributeSchema = z.object({
  label: boundedText(80),
  value: boundedText(300),
  category: z.enum(["relevant", "proxy"]),
}).strict();

export const comparisonEntitySchema = z.object({
  id: identifierSchema,
  label: boundedText(80),
  score: z.number().int().min(0).max(100),
  attributes: z.array(attributeSchema).min(1).max(12),
}).strict();

export const scenarioSchema = z.object({
  id: identifierSchema,
  title: boundedText(100),
  summary: boundedText(280),
  context: boundedText(120),
  entities: z.tuple([comparisonEntitySchema, comparisonEntitySchema]),
  adversarialPrompt: boundedText(500),
}).strict();

export const scenarioCatalogSchema = z.object({
  schemaVersion: z.literal(1),
  scenarios: z.array(scenarioSchema).length(5),
}).strict();

export const demoConfigSchema = z.object({
  schemaVersion: z.literal(1),
  id: identifierSchema,
  showcaseLabel: boundedText(100),
  brand: z.object({
    name: boundedText(40),
    logoPath: z.string().startsWith("/").max(200),
  }),
  eyebrow: boundedText(100),
  title: boundedText(160),
  description: boundedText(500),
  comparison: z.object({
    entitySingular: boundedText(40),
    entityPlural: boundedText(40),
    sectionTitle: boundedText(120),
    scoreLabel: boundedText(80),
    relevantLabel: boundedText(80),
    proxyLabel: boundedText(80),
    cleanEvidenceLabel: boundedText(100),
    riskSignalLabel: boundedText(100),
  }),
  prompt: z.object({
    preamble: boundedText(500),
    responseInstruction: boundedText(500),
  }),
  governance: z.object({
    policyIds: z.array(z.string().uuid()).min(1).max(20),
    maxRetries: z.union([z.literal(0), z.literal(1)]),
    generation: z.object({
      temperature: z.number().min(0).max(2),
      maxTokens: z.number().int().min(1).max(4096),
    }),
  }),
});

export const tokenUsageSchema = z.object({
  prompt_tokens: z.number().int().nonnegative(),
  completion_tokens: z.number().int().nonnegative(),
  total_tokens: z.number().int().nonnegative(),
});

export const attemptMetadataSchema = z.object({
  attempt: z.number().int().positive(),
  provider: z.string(),
  model: z.string(),
  generation_duration_ms: z.number().int().nonnegative(),
  evaluation_duration_ms: z.number().int().nonnegative(),
  policies_evaluated: z.number().int().nonnegative(),
  allowed: z.boolean(),
  usage: tokenUsageSchema.optional(),
  rejected_content: z.string().optional(),
  steering_rationale: z.array(z.string()).optional(),
});

export const evaluationSummarySchema = z.object({
  allowed: z.boolean(),
  policy_ids: z.array(z.string()),
  policies_evaluated: z.number().int().nonnegative(),
  policies_passed: z.number().int().nonnegative(),
  policies_failed: z.number().int().nonnegative(),
  policies_errored: z.number().int().nonnegative(),
  violation_count: z.number().int().nonnegative(),
  statutory_anchors: z.array(z.string()),
  receipt_id: z.string().optional(),
});

const accountingSchema = z.object({
  generation_attempts: z.number().int().nonnegative(),
  evaluation_batches: z.number().int().nonnegative(),
  policy_evaluations: z.number().int().nonnegative(),
});

export const governedCompleteDataSchema = z.object({
  content: z.string(),
  provider: z.string(),
  model: z.string(),
  usage: tokenUsageSchema.optional(),
  attempts: z.number().int().positive(),
  attempt_metadata: z.array(attemptMetadataSchema),
  evaluation: evaluationSummarySchema,
  accounting: accountingSchema,
  total_duration_ms: z.number().int().nonnegative(),
});

export const governedBlockedDataSchema = z.object({
  attempts: z.number().int().positive(),
  attempt_metadata: z.array(attemptMetadataSchema),
  evaluation: evaluationSummarySchema,
  accounting: accountingSchema,
  total_duration_ms: z.number().int().nonnegative(),
});

export const statusDataSchema = z.object({
  stage: z.enum(["accepted", "generating", "evaluating", "scrubbing", "regenerating"]),
  attempt: z.number().int().nonnegative(),
  violations: z.number().int().nonnegative().optional(),
});

export const heartbeatDataSchema = z.object({ timestamp: z.string() });
export const completeEnvelopeSchema = z.object({ success: z.literal(true), data: governedCompleteDataSchema });
const governedErrorSchema = z.object({ code: z.string(), message: z.string(), http_status: z.number().int() });
export const blockedEnvelopeSchema = z.object({ success: z.literal(false), error: governedErrorSchema, data: governedBlockedDataSchema });
export const errorEnvelopeSchema = z.object({ success: z.literal(false), error: governedErrorSchema, data: z.unknown().optional() });

export const generateRequestSchema = z.object({ scenarioId: identifierSchema }).strict();

export type DemoConfig = z.infer<typeof demoConfigSchema>;
export type DemoScenario = z.infer<typeof scenarioSchema>;
export type ComparisonEntity = z.infer<typeof comparisonEntitySchema>;
export type GovernedCompleteData = z.infer<typeof governedCompleteDataSchema>;
export type GovernedBlockedData = z.infer<typeof governedBlockedDataSchema>;
export type AttemptMetadata = z.infer<typeof attemptMetadataSchema>;
export type StatusData = z.infer<typeof statusDataSchema>;

export type GovernedStreamEvent =
  | { event: "status"; data: StatusData }
  | { event: "heartbeat"; data: z.infer<typeof heartbeatDataSchema> }
  | { event: "complete"; data: z.infer<typeof completeEnvelopeSchema> }
  | { event: "blocked"; data: z.infer<typeof blockedEnvelopeSchema> }
  | { event: "error"; data: z.infer<typeof errorEnvelopeSchema> };

export interface DpoRecord {
  prompt: string;
  rejected: string;
  chosen: string;
  steering_rationale: string[];
  metadata: {
    source: "live";
    scenario_id: string;
    source_attempt: number;
    provider: string;
    model: string;
    policy_ids: string[];
    receipt_id?: string;
  };
}
