/**
 * Shared utilities for FactorSpec construction across pages.
 *
 * Until Phase 3.3 these were duplicated in 5 places (BacktestForm,
 * SignalForm, screener/page, factors/page, report/page) — drift risk
 * any time the AST grammar evolved. Single source of truth here.
 */

/**
 * Naive operator extraction — pulls function-call identifiers out of an
 * expression string. Backend re-validates via the AST whitelist
 * (`_ALLOWED_OPERATORS`), so this is only used to feed the declared-ops
 * field that the API checks for an exact match.
 */
export function extractOps(expr: string): readonly string[] {
  const re = /([a-zA-Z_][a-zA-Z0-9_]*)\s*\(/g;
  const set = new Set<string>();
  let m: RegExpExecArray | null;
  while ((m = re.exec(expr))) set.add(m[1]);
  return Array.from(set);
}

/**
 * Default lookback (in days) for FactorSpec.lookback when the page
 * doesn't expose its own slider. Matches the platform default; see
 * `core/types.py::FactorSpec.lookback` (Pydantic ge=5 le=252).
 */
export const DEFAULT_FACTOR_LOOKBACK = 12;
