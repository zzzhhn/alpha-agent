"use client";

import { useEffect, useState } from "react";
import { getWatchlist, addToWatchlist, removeFromWatchlist } from "@/lib/watchlist";
import { TmButton } from "@/components/tm/TmButton";

const FORM_INPUT =
  "h-7 flex-1 bg-tm-bg-2 border border-tm-rule px-2 font-tm-mono text-[11.5px] text-tm-fg outline-none transition-colors placeholder:text-tm-muted focus:border-tm-accent";

export default function WatchlistEditor() {
  const [list, setList] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setList(getWatchlist());
  }, []);

  function handleAdd() {
    const ticker = draft.trim().toUpperCase();
    if (!ticker) return;
    if (!/^[A-Z]{1,5}$/.test(ticker)) {
      setError(`"${ticker}" doesn't look like a valid ticker (1-5 uppercase letters)`);
      return;
    }
    setList(addToWatchlist(ticker));
    setDraft("");
    setError(null);
  }

  function handleRemove(ticker: string) {
    setList(removeFromWatchlist(ticker));
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") handleAdd();
  }

  return (
    <div className="flex flex-col gap-3 px-3 py-3">
      <div className="flex gap-2">
        <input
          className={FORM_INPUT}
          placeholder="Ticker (e.g. AAPL) · Enter to add"
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            setError(null);
          }}
          onKeyDown={handleKeyDown}
        />
        <TmButton variant="primary" onClick={handleAdd}>+ ADD</TmButton>
      </div>
      {error ? (
        <span className="font-tm-mono text-[10px] text-tm-neg">{error}</span>
      ) : null}
      {list.length === 0 ? (
        <div className="font-tm-mono text-[10.5px] text-tm-muted py-2">
          Empty — add tickers above
        </div>
      ) : (
        <ul className="flex flex-col divide-y divide-tm-rule border border-tm-rule">
          {list.map((ticker) => (
            <li
              key={ticker}
              className="flex items-center justify-between px-3 py-1.5"
            >
              <span className="font-tm-mono text-[11px] text-tm-fg">{ticker}</span>
              <button
                type="button"
                className="font-tm-mono text-[10px] text-tm-neg hover:text-tm-neg cursor-pointer transition-colors"
                onClick={() => handleRemove(ticker)}
              >
                × REMOVE
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
