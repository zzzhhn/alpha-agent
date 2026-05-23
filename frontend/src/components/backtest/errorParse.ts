/**
 * errorParse — backtest 422 / runtime error parser (T-debug pass).
 *
 * The session hook prepends "HTTP <code>: " (or yields a raw Error.message)
 * before storing the message string on `RunState.error`. FastAPI 422 bodies
 * serialize as a JSON array of {type, loc, msg, input, ctx} objects; we want
 * a single short summary (for toast + VerdictBar headline) plus the raw
 * detail (for VerdictBar's collapsible <details>).
 *
 * Output is language-neutral on purpose — VerdictBar special-cases the
 * "unknown operator" pattern with a localized prefix; everything else falls
 * back to the English summary (still better than dumping the JSON array).
 */

export interface ParsedError {
  readonly kind: "validation" | "network" | "unknown";
  /** 1-line, <= 140 chars, safe to render in toast / single-line slots. */
  readonly summary: string;
  /** Full original message (for <details>), or null when summary IS full. */
  readonly detail: string | null;
  /** Dotted/bracketed field path, e.g. "spec.operators_used[1]". */
  readonly badField?: string | null;
  /** Offending value, e.g. "ts_means". Always a string when present. */
  readonly badValue?: string | null;
}

interface PydanticIssue {
  readonly type?: string;
  readonly loc?: ReadonlyArray<string | number>;
  readonly msg?: string;
  readonly input?: unknown;
  readonly ctx?: Record<string, unknown>;
}

const MAX_SUMMARY_LEN = 140;

export function parseBacktestError(message: string): ParsedError {
  // FastAPI 422 bodies always start with "["; if we don't see one anywhere
  // in the string, treat as opaque (network error / runtime exception copy).
  const jsonStart = message.indexOf("[");
  if (jsonStart === -1) {
    return {
      kind: "unknown",
      summary: truncate(message, MAX_SUMMARY_LEN),
      detail: null,
    };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(message.slice(jsonStart));
  } catch {
    // Not JSON after all — fall through to "unknown" with original message
    // preserved as detail.
    return {
      kind: "unknown",
      summary: truncate(message, MAX_SUMMARY_LEN),
      detail: message,
    };
  }

  if (!Array.isArray(parsed) || parsed.length === 0) {
    return {
      kind: "unknown",
      summary: truncate(message, MAX_SUMMARY_LEN),
      detail: message,
    };
  }

  const first = parsed[0] as PydanticIssue;

  if (first?.type === "literal_error" && Array.isArray(first.loc)) {
    const field = formatFieldPath(first.loc);
    const badValue =
      typeof first.input === "string" ? first.input : null;
    const summary = badValue
      ? `Invalid value for ${field}: "${badValue}"`
      : `Invalid value for ${field}`;
    return {
      kind: "validation",
      summary: truncate(summary, MAX_SUMMARY_LEN),
      detail: message,
      badField: field,
      badValue,
    };
  }

  if (typeof first?.msg === "string") {
    return {
      kind: "validation",
      summary: truncate(first.msg, MAX_SUMMARY_LEN),
      detail: message,
    };
  }

  return {
    kind: "unknown",
    summary: truncate(message, MAX_SUMMARY_LEN),
    detail: message,
  };
}

/**
 * Pydantic `loc` arrays start with the section ("body", "query", ...) and
 * then walk the model. We strip the first 2 entries ("body", "<root model>")
 * and emit a dotted/bracketed JS-style path so users see "operators_used[1]"
 * rather than "body > spec > operators_used > 1".
 */
function formatFieldPath(loc: ReadonlyArray<string | number>): string {
  const tail = loc.slice(2);
  if (tail.length === 0) return loc.map(String).join(".");
  return tail
    .map((part) =>
      typeof part === "number" ? `[${part}]` : `.${part}`,
    )
    .join("")
    .replace(/^\./, "");
}

function truncate(s: string, n: number): string {
  return s.length <= n ? s : s.slice(0, n - 1) + "…";
}
