import type {
  HypothesisHistoryEntry,
  HypothesisTranslateRequest,
  HypothesisTranslateResponse,
} from "./types";

const STORAGE_KEY = "alphacore.hypothesis.history.v1";
const MAX_RECENT = 5;
const MAX_FAVORITES = 20;

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function readRaw(): readonly HypothesisHistoryEntry[] {
  if (!isBrowser()) return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed as HypothesisHistoryEntry[];
  } catch {
    return [];
  }
}

function writeRaw(entries: readonly HypothesisHistoryEntry[]): void {
  if (!isBrowser()) return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // storage full or disabled — silently drop; UI state stays valid
  }
}

function generateId(): string {
  return `hy_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export function getHistory(): readonly HypothesisHistoryEntry[] {
  // newest first
  return [...readRaw()].sort((a, b) => b.timestamp.localeCompare(a.timestamp));
}

export function getFavorites(): readonly HypothesisHistoryEntry[] {
  return getHistory().filter((e) => e.isFavorite);
}

export function getRecent(): readonly HypothesisHistoryEntry[] {
  return getHistory()
    .filter((e) => !e.isFavorite)
    .slice(0, MAX_RECENT);
}

export function addToHistory(
  request: HypothesisTranslateRequest,
  result: HypothesisTranslateResponse,
): HypothesisHistoryEntry {
  const entry: HypothesisHistoryEntry = {
    id: generateId(),
    timestamp: new Date().toISOString(),
    request,
    result,
    isFavorite: false,
  };

  const current = readRaw();
  const favorites = current.filter((e) => e.isFavorite);
  const recent = current
    .filter((e) => !e.isFavorite)
    .sort((a, b) => b.timestamp.localeCompare(a.timestamp));

  // prepend new entry, LRU-evict oldest non-favorite past MAX_RECENT
  const newRecent = [entry, ...recent].slice(0, MAX_RECENT);
  writeRaw([...favorites, ...newRecent]);
  return entry;
}

export function toggleFavorite(id: string): readonly HypothesisHistoryEntry[] {
  const current = readRaw();
  const target = current.find((e) => e.id === id);
  if (!target) return current;

  const willFavorite = !target.isFavorite;
  const favCount = current.filter((e) => e.isFavorite).length;
  if (willFavorite && favCount >= MAX_FAVORITES) {
    // refuse to add more favorites; caller can surface a toast if it wants
    return current;
  }

  const next = current.map((e) =>
    e.id === id ? { ...e, isFavorite: willFavorite } : e,
  );
  writeRaw(next);
  return next;
}

export function removeFromHistory(id: string): readonly HypothesisHistoryEntry[] {
  const next = readRaw().filter((e) => e.id !== id);
  writeRaw(next);
  return next;
}

export function clearHistory(keepFavorites = true): readonly HypothesisHistoryEntry[] {
  const next = keepFavorites ? readRaw().filter((e) => e.isFavorite) : [];
  writeRaw(next);
  return next;
}

export const HYPOTHESIS_HISTORY_LIMITS = {
  maxRecent: MAX_RECENT,
  maxFavorites: MAX_FAVORITES,
} as const;
