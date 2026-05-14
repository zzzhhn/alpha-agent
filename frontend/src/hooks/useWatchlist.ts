"use client";

import { useCallback, useEffect, useState } from "react";
import { getWatchlist } from "@/lib/watchlist";

// Reactive read-only view of the localStorage watchlist. localStorage is
// unreadable during SSR, so this reads on mount and re-syncs on cross-tab
// `storage` events. Call it once near the top of a list and thread the
// returned `isWatched` down as a prop, rather than calling it per row.
export function useWatchlist() {
  const [watched, setWatched] = useState<Set<string>>(new Set());

  useEffect(() => {
    const sync = () => setWatched(new Set(getWatchlist()));
    sync();
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);

  // Stored tickers are already uppercase (setWatchlist normalizes on write);
  // uppercase the lookup argument so callers can pass any casing.
  const isWatched = useCallback(
    (ticker: string) => watched.has(ticker.toUpperCase()),
    [watched],
  );

  return { isWatched, count: watched.size };
}
