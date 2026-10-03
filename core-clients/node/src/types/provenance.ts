/**
 * Standardised provenance envelope for governed tool outcomes.
 *
 * Mirrors the `_ramen_provenance` envelope that ramen-foundry attaches to
 * `ToolMessage.response_metadata`, so TypeScript agents, MCP hosts, and Python
 * agents emit the same shape to observability tools. It is flat and
 * JSON-serialisable, and holds only identifiers and short text.
 */
export interface RamenProvenanceEnvelope {
  /** "ramen-forge" when the lesson came from ramen forge; otherwise "ramen-local". */
  source: "ramen-forge" | "ramen-local";
  version: "1.0";
  domain: string;
  tool_name: string;
  /** The recalled or recorded exemplar, if any. */
  exemplar_id: string | null;
  statutory_anchor: string | null;
  /** Schema V5 receipt id of the evaluation this envelope describes. */
  receipt_id: string | null;
  prevention_summary: string | null;
  /**
   * Filtered ramen forge listing (domain, tool, task fingerprint) that returns
   * the lesson with its signature. ramen forge cannot look records up by
   * exemplar id, so this is a filter rather than a permalink.
   */
  audit_uri: string | null;
}

export const PROVENANCE_VERSION = "1.0" as const;
