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
}

/** Resolve a Zoo entry's direction with the legacy default. */
export function readDirection(entry: ZooEntry): ZooDirection {
  return entry.direction ?? "long_short";
}

const STORAGE_KEY = "alphacore.factor.zoo.v1";
const MAX_ENTRIES = 50;

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
