import type { GovernedBlockedData } from "./governed-types.js";

/** A governed-generation transport, API, or stream protocol failure. */
export class GovernedGenerationException extends Error {
  constructor(
    readonly status: number | null,
    readonly code: string,
    message: string,
    readonly details?: unknown,
  ) {
    super(message);
    this.name = "GovernedGenerationException";
  }
}

/** No compliant output was produced within the governed retry limit. */
export class GovernanceDeniedException extends GovernedGenerationException {
  readonly status = 422 as const;
  readonly code = "GOVERNED_OUTPUT_BLOCKED" as const;

  constructor(message: string, readonly data: GovernedBlockedData) {
    super(422, "GOVERNED_OUTPUT_BLOCKED", message, data);
    this.name = "GovernanceDeniedException";
  }
}
