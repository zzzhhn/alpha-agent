"use client";

// Client shell for /picks: the server component hands us the initial
// top-50 board, and this layers a debounced ticker search on top that
// re-queries /api/picks/lean. A search widens the limit to 600 so a match
// anywhere in the full ~557-ticker universe (including slow-only "partial"
// rows) is reachable, not just the top of the default board.
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchPicks, type RatingCard } from "@/lib/api/picks";
import PicksTable from "./PicksTable";
import RefreshButton from "./RefreshButton";
import { TmPane } from "@/components/tm/TmPane";
import {
  TmSubbar,
  TmSubbarKV,
  TmSubbarSep,
  TmStatusPill,
} from "@/components/tm/TmSubbar";
import { useLocale } from "@/components/layout/LocaleProvider";
import { useWatchlist } from "@/hooks/useWatchlist";

type PicksData = { picks: RatingCard[]; as_of: string | null; stale: boolean };

export default function PicksBrowser({
  initialData,
}: {
  initialData: PicksData;
}) {
  const [data, setData] = useState<PicksData>(initialData);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const { locale } = useLocale();
  const mounted = useRef(false);
  // Called once here, threaded down as a prop, so the localStorage read +
  // storage listener happen per-table rather than per-row.
  const { isWatched } = useWatchlist();

  const runSearch = useCallback(async (q: string) => {
    setLoading(true);
    try {
      // No query: default top-50 board. Query: widen to the full universe
      // so the match is found wherever it ranks.
      const trimmed = q.trim();
      const next = await fetchPicks(trimmed ? 600 : 50, trimmed || undefined);
      setData(next);
    } catch {
      // Keep the last good data on a transient failure; a hard failure is
      // caught by the route-level error.tsx.
    } finally {
      setLoading(false);
    }
  }, []);

  // Debounce the search input. Skip the mount fire so initialData renders
  // immediately without a redundant re-fetch.
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    const id = setTimeout(() => runSearch(search), 300);
    return () => clearTimeout(id);
  }, [search, runSearch]);

  const searching = search.trim().length > 0;
  const count = data.picks.length;
  const asOf = data.as_of
    ? new Date(data.as_of).toLocaleString()
    : locale === "zh"
      ? "暂无"
      : "n/a";

  const copy =
    locale === "zh"
      ? {
          picks: "选股",
          signals: searching ? `${count} 条匹配` : `${count} 条信号`,
          asOf: "数据时间",
          stale: "数据超过 24 小时",
          placeholder: "搜索 ticker（如 NVDA）",
          paneTitle: "今日选股",
          paneMeta: searching
            ? `“${search.trim().toUpperCase()}” 的搜索结果`
            : "真实信号优先，其后覆盖完整 universe（partial 行数据可能最旧 1 天）",
          loading: "搜索中…",
          empty: "没有匹配的 ticker",
        }
      : {
          picks: "PICKS",
          signals: searching ? `${count} matches` : `${count} signals`,
          asOf: "AS OF",
          stale: "DATA > 24h OLD",
          placeholder: "Search ticker (e.g. NVDA)",
          paneTitle: "TODAY'S PICKS",
          paneMeta: searching
            ? `results for "${search.trim().toUpperCase()}"`
            : "real signals first, then the full universe (partial rows can be ~1d old)",
          loading: "Searching...",
          empty: "No matching ticker",
        };

  return (
    <>
      <TmSubbar>
        <TmSubbarKV label={copy.picks} value={copy.signals} />
        <TmSubbarSep />
        <TmSubbarKV label={copy.asOf} value={asOf} />
        {data.stale ? (
          <>
            <TmSubbarSep />
            <TmStatusPill tone="err">{copy.stale}</TmStatusPill>
          </>
        ) : null}
      </TmSubbar>

      <div className="flex justify-end px-4 pt-3">
        <RefreshButton />
      </div>

      <TmPane title={copy.paneTitle} meta={copy.paneMeta}>
        <div className="flex items-center gap-2 px-3 py-2">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={copy.placeholder}
            maxLength={12}
            className="w-56 rounded border border-tm-rule bg-tm-bg-2 px-2 py-1 font-tm-mono text-[11px] text-tm-fg placeholder:text-tm-muted focus:border-tm-accent focus:outline-none"
          />
          {loading ? (
            <span className="font-tm-mono text-[10px] text-tm-muted">
              {copy.loading}
            </span>
          ) : null}
        </div>
        {count === 0 && searching ? (
          <div className="px-3 py-6 font-tm-mono text-[11px] text-tm-muted">
            {copy.empty}
          </div>
        ) : (
          <PicksTable picks={data.picks} isWatched={isWatched} />
        )}
      </TmPane>
    </>
  );
}
