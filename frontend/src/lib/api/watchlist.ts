// frontend/src/lib/api/watchlist.ts
import { apiGet, apiPost } from "./client";

// Backend mirror of the localStorage watchlist (dual-write). Best-effort:
// failures are swallowed - localStorage is the source of truth for the UI,
// the backend copy only feeds the fast_intraday cron's universe so a
// starred ticker gets intraday coverage.
export interface WatchlistResponse {
  tickers: string[];
}

export const fetchWatchlistRemote = () =>
  apiGet<WatchlistResponse>("/api/watchlist");

// Replace-semantics POST: the frontend always sends the full normalized
// list so the backend overwrites whatever it had. Errors are caught here,
// not bubbled, because the user-visible truth lives in localStorage.
export async function syncWatchlistRemote(tickers: string[]): Promise<void> {
  try {
    await apiPost<WatchlistResponse, { tickers: string[] }>(
      "/api/watchlist",
      { tickers },
    );
  } catch {
    // Silent on purpose: a failed sync just means the cron will not pick
    // up the change this run. The user-visible state is already correct.
  }
}
