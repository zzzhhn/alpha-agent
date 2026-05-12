import { useEffect, useState } from "react";
import { fetchStock, type RatingCard } from "@/lib/api/picks";

export function useStock(ticker: string) {
  const [card, setCard] = useState<RatingCard | null>(null);
  const [stale, setStale] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let alive = true;
    fetchStock(ticker)
      .then((r) => {
        if (!alive) return;
        setCard(r.card);
        setStale(r.stale);
      })
      .catch((e: Error) => {
        if (alive) setError(e);
      });
    return () => {
      alive = false;
    };
  }, [ticker]);

  return { card, stale, error };
}
