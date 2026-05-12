// frontend/src/lib/watchlist.ts
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
