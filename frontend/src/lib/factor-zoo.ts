/**
 * Factor Zoo — localStorage-backed registry of saved factors.
 *
 * Mirrors the pattern in hypothesis-history.ts. Each saved factor is a
 * snapshot of the FactorSpec plus a user-supplied name + a few
 * "headline metrics" captured at save time so the Zoo browser can
 * sort/filter without re-running the backtest. The full result is NOT
 * stored — that would bloat localStorage and go stale; the Zoo is just
 * a bookmark, the engine is the source of truth.
 *
 * No backend involvement. Every operation is sync, runs only in the
 * browser, and silently no-ops on the server.
 */

/** Direction the factor was last backtested under. Defaults to long_short
 * for legacy entries that predate this field. Read consumers should always
 * fallback via {@link readDirection} below. */
export type ZooDirection = "long_short" | "long_only" | "short_only";

export interface ZooEntry {
  readonly id: string;
  readonly name: string;
  readonly expression: string;
  readonly hypothesis: string;
  readonly intuition?: string;
  readonly direction?: ZooDirection;
  readonly savedAt: string;          // ISO 8601
  readonly headlineMetrics?: {
    readonly testSharpe?: number;
    readonly totalReturn?: number;   // full-period, decimal
    readonly testIc?: number;
  };
  // v4 cross-page parity (Phase 2.4): persist the full backtest config
  // that produced the saved metrics. Without these fields, replay from
  // /factors uses /backtest defaults — saved Sharpe is unreplicable and
  // the headline metric becomes a "trust me bro" claim. Optional for
  // back-compat with v1 entries (resolveConfig fills defaults).
  readonly neutralize?: "none" | "sector";
  readonly benchmarkTicker?: "SPY" | "RSP";
  readonly mode?: "static" | "walk_forward";
  readonly topPct?: number;          // 0.01-0.50
  readonly bottomPct?: number;       // 0.01-0.50
  readonly transactionCostBps?: number;
  // P2-4: true for the factors AlphaCore seeds into a brand-new user's Zoo
  // so Screener / Report / Zoo aren't empty on first visit. User-deletable
  // like any entry; the one-time seed flag prevents re-seeding deletions.
  readonly curated?: boolean;
}

/** Resolve a Zoo entry's direction with the legacy default. */
export function readDirection(entry: ZooEntry): ZooDirection {
  return entry.direction ?? "long_short";
}

/** Resolve full backtest config with v1-entry-friendly defaults. */
export function readConfig(entry: ZooEntry): {
  direction: ZooDirection;
  neutralize: "none" | "sector";
  benchmarkTicker: "SPY" | "RSP";
  mode: "static" | "walk_forward";
  topPct: number;
  bottomPct: number;
  transactionCostBps: number;
} {
  return {
    direction: entry.direction ?? "long_short",
    neutralize: entry.neutralize ?? "none",
    benchmarkTicker: entry.benchmarkTicker ?? "SPY",
    mode: entry.mode ?? "static",
    topPct: entry.topPct ?? 0.30,
    bottomPct: entry.bottomPct ?? 0.30,
    transactionCostBps: entry.transactionCostBps ?? 5,
  };
}

const STORAGE_KEY = "alphacore.factor.zoo.v1";
const SEED_FLAG_KEY = "alphacore.factor.zoo.seeded.v1";
const MAX_ENTRIES = 50;

// Cold-start seed: the 3 strongest curated factors (mirrors the PURE/
// MARGINAL-tier picks from FACTOR_EXAMPLES). Seeded once into a new user's
// Zoo so Screener / Report / Zoo work on first visit instead of dead-ending
// on "Zoo is empty". Metrics are the 2026-05-08 v3-panel measurements.
const CURATED_SEED: readonly Omit<ZooEntry, "id" | "savedAt">[] = [
  {
    name: "Earnings Yield (E/P)",
    expression:
      "rank(divide(net_income_adjusted, multiply(close, shares_outstanding)))",
    hypothesis:
      "Long high earnings yield (net income / market cap), short low — long_short Basu 1977 value",
    intuition:
      "PURE ALPHA tier: α-t=+2.29, α-p=0.022, β=-0.10, SR=+1.52. Shorting overvalued growth nets out sector beta, leaving clean alpha.",
    direction: "long_short",
    neutralize: "none",
    benchmarkTicker: "SPY",
    topPct: 0.3,
    bottomPct: 0.3,
    headlineMetrics: { testSharpe: 1.52, totalReturn: 0.258, testIc: 0.011 },
    curated: true,
  },
  {
    name: "Volume Z-Score 20d",
    expression: "ts_zscore(volume, 20)",
    hypothesis:
      "20-day volume z-score — abnormal-trading signal; long_short + sector-neutral isolates the alpha",
    intuition:
      "PURE ALPHA tier: α-t=+2.03, α-p=0.043, β=+0.03, SR=+2.93 (highest in batch). 'Unusual volume precedes price.'",
    direction: "long_short",
    neutralize: "sector",
    benchmarkTicker: "SPY",
    topPct: 0.3,
    bottomPct: 0.3,
    headlineMetrics: { testSharpe: 2.93, totalReturn: 0.186, testIc: 0.0107 },
    curated: true,
  },
  {
    name: "Dollar Volume Z-Score 60d",
    expression: "ts_zscore(dollar_volume, 60)",
    hypothesis:
      "60-day dollar volume z-score — better attention proxy than raw volume; β near zero",
    intuition:
      "MARGINAL tier: α-t=+1.88, α-p=0.060, β=-0.087, SR=+2.04. Highly correlated with Volume Z-Score 20d — don't stack both.",
    direction: "long_short",
    neutralize: "none",
    benchmarkTicker: "SPY",
    topPct: 0.3,
    bottomPct: 0.3,
    headlineMetrics: { testSharpe: 2.04, totalReturn: 0.131, testIc: 0.0119 },
    curated: true,
  },
];

/**
 * One-time cold-start seed. On a brand-new browser (no seed flag), inserts
 * the curated factors the user hasn't already saved, then sets the flag so
 * deletions are never re-seeded. Idempotent + safe to call from multiple
 * pages — the flag guards it. No-ops on the server / when storage is off.
 */
export function seedZooIfFirstRun(): void {
  if (!isBrowser()) return;
  try {
    if (window.localStorage.getItem(SEED_FLAG_KEY)) return;
    const existing = readRaw();
    const existingExprs = new Set(existing.map((e) => e.expression));
    const seeds: ZooEntry[] = CURATED_SEED.filter(
      (s) => !existingExprs.has(s.expression),
    ).map((s, i) => ({
      ...s,
      id: generateId(),
      // Stagger savedAt so listZoo's desc sort keeps the seed order.
      savedAt: new Date(Date.now() - i).toISOString(),
    }));
    if (seeds.length > 0) writeRaw([...seeds, ...existing]);
    window.localStorage.setItem(SEED_FLAG_KEY, new Date().toISOString());
  } catch {
    // storage disabled — skip seeding; the UI still works (just empty Zoo)
  }
}

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function readRaw(): ZooEntry[] {
  if (!isBrowser()) return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed as ZooEntry[];
  } catch {
    return [];
  }
}

function writeRaw(entries: ZooEntry[]): void {
  if (!isBrowser()) return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // storage full or disabled — silently drop; UI state stays valid
  }
}

function generateId(): string {
  return `zoo_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

/** All saved factors, newest first. */
export function listZoo(): readonly ZooEntry[] {
  return readRaw().slice().sort(
    (a, b) => new Date(b.savedAt).getTime() - new Date(a.savedAt).getTime(),
  );
}

/** Persist a new factor. If `expression` already exists, updates in place. */
export function addToZoo(entry: Omit<ZooEntry, "id" | "savedAt">): ZooEntry {
  const all = readRaw();
  const idx = all.findIndex((e) => e.expression === entry.expression);
  const now = new Date().toISOString();
  const next: ZooEntry = idx >= 0
    ? { ...all[idx], ...entry, savedAt: now }
    : { ...entry, id: generateId(), savedAt: now };

  if (idx >= 0) {
    all[idx] = next;
  } else {
    all.unshift(next);
    if (all.length > MAX_ENTRIES) all.length = MAX_ENTRIES;
  }
  writeRaw(all);
  return next;
}

export function removeFromZoo(id: string): void {
  const all = readRaw().filter((e) => e.id !== id);
  writeRaw(all);
}

export function clearZoo(): void {
  writeRaw([]);
}

/** Quick membership check by expression (used to disable "Save" button if already saved). */
export function isInZoo(expression: string): boolean {
  return readRaw().some((e) => e.expression === expression);
}
