/**
 * Shared utilities for FactorSpec construction across pages.
 *
 * Until Phase 3.3 these were duplicated in 5 places (BacktestForm,
 * SignalForm, screener/page, factors/page, report/page) — drift risk
 * any time the AST grammar evolved. Single source of truth here.
 */

/**
 * Authoritative client-side mirror of the backend AST whitelist
 * (`AllowedOperator` literal in `alpha_agent/core/types.py` →
 * `BUILTIN_OPS` frozenset in `alpha_agent/core/factor_ast.py`).
 *
 * Keep this list in sync with the Python source: any edit to
 * `AllowedOperator` MUST be mirrored here. The backend re-validates
 * via `_ALLOWED_OPS`, so client-side checks here are purely UX (catch
 * typos before submitting a 422); the server remains the trust boundary.
 *
 * 66 operators (2026-05-23). Phase 3a dynamic extended_operators are
 * NOT mirrored here — those come from the DB and would require a fetch;
 * a false-positive "unknown" hint on an extended op is acceptable
 * because the user can still submit (RUN button is disabled only when
 * `ALLOWED_OPS.has(op) === false`, and the user dismisses via fixing
 * the name or — for true extended ops — the backend accepts it).
 */
export const ALLOWED_OPS: ReadonlySet<string> = new Set<string>([
  // arithmetic — canonical BRAIN names
  "abs", "add", "subtract", "multiply", "divide", "inverse", "log", "sqrt",
  "power", "sign", "signed_power", "max", "min", "reverse", "densify",
  // arithmetic — legacy aliases
  "sub", "mul", "div", "pow",
  // logical
  "if_else", "and_", "or_", "not_", "is_nan",
  "equal", "not_equal", "less", "greater", "less_equal", "greater_equal",
  // time-series
  "ts_delay", "ts_delta", "ts_mean", "ts_std", "ts_std_dev", "ts_sum",
  "ts_product", "ts_min", "ts_max", "ts_rank", "ts_zscore", "ts_arg_min",
  "ts_arg_max", "ts_corr", "ts_covariance", "ts_quantile", "ts_decay_linear",
  "ts_decay_exp", "ts_count_nans", "last_diff_value",
  // cross-section
  "rank", "zscore", "scale", "normalize", "quantile", "winsorize",
  // group (T2)
  "group_rank", "group_zscore", "group_mean", "group_scale",
  "group_neutralize", "group_backfill",
  // T3-promoted
  "ts_regression", "ts_backfill", "trade_when", "hump",
]);

/** Check whether `name` is a known built-in operator. */
export function isAllowedOp(name: string): boolean {
  return ALLOWED_OPS.has(name);
}

/**
 * Levenshtein edit distance with rolling two-row DP (O(min(a,b)) space).
 * Hoisted outside `suggestOp` so the inner loop allocates one row, not one
 * per ALLOWED_OPS entry on every call.
 */
function levenshtein(a: string, b: string): number {
  if (a === b) return 0;
  if (a.length === 0) return b.length;
  if (b.length === 0) return a.length;
  const m = a.length;
  const n = b.length;
  const dp: number[] = new Array(n + 1);
  for (let j = 0; j <= n; j++) dp[j] = j;
  for (let i = 1; i <= m; i++) {
    let prev = dp[0];
    dp[0] = i;
    for (let j = 1; j <= n; j++) {
      const tmp = dp[j];
      dp[j] =
        a.charCodeAt(i - 1) === b.charCodeAt(j - 1)
          ? prev
          : Math.min(prev, dp[j], dp[j - 1]) + 1;
      prev = tmp;
    }
  }
  return dp[n];
}

/**
 * Suggest the nearest valid operator by Levenshtein distance.
 * Returns the closest match if distance ≤ 2, else null.
 *
 * Threshold of 2 catches the common typos (`ts_means` → `ts_mean`,
 * `tsmean` → `ts_mean`, `subract` → `subtract`) at the cost of some
 * loose suggestions for very short tokens; the suggestion is rendered
 * as advisory text, not auto-applied, so a noisy hint is harmless.
 */
export function suggestOp(name: string): string | null {
  let bestOp: string | null = null;
  let bestDist = Number.POSITIVE_INFINITY;
  // `forEach` over a Set sidesteps the `--target ES5 + ReadonlySet` iteration
  // restriction in this project's tsconfig (no `target` set → defaults to ES5).
  ALLOWED_OPS.forEach((op) => {
    const d = levenshtein(name, op);
    if (d < bestDist) {
      bestDist = d;
      bestOp = op;
    }
  });
  return bestOp !== null && bestDist <= 2 ? bestOp : null;
}

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
