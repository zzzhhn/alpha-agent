"use client";

import { useEffect, useState } from "react";
import { getWatchlist, addToWatchlist, removeFromWatchlist } from "@/lib/watchlist";
import { TmButton } from "@/components/tm/TmButton";
import { TmInput } from "@/components/tm/TmField";
import { TmPagination } from "@/components/tm/TmPagination";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";

export default function WatchlistEditor() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [list, setList] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const pageSize = 8;
  const activePage = Math.min(page, Math.max(1, Math.ceil(list.length / pageSize)));

  useEffect(() => {
    const initial = getWatchlist();
    setList(initial);
    // Opening Settings must be read-only. A stale or empty local list must
    // not replace the server mirror; explicit add/remove still dual-write.
  }, []);

  function handleAdd() {
    const ticker = draft.trim().toUpperCase();
    if (!ticker) return;
    if (!/^[A-Z]{1,5}$/.test(ticker)) {
      setError(t(locale, "watchlist.invalid_ticker").replace("{ticker}", ticker));
      return;
    }
    const next = addToWatchlist(ticker);
    setList([...next]);
    setPage(Math.floor(next.indexOf(ticker) / pageSize) + 1);
    setDraft("");
    setError(null);
  }

  function handleRemove(ticker: string) {
    setList(removeFromWatchlist(ticker));
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !e.nativeEvent.isComposing) handleAdd();
  }

  return (
    <div className="flex flex-col gap-3 px-3 py-3">
      <div className="flex items-start gap-2">
        <TmInput
          fieldSize="sm"
          label={zh ? "股票代码" : "Ticker symbol"}
          error={error ?? undefined}
          placeholder={t(locale, "watchlist.input_placeholder")}
          value={draft}
          onChange={(next) => {
            setDraft(next);
            setError(null);
          }}
          onKeyDown={handleKeyDown}
          className="min-w-0 flex-1"
        />
        <TmButton variant="primary" className="mt-5" onClick={handleAdd} disabled={!draft.trim()}>
          {zh ? "添加" : "Add"}
        </TmButton>
      </div>
      {list.length === 0 ? (
        <div className="font-tm-mono text-xs text-tm-muted py-2">
          {t(locale, "watchlist.empty")}
        </div>
      ) : (
        <ul className="flex flex-col divide-y divide-tm-rule border border-tm-rule">
          {list.slice((activePage - 1) * pageSize, activePage * pageSize).map((ticker) => (
            <li
              key={ticker}
              className="flex items-center justify-between px-3 py-1.5"
            >
              <span className="font-tm-mono text-xs text-tm-fg">{ticker}</span>
              <TmButton
                variant="ghost"
                size="xs"
                className="px-0 text-tm-neg hover:text-tm-neg"
                onClick={() => handleRemove(ticker)}
                aria-label={zh ? `移除 ${ticker}` : `Remove ${ticker}`}
              >
                {zh ? "移除" : "Remove"}
              </TmButton>
            </li>
          ))}
        </ul>
      )}
      {list.length > pageSize && <TmPagination page={activePage} pageSize={pageSize} totalItems={list.length}
        onPageChange={setPage} onPageSizeChange={()=>{}} pageSizeOptions={[pageSize]}
        labels={{navigation:zh ? "关注列表分页" : "Watchlist pagination",previous:zh ? "上一页" : "Prev",next:zh ? "下一页" : "Next",previousAriaLabel:zh ? "上一页" : "Previous page",nextAriaLabel:zh ? "下一页" : "Next page",pageSize:zh ? "每页" : "Per page",page:(current,total)=>`${current} / ${total}`,total:total=>zh ? `${total} 只` : `${total} tickers`}}/>}
    </div>
  );
}
