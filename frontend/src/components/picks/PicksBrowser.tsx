"use client";

// Client shell for /picks: the server component hands us the initial
// top-50 board, and this layers a debounced ticker search on top that
// re-queries /api/picks/lean. A search widens the limit to 600 so a match
// anywhere in the full ~557-ticker universe (including slow-only "partial"
// rows) is reachable, not just the top of the default board.
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  fetchPicks,
  type FactorMode,
  type PicksResponse,
  type PicksSide,
} from "@/lib/api/picks";
import PicksTable from "./PicksTable";
import { fetchPaperAccount } from "@/lib/api/paper";
import RefreshButton from "./RefreshButton";
import BasketEdgeStrip from "./BasketEdgeStrip";
import ConvictionBand from "./ConvictionBand";
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
import { isPicksSnapshotStale } from "@/lib/picks-freshness";
import {
  DISPATCH_EVENT,
  clearDispatch,
  isInFlight,
  loadDispatch,
  loadSnapshot,
  saveSnapshot,
} from "@/lib/dispatch-state";

type PicksData = PicksResponse;

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
  const [simPositions, setSimPositions] = useState<ReadonlyMap<string, number>>(new Map());
  const [paperCash] = useState(0);

  // Paper trading is now the standalone /paper route (V2), not an in-page
  // modal, so this is the sole source of the "held qty" badge on each pick
  // row: load once on mount, then refresh after any order placed from the
  // SimOrderDrawer quick-entry so the badge stays live without reopening
  // anything.
  const loadSimPositions = useCallback(async () => {
    try {
      const acct = await fetchPaperAccount();
      setSimPositions(new Map(acct.positions.map((p) => [p.ticker, p.qty])));
    } catch {
      // non-fatal — badge just stays at its last known state
    }
  }, []);

  useEffect(() => {
    void loadSimPositions();
  }, [loadSimPositions]);

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
        setData(snap);
      }
      wasInFlightRef.current = true;
    }
    const onDispatch = () => {
      // Snapshot the default board (no active search) for reload-freeze.
      const l = liveRef.current;
      if (!l.search.trim()) {
        saveSnapshot(l.data);
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
  const snapshotStale =
    count > 0 &&
    (!data.tradable || isPicksSnapshotStale(data.as_of, data.stale, now));
  const asOf = data.as_of
    ? data.as_of.replace("T", " ").replace(/:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$/, "") + " UTC"
    : locale === "zh"
      ? "暂无"
      : "n/a";

  const copy =
    locale === "zh"
      ? {
          picks: "选股",
          signals: searching ? `${count} 条匹配` : `${count} 条信号`,
          asOf: "数据时间",
          marketDate: "市场日",
          run: "快照",
          coverage: "覆盖率",
          stale: "数据超过 24 小时",
          placeholder: "搜索 ticker（如 NVDA）",
          paneTitle: "候选明细",
          paneMeta: searching
            ? `“${search.trim().toUpperCase()}” 的搜索结果`
            : "真实信号优先，其后覆盖完整 universe（partial 行数据可能最旧 1 天）",
          loading: "搜索中…",
          empty: "没有匹配的 ticker",
          modeLabel: "决策策略",
          modeShort: "战术 5 日",
          modeLong: "战略 60 日",
          modeTip:
            "战术策略使用冻结的 5 日生产政策与校准。战略策略是独立冻结的 60 日前瞻验证政策，只使用 20 日以上原生周期信号，不沿用 5 日命中率。",
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
          marketDate: "MARKET DATE",
          run: "RUN",
          coverage: "COVERAGE",
          stale: "DATA > 24h OLD",
          placeholder: "Search ticker (e.g. NVDA)",
          paneTitle: "CANDIDATE DETAIL",
          paneMeta: searching
            ? `results for "${search.trim().toUpperCase()}"`
            : "real signals first, then the full universe (partial rows can be ~1d old)",
          loading: "Searching...",
          empty: "No matching ticker",
          modeLabel: "DECISION POLICY",
          modeShort: "Tactical 5d",
          modeLong: "Strategic 60d",
          modeTip:
            "Tactical uses the frozen 5d production policy and calibration. Strategic is an independent frozen 60d forward-validation policy using only signals with 20d+ native horizons; it does not reuse the 5d hit-rate.",
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
      <section className="border-b border-tm-rule bg-tm-bg px-4 py-4" aria-labelledby="picks-heading">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="font-tm-mono text-[10px] uppercase tracking-[0.12em] text-tm-accent">01 · {locale === "zh" ? "理解变化" : "UNDERSTAND CHANGES"}</p>
            <h1 id="picks-heading" className="mt-1 text-xl font-semibold text-tm-fg">{locale === "zh" ? "今日组合决策" : "Today’s Portfolio Decision"}</h1>
            <p className="mt-2 max-w-2xl text-[12px] leading-5 text-tm-muted">
              {locale === "zh" ? "先确认快照与策略，再查看候选及驱动。真正的交易动作在组合工作台完成，避免把单只股票分数误当成仓位指令。" : "Confirm the snapshot and policy, then inspect candidates and drivers. Execute in the portfolio workspace so a single-name score is not mistaken for a position instruction."}
            </p>
          </div>
          <Link href="/paper" prefetch={false} className="inline-flex shrink-0 items-center justify-center border border-tm-accent bg-tm-accent px-4 py-2 font-tm-mono text-[11px] font-semibold text-tm-bg hover:opacity-90">
            {locale === "zh" ? "02 · 打开组合工作台" : "02 · OPEN PORTFOLIO WORKSPACE"}
          </Link>
        </div>
        {factorMode === "long" ? (
          <p className="mt-3 rounded border border-tm-warn/40 bg-tm-warn/10 px-3 py-2 font-tm-mono text-[10.5px] leading-5 text-tm-warn">
            {locale === "zh" ? "战略 60 日策略正在独立前瞻验证，未使用 5 日校准命中率，不应直接与战术榜单的命中率横向比较。" : "The strategic 60d policy is in independent forward validation. It does not use the 5d calibrated hit rate and should not be compared as if both confidence figures shared one basis."}
          </p>
        ) : null}
      </section>
      <TmSubbar>
        <TmSubbarKV label={copy.picks} value={copy.signals} />
        <TmSubbarSep />
        <TmSubbarKV label={copy.asOf} value={asOf} />
        {data.run ? (
          <>
            <TmSubbarSep />
            <TmSubbarKV label={copy.marketDate} value={data.run.market_date} />
            <TmSubbarSep />
            <TmSubbarKV label={copy.run} value={`#${data.run.run_id}`} />
            <TmSubbarSep />
            <TmSubbarKV
              label={copy.coverage}
              value={`${Math.round(data.run.coverage * 100)}%`}
            />
          </>
        ) : null}
        <TmSubbarSep />
        <button
          type="button"
          onClick={onModeToggle}
          title={copy.modeTip}
          className="inline-flex items-center gap-1.5 rounded-md border border-tm-accent/40 bg-tm-accent/10 px-2 py-0.5 font-tm-mono text-[11px] text-tm-accent transition hover:bg-tm-accent/20 focus:outline-none focus:ring-1 focus:ring-tm-accent"
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
              ? "inline-flex items-center gap-1.5 rounded-md border border-tm-neg/40 bg-tm-neg/10 px-2 py-0.5 font-tm-mono text-[11px] text-tm-neg transition hover:bg-tm-neg/20 focus:outline-none focus:ring-1 focus:ring-tm-neg"
              : "inline-flex items-center gap-1.5 rounded-md border border-tm-pos/40 bg-tm-pos/10 px-2 py-0.5 font-tm-mono text-[11px] text-tm-pos transition hover:bg-tm-pos/20 focus:outline-none focus:ring-1 focus:ring-tm-pos"
          }
          aria-label={copy.sideLabel}
        >
          <span className="opacity-70">{copy.sideLabel}</span>
          <span className="font-semibold">
            {side === "short" ? copy.sideShort : copy.sideLong}
          </span>
        </button>
        {snapshotStale ? (
          <>
            <TmSubbarSep />
            <TmStatusPill tone="err">{copy.stale}</TmStatusPill>
          </>
        ) : null}

      </TmSubbar>

      <>
        {!searching && data.changes ? (
          <section className="border-b border-tm-rule bg-tm-bg px-4 py-3" aria-labelledby="changes-heading">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 id="changes-heading" className="font-tm-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-tm-fg">
                {locale === "zh" ? "相对上一快照的组合变化" : "PORTFOLIO CHANGES VS PRIOR SNAPSHOT"}
              </h2>
              {data.changes.available && data.changes.turnover != null ? <span className="font-tm-mono text-[10px] text-tm-muted">{locale === "zh" ? "名单换手" : "NAME TURNOVER"} {(data.changes.turnover * 100).toFixed(1)}%</span> : null}
            </div>
            {data.changes.available ? (
              <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
                <ChangeList tone="text-tm-pos" title={locale === "zh" ? "新增" : "ADDED"} empty={locale === "zh" ? "无新增" : "No additions"} items={data.changes.added.map((item) => `${item.ticker} #${item.current_rank ?? "—"}`)} />
                <ChangeList tone="text-tm-neg" title={locale === "zh" ? "移出" : "REMOVED"} empty={locale === "zh" ? "无移出" : "No removals"} items={data.changes.removed.map((item) => `${item.ticker} #${item.prior_rank ?? "—"}`)} />
                <ChangeList tone="text-tm-accent" title={locale === "zh" ? "评级变化" : "TIER CHANGES"} empty={locale === "zh" ? "无评级变化" : "No tier changes"} items={data.changes.tier_changes.map((item) => `${item.ticker} ${item.prior_tier ?? "—"}→${item.current_tier ?? "—"}`)} />
              </div>
            ) : (
              <p className="mt-2 font-tm-mono text-[10px] leading-5 text-tm-muted">{factorMode === "long" ? (locale === "zh" ? "独立战略政策尚未积累两个同政策快照，因此不伪造跨政策变化。" : "The independent strategic policy does not yet have two same-policy snapshots, so cross-policy changes are not fabricated.") : (locale === "zh" ? "尚无可比的上一份同政策快照。" : "No comparable prior snapshot exists for this policy.")}</p>
            )}
          </section>
        ) : null}
        {/* BASKET.EDGE strip — the engine's honest edge is the ranked long-short
            basket, not single-name direction. Pinned above the picks table.
            Its Paper Trading entry now links to /paper (V2: no longer a modal). */}
        <BasketEdgeStrip />

          <div className="flex justify-end px-4 pt-3">
            <RefreshButton />
          </div>

          {/* ★ Highest-Conviction hero band — top-3 of the current board as
              decision-first cards (ALPHACORE design). Hidden during an active
              search, where the result set is a lookup, not a conviction ranking. */}
          {!searching && !snapshotStale ? <ConvictionBand picks={data.picks} /> : null}

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
              <div className="mx-3 mt-2 rounded border border-tm-accent/40 bg-tm-accent/10 px-3 py-1.5 font-tm-mono text-xs text-tm-accent">
                {t(locale, "picks.freeze_banner").replace(
                  "{min}",
                  String(refreshRemainingMin),
                )}
              </div>
            ) : justRefreshed ? (
              <div className="mx-3 mt-2 rounded border border-tm-pos/40 bg-tm-pos/10 px-3 py-1.5 font-tm-mono text-xs text-tm-pos">
                {t(locale, "picks.refreshed_banner")}
              </div>
            ) : snapshotStale ? (
              <div className="mx-3 mt-2 rounded border border-tm-neg/40 bg-tm-neg/10 px-3 py-2 font-tm-mono text-xs leading-5 text-tm-neg">
                {t(locale, "picks.stale_freeze_banner")}
              </div>
            ) : null}
            <div className="flex items-center gap-2 px-3 py-2">
              <input
                type="text"
                aria-label={copy.placeholder}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={copy.placeholder}
                maxLength={12}
                className="w-56 rounded border border-tm-rule bg-tm-bg-2 px-2 py-1 font-tm-mono text-[11px] text-tm-fg placeholder:text-tm-muted focus:border-tm-accent focus:outline-none"
              />
              {loading ? (
                <span className="font-tm-mono text-[11px] text-tm-muted">
                  {copy.loading}
                </span>
              ) : null}
            </div>
            {count === 0 && searching ? (
              <div className="px-3 py-6 font-tm-mono text-[11px] text-tm-muted">
                {copy.empty}
              </div>
            ) : (
              <PicksTable
                picks={data.picks}
                isWatched={isWatched}
                simPositions={simPositions}
                cash={paperCash}
                onOrderPlaced={loadSimPositions}
                ranked={data.ranked && !searching}
                ordersDisabled={snapshotStale || !data.tradable || searching}
              />
            )}
          </TmPane>
        </>
    </>
  );
}

function ChangeList({ title, items, empty, tone }: { readonly title: string; readonly items: readonly string[]; readonly empty: string; readonly tone: string }) {
  return <div className="rounded border border-tm-rule bg-tm-bg-2 px-3 py-2"><div className={`font-tm-mono text-[9.5px] font-semibold uppercase ${tone}`}>{title}</div><p className="mt-1 truncate font-tm-mono text-[10.5px] text-tm-fg-2" title={items.join(" · ")}>{items.length ? items.slice(0, 5).join(" · ") : empty}</p></div>;
}
