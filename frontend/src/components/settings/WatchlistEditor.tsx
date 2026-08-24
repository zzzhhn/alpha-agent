"use client";

import { useEffect, useState } from "react";
import { getWatchlist, addToWatchlist, removeFromWatchlist } from "@/lib/watchlist";
import { syncWatchlistRemote } from "@/lib/api/watchlist";
import { TmButton } from "@/components/tm/TmButton";
import { TmInput } from "@/components/tm/TmField";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";

export default function WatchlistEditor() {
  const { locale } = useLocale();
  const [list, setList] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const initial = getWatchlist();
    setList(initial);
    // One-time reconcile: push whatever is in localStorage to the backend
    // so the cron sees it. Covers pre-existing entries from before
    // dual-write shipped. Future add/remove already dual-write via
    // setWatchlist; this is the catch-up for the existing state.
    void syncWatchlistRemote(initial);
  }, []);

  function handleAdd() {
    const ticker = draft.trim().toUpperCase();
    if (!ticker) return;
    if (!/^[A-Z]{1,5}$/.test(ticker)) {
      setError(t(locale, "watchlist.invalid_ticker").replace("{ticker}", ticker));
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
        <TmInput
          fieldSize="sm"
          placeholder={t(locale, "watchlist.input_placeholder")}
          value={draft}
          onChange={(next) => {
            setDraft(next);
            setError(null);
          }}
          onKeyDown={handleKeyDown}
          className="min-w-0 flex-1"
        />
        <TmButton variant="primary" onClick={handleAdd}>+ ADD</TmButton>
      </div>
      {error ? (
        <span className="font-tm-mono text-[10px] text-tm-neg">{error}</span>
      ) : null}
      {list.length === 0 ? (
        <div className="font-tm-mono text-[10.5px] text-tm-muted py-2">
          {t(locale, "watchlist.empty")}
        </div>
      ) : (
        <ul className="flex flex-col divide-y divide-tm-rule border border-tm-rule">
          {list.map((ticker) => (
            <li
              key={ticker}
              className="flex items-center justify-between px-3 py-1.5"
            >
              <span className="font-tm-mono text-[11px] text-tm-fg">{ticker}</span>
              <TmButton
                variant="ghost"
                size="xs"
                className="px-0 text-tm-neg hover:text-tm-neg"
                onClick={() => handleRemove(ticker)}
              >
                × REMOVE
              </TmButton>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
