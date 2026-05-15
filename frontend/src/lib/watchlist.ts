// frontend/src/lib/watchlist.ts
import { syncWatchlistRemote } from "./api/watchlist";

const KEY = "alpha-agent:watchlist";

const isClient = () => typeof window !== "undefined";

export function getWatchlist(): string[] {
  if (!isClient()) return [];
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "[]") as string[];
  } catch {
    return [];
  }
}

export function setWatchlist(tickers: string[]): void {
  if (!isClient()) return;
  const cleaned = Array.from(
    new Set(tickers.map((t) => t.trim().toUpperCase()).filter(Boolean)),
  );
  localStorage.setItem(KEY, JSON.stringify(cleaned));
  // Dual-write: best-effort sync the full normalized list to the backend
  // so the fast_intraday cron unions it into the universe. Fire-and-forget;
  // failures are swallowed inside syncWatchlistRemote. Only the
  // /settings editor reaches this path, and /settings is auth-protected,
  // so the same-origin POST goes through middleware with a valid Bearer.
  void syncWatchlistRemote(cleaned);
}

export function addToWatchlist(ticker: string): string[] {
  const list = getWatchlist();
  if (!list.includes(ticker.toUpperCase())) {
    list.push(ticker.toUpperCase());
    setWatchlist(list);
  }
  return list;
}

export function removeFromWatchlist(ticker: string): string[] {
  const list = getWatchlist().filter((t) => t !== ticker.toUpperCase());
  setWatchlist(list);
  return list;
}
