"use client";

// Client shell for /picks: the server component hands us the initial
// top-50 board, and this layers a debounced ticker search on top that
// re-queries /api/picks/lean. A search widens the limit to 600 so a match
// anywhere in the full ~557-ticker universe (including slow-only "partial"
// rows) is reachable, not just the top of the default board.
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchPicks, type FactorMode, type RatingCard } from "@/lib/api/picks";
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
// Shared hook so a flip on Stock detail's AttributionTable / Radar
// propagates back here via the storage event broadcast inside the hook.
import { useFactorMode } from "@/hooks/useFactorMode";

type PicksData = { picks: RatingCard[]; as_of: string | null; stale: boolean };

export default function PicksBrowser({
  initialData,
}: {
  initialData: PicksData;
}) {
  const [data, setData] = useState<PicksData>(initialData);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  // SHORT (12d/60d, default — short-line/intraday-aligned) vs LONG (252d/126d,
  // academic). Hook handles SSR-safe hydration + cross-tab + same-tab storage
  // event broadcast so AttributionTable's pill on Stock detail flips here.
  const [factorMode, setFactorMode] = useFactorMode();
  const { locale } = useLocale();
  const mounted = useRef(false);
  // Called once here, threaded down as a prop, so the localStorage read +
  // storage listener happen per-table rather than per-row.
  const { isWatched } = useWatchlist();

  // Generation counter discards stale fetch results when the user types
  // quickly. Without it, the response for "NV" can arrive AFTER "NVDA" and
  // overwrite the narrower result set with broader data, making subsequent
  // clicks navigate to the wrong ticker.
  const reqIdRef = useRef(0);

  const runSearch = useCallback(
    async (q: string, mode: FactorMode) => {
      const reqId = ++reqIdRef.current;
      setLoading(true);
      try {
        // No query: default top-50 board. Query: widen to the full universe
        // so the match is found wherever it ranks.
        const trimmed = q.trim();
        const next = await fetchPicks(
          trimmed ? 600 : 50,
          trimmed || undefined,
          mode,
        );
        if (reqId !== reqIdRef.current) return;
        setData(next);
      } catch {
        // Keep the last good data on a transient failure; a hard failure is
        // caught by the route-level error.tsx.
      } finally {
        if (reqId === reqIdRef.current) setLoading(false);
      }
    },
    [],
  );

  // Debounce the search input + re-fire when factorMode flips. Skip the
  // mount fire so initialData renders immediately without a redundant
  // re-fetch — but the post-hydration mode flip DOES fire a re-fetch if
  // the user's stored pref is "long" (different from SSR's "short" default).
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      // First effect run after hydration: only re-fetch if mode differs
      // from the SSR default of "short".
      if (factorMode === "long") {
        runSearch(search, factorMode);
      }
      return;
    }
    const id = setTimeout(() => runSearch(search, factorMode), 300);
    return () => clearTimeout(id);
  }, [search, factorMode, runSearch]);

  const onModeToggle = useCallback(() => {
    setFactorMode(factorMode === "short" ? "long" : "short");
  }, [factorMode, setFactorMode]);

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
          modeLabel: "因子模式",
          modeShort: "短线 (12d/60d)",
          modeLong: "长线 (252d/126d)",
          modeTip:
            "短线模式 = 12 日动量减 3 月波动,跟新闻/技术面/盘前同时间维度,适合 swing/intraday。长线 = 12 月动量减 6 月波动,适合月度/季度持仓。点击切换。",
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
          modeLabel: "FACTOR MODE",
          modeShort: "Short (12d/60d)",
          modeLong: "Long (252d/126d)",
          modeTip:
            "Short = 12d momentum − 3mo vol, aligned with news/technicals/premarket horizon, suited for swing/intraday. Long = 12mo momentum − 6mo vol, suited for monthly/quarterly holding. Click to toggle.",
        };

  return (
    <>
      <TmSubbar>
        <TmSubbarKV label={copy.picks} value={copy.signals} />
        <TmSubbarSep />
        <TmSubbarKV label={copy.asOf} value={asOf} />
        <TmSubbarSep />
        <button
          type="button"
          onClick={onModeToggle}
          title={copy.modeTip}
          className="inline-flex items-center gap-1.5 rounded-md border border-tm-accent/40 bg-tm-accent/10 px-2 py-0.5 font-tm-mono text-[10px] text-tm-accent transition hover:bg-tm-accent/20 focus:outline-none focus:ring-1 focus:ring-tm-accent"
          aria-label={copy.modeLabel}
        >
          <span className="opacity-70">{copy.modeLabel}</span>
          <span className="font-semibold">
            {factorMode === "short" ? copy.modeShort : copy.modeLong}
          </span>
        </button>
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
