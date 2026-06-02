"use client";

// Client shell for /picks: the server component hands us the initial
// top-50 board, and this layers a debounced ticker search on top that
// re-queries /api/picks/lean. A search widens the limit to 600 so a match
// anywhere in the full ~557-ticker universe (including slow-only "partial"
// rows) is reachable, not just the top of the default board.
import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchPicks,
  type FactorMode,
  type PicksSide,
  type RatingCard,
} from "@/lib/api/picks";
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
import { t } from "@/lib/i18n";
import { useWatchlist } from "@/hooks/useWatchlist";
// Shared hook so a flip on Stock detail's AttributionTable / Radar
// propagates back here via the storage event broadcast inside the hook.
import { useFactorMode } from "@/hooks/useFactorMode";
import {
  DISPATCH_EVENT,
  clearDispatch,
  isInFlight,
  loadDispatch,
  loadSnapshot,
  saveSnapshot,
} from "@/lib/dispatch-state";

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
  // P1-2: long = top-N by composite (highest-conviction longs, the SSR
  // default), short = bottom-N (most bearish UW/SELL names the top view
  // never surfaces). Local state — not persisted; each visit starts on
  // the long board.
  const [side, setSide] = useState<PicksSide>("long");
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
    async (q: string, mode: FactorMode, sideArg: PicksSide) => {
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
          sideArg,
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

  // Debounce the search input + re-fire when factorMode / side flips. Skip
  // the mount fire so initialData renders immediately without a redundant
  // re-fetch — but a post-hydration flip away from the SSR defaults
  // (factorMode="short", side="long") DOES fire a re-fetch.
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      if (factorMode === "long" || side !== "long") {
        runSearch(search, factorMode, side);
      }
      return;
    }
    const id = setTimeout(() => runSearch(search, factorMode, side), 300);
    return () => clearTimeout(id);
  }, [search, factorMode, side, runSearch]);

  const onModeToggle = useCallback(() => {
    setFactorMode(factorMode === "short" ? "long" : "short");
  }, [factorMode, setFactorMode]);

  const onSideToggle = useCallback(() => {
    setSide((s) => (s === "long" ? "short" : "long"));
  }, []);

  // ── Refresh-window snapshot freeze (#4) ──────────────────────────────────
  // The board updates progressively over the ~18min dispatch window, so a
  // mid-window reload would otherwise show a different half-updated list each
  // time. PicksBrowser doesn't poll, so same-tab the list is frozen naturally;
  // the only thing that changes it mid-window is a page reload (SSR re-fetch).
  // So: on dispatch, snapshot the default board; on mount during the window,
  // serve that snapshot instead of the half-updated SSR data; when the window
  // ends, refetch once and flash an "updated" banner.
  const [now, setNow] = useState(() => Date.now());
  const [justRefreshed, setJustRefreshed] = useState(false);
  // Gate localStorage-derived UI on mount so SSR and first client render agree
  // (loadDispatch returns null server-side but a value client-side -> mismatch).
  const [hydrated, setHydrated] = useState(false);
  const liveRef = useRef({ data, search, factorMode, side });
  liveRef.current = { data, search, factorMode, side };
  const wasInFlightRef = useRef(false);

  useEffect(() => {
    setHydrated(true);
    // Mount: during an in-flight window, prefer the frozen snapshot over the
    // progressively-updating SSR data.
    if (isInFlight(loadDispatch())) {
      const snap = loadSnapshot();
      if (snap) {
        setData({ picks: snap.picks, as_of: snap.as_of, stale: snap.stale });
      }
      wasInFlightRef.current = true;
    }
    const onDispatch = () => {
      // Snapshot the default board (no active search) for reload-freeze.
      const l = liveRef.current;
      if (!l.search.trim()) {
        saveSnapshot({
          picks: l.data.picks,
          as_of: l.data.as_of,
          stale: l.data.stale,
        });
      }
      wasInFlightRef.current = true;
      setNow(Date.now());
    };
    window.addEventListener(DISPATCH_EVENT, onDispatch);
    const id = setInterval(() => {
      setNow(Date.now());
      if (wasInFlightRef.current && !isInFlight(loadDispatch())) {
        // Window ended: drop the freeze, pull fresh once, flash a banner.
        wasInFlightRef.current = false;
        clearDispatch();
        const l = liveRef.current;
        runSearch(l.search, l.factorMode, l.side);
        setJustRefreshed(true);
        setTimeout(() => setJustRefreshed(false), 8000);
      }
    }, 5000);
    return () => {
      window.removeEventListener(DISPATCH_EVENT, onDispatch);
      clearInterval(id);
    };
    // Mount-only: refs carry the latest values into the listener/interval.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runSearch]);

  const dispatch = hydrated ? loadDispatch() : null;
  const refreshing = isInFlight(dispatch, now);
  const refreshRemainingMin = dispatch
    ? Math.max(Math.ceil((dispatch.at + dispatch.etaMin * 60_000 - now) / 60_000), 0)
    : 0;

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
          sideLabel: "方向",
          sideLong: "做多榜",
          sideShort: "做空榜",
          sideTip:
            "做多榜 = composite 最高的票(最强 conviction longs)。做空榜 = composite 最低的票(最弱 / UW/SELL tier),默认榜单看不到它们因为排在 universe 底部。点击切换。",
          metaLong:
            "composite 最高优先(真实信号优先,partial 行数据可能最旧 1 天)",
          metaShort:
            "composite 最低优先 — universe 底部的看空候选(UW/SELL),默认做多榜不显示",
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
          sideLabel: "SIDE",
          sideLong: "Longs",
          sideShort: "Shorts",
          sideTip:
            "Longs = the highest-composite names (strongest conviction). Shorts = the lowest-composite names (weakest / UW/SELL tier), which the default board never surfaces because they rank at the bottom of the universe. Click to toggle.",
          metaLong:
            "highest composite first (real signals first; partial rows can be ~1d old)",
          metaShort:
            "lowest composite first — the bottom-of-universe short candidates (UW/SELL) the long board hides",
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
        <TmSubbarSep />
        <button
          type="button"
          onClick={onSideToggle}
          title={copy.sideTip}
          className={
            side === "short"
              ? "inline-flex items-center gap-1.5 rounded-md border border-tm-neg/40 bg-tm-neg/10 px-2 py-0.5 font-tm-mono text-[10px] text-tm-neg transition hover:bg-tm-neg/20 focus:outline-none focus:ring-1 focus:ring-tm-neg"
              : "inline-flex items-center gap-1.5 rounded-md border border-tm-pos/40 bg-tm-pos/10 px-2 py-0.5 font-tm-mono text-[10px] text-tm-pos transition hover:bg-tm-pos/20 focus:outline-none focus:ring-1 focus:ring-tm-pos"
          }
          aria-label={copy.sideLabel}
        >
          <span className="opacity-70">{copy.sideLabel}</span>
          <span className="font-semibold">
            {side === "short" ? copy.sideShort : copy.sideLong}
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

      <TmPane
        title={copy.paneTitle}
        meta={
          searching
            ? copy.paneMeta
            : side === "short"
              ? copy.metaShort
              : copy.metaLong
        }
      >
        {refreshing ? (
          <div className="mx-3 mt-2 rounded border border-tm-accent/40 bg-tm-accent/10 px-3 py-1.5 font-tm-mono text-[10.5px] text-tm-accent">
            {t(locale, "picks.freeze_banner").replace(
              "{min}",
              String(refreshRemainingMin),
            )}
          </div>
        ) : justRefreshed ? (
          <div className="mx-3 mt-2 rounded border border-tm-pos/40 bg-tm-pos/10 px-3 py-1.5 font-tm-mono text-[10.5px] text-tm-pos">
            {t(locale, "picks.refreshed_banner")}
          </div>
        ) : null}
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
