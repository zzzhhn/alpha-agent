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
  type PicksResponse,
  type PicksSide,
} from "@/lib/api/picks";
import PicksTable from "./PicksTable";
import { fetchPaperAccount } from "@/lib/api/paper";
import RefreshButton from "./RefreshButton";
import BasketEdgeStrip from "./BasketEdgeStrip";
import InvestmentEvidence from "./InvestmentEvidence";
import InvestmentProfile from "./InvestmentProfile";
import InvestmentNotebook from "./InvestmentNotebook";
import ConvictionBand from "./ConvictionBand";
import { TmPane } from "@/components/tm/TmPane";
import { TmStatePane } from "@/components/tm/TmStatePane";
import {
  TmSubbar,
  TmSubbarKV,
  TmSubbarSep,
  TmStatusPill,
} from "@/components/tm/TmSubbar";
import { TmButton, TmDisclosureButton, TmLinkButton } from "@/components/tm/TmButton";
import { TmInput } from "@/components/tm/TmField";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { useWatchlist } from "@/hooks/useWatchlist";
// Shared hook so a flip on Stock detail's AttributionTable / Radar
// propagates back here via the storage event broadcast inside the hook.
import { useFactorMode } from "@/hooks/useFactorMode";
import { picksSnapshotStatus } from "@/lib/picks-freshness";
import {
  DISPATCH_EVENT,
  isInFlight,
  loadDispatch,
  loadSnapshot,
  REFRESH_SETTLED_EVENT,
  saveSnapshot,
  type RefreshSettledDetail,
} from "@/lib/dispatch-state";
import { WorkbenchHeader } from "@/components/workbench/WorkbenchHeader";

type PicksData = PicksResponse;

export default function PicksBrowser({
  initialData,
}: {
  initialData: PicksData;
}) {
  const [data, setData] = useState<PicksData>(initialData);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);
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
  const [paperCash, setPaperCash] = useState<number | undefined>();
  const [showResearch, setShowResearch] = useState(false);
  const [showMethod, setShowMethod] = useState(false);
  const [resultQuery, setResultQuery] = useState({ search: "", mode: "short", side: "long" });

  // Paper trading is now the standalone /paper route (V2), not an in-page
  // modal, so this is the sole source of the "held qty" badge on each pick
  // row: load once on mount, then refresh after any order placed from the
  // SimOrderDrawer quick-entry so the badge stays live without reopening
  // anything.
  const loadSimPositions = useCallback(async () => {
    try {
      const acct = await fetchPaperAccount();
      setSimPositions(new Map(acct.positions.map((p) => [p.ticker, p.qty])));
      setPaperCash(acct.available_cash);
    } catch {
      // non-fatal — badge just stays at its last known state
      setPaperCash(undefined);
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
        setResultQuery({ search: trimmed.toUpperCase(), mode, side: sideArg });
        setRequestError(null);
      } catch (error) {
        if (reqId === reqIdRef.current) {
          setRequestError(error instanceof Error ? error.message : String(error));
        }
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
      if (factorMode === "long" || side !== "long" || initialData.stale) {
        runSearch(search, factorMode, side);
      }
      return;
    }
    const id = setTimeout(() => runSearch(search, factorMode, side), 300);
    return () => clearTimeout(id);
  }, [search, factorMode, side, runSearch, initialData.stale]);

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
  // serve that snapshot instead of the half-updated SSR data; only a terminal
  // backend publish audit releases the freeze and chooses the result banner.
  const [now, setNow] = useState(() => Date.now());
  const [refreshResult, setRefreshResult] =
    useState<RefreshSettledDetail | null>(null);
  // Gate localStorage-derived UI on mount so SSR and first client render agree
  // (loadDispatch returns null server-side but a value client-side -> mismatch).
  const [hydrated, setHydrated] = useState(false);
  const liveRef = useRef({ data, search, factorMode, side });
  liveRef.current = { data, search, factorMode, side };

  useEffect(() => {
    setHydrated(true);
    // Mount: during an in-flight window, prefer the frozen snapshot over the
    // progressively-updating SSR data.
    if (isInFlight(loadDispatch())) {
      const snap = loadSnapshot();
      if (snap) {
        setData(snap);
      }
    }
    const onDispatch = () => {
      // Snapshot the default board (no active search) for reload-freeze.
      const l = liveRef.current;
      if (!l.search.trim()) {
        saveSnapshot(l.data);
      }
      setRefreshResult(null);
      setNow(Date.now());
    };
    const onSettled = (event: Event) => {
      const detail = (event as CustomEvent<RefreshSettledDetail>).detail;
      const l = liveRef.current;
      void runSearch(l.search, l.factorMode, l.side).finally(() => {
        setRefreshResult(detail);
        setTimeout(() => setRefreshResult(null), 12_000);
      });
    };
    window.addEventListener(DISPATCH_EVENT, onDispatch);
    window.addEventListener(REFRESH_SETTLED_EVENT, onSettled);
    const id = setInterval(() => {
      setNow(Date.now());
    }, 5000);
    return () => {
      window.removeEventListener(DISPATCH_EVENT, onDispatch);
      window.removeEventListener(REFRESH_SETTLED_EVENT, onSettled);
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
  const queryPending = loading || resultQuery.search !== search.trim().toUpperCase()
    || resultQuery.mode !== factorMode || resultQuery.side !== side;
  const count = data.picks.length;
  const snapshotStatus = picksSnapshotStatus(data.as_of, data.stale);
  const snapshotStale = !data.tradable || snapshotStatus !== "current";
  const asOf = data.as_of
    ? data.as_of.replace("T", " ").replace(/:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$/, "") + " UTC"
    : locale === "zh"
      ? "暂无"
      : "n/a";

  const copy =
    locale === "zh"
      ? {
          picks: "选股",
          signals: resultQuery.search ? `${count} 条匹配` : `${count} 条信号`,
          asOf: "数据时间",
          marketDate: "市场日",
          run: "快照",
          coverage: "覆盖率",
          stale: "推荐快照不可交易",
          placeholder: "搜索股票代码，如 NVDA",
          paneTitle: "候选明细",
          paneMeta: searching
            ? `“${search.trim().toUpperCase()}” 的搜索结果`
            : "真实信号优先，其后覆盖完整 universe（partial 行数据可能最旧 1 天）",
          loading: "正在更新候选…",
          empty: "没有匹配的股票代码",
          modeLabel: "决策策略",
          modeShort: "战术 5 日",
          modeLong: "战略 60 日",
          modeTip:
            "战术策略使用冻结的 5 日生产政策与校准。战略策略是独立冻结的 60 日前瞻验证政策，只使用 20 日以上原生周期信号，不沿用 5 日校准置信度。",
          sideLabel: "方向",
          sideLong: "做多榜",
          sideShort: "做空榜",
          sideTip:
            "做多榜按模型排名分从高到低排列；做空榜从低到高排列，展示偏空评级候选。排名与评级不是交易指令。点击切换方向。",
          metaLong:
            "模型排名分由高到低 · 不完整信号单独标注",
          metaShort:
            "模型排名分由低到高 · 偏空候选 UW／SELL",
        }
      : {
          picks: "PICKS",
          signals: resultQuery.search ? `${count} matches` : `${count} signals`,
          asOf: "AS OF",
          marketDate: "MARKET DATE",
          run: "RUN",
          coverage: "COVERAGE",
          stale: "SNAPSHOT NOT TRADABLE",
          placeholder: "Search ticker (e.g. NVDA)",
          paneTitle: "CANDIDATE DETAIL",
          paneMeta: searching
            ? `results for "${search.trim().toUpperCase()}"`
            : "real signals first, then the full universe (partial rows can be ~1d old)",
          loading: "Updating candidates…",
          empty: "No matching ticker",
          modeLabel: "DECISION POLICY",
          modeShort: "Tactical 5d",
          modeLong: "Strategic 60d",
          modeTip:
            "Tactical uses the frozen 5d production policy and calibration. Strategic is an independent frozen 60d forward-validation policy using only signals with 20d+ native horizons; it does not reuse the 5d calibrated confidence.",
          sideLabel: "SIDE",
          sideLong: "Longs",
          sideShort: "Shorts",
          sideTip:
            "Longs = the highest-composite names (strongest conviction). Shorts = the lowest-composite names (weakest / UW/SELL tier), which the default board never surfaces because they rank at the bottom of the universe. Click to toggle.",
          metaLong:
            "Highest model rank first · partial signals are marked",
          metaShort:
            "Lowest model rank first · bearish candidates UW / SELL",
        };

  const directionalCount = data.picks.filter((card) =>
    resultQuery.side === "short" ? ["UW", "SELL"].includes(card.rating) : ["BUY", "OW"].includes(card.rating),
  ).length;

  return (
    <>
      <WorkbenchHeader
        eyebrow={`01 · ${locale === "zh" ? "理解变化" : "UNDERSTAND CHANGES"}`}
        title={locale === "zh" ? "今日组合决策" : "Today’s Portfolio Decision"}
        subtitle={locale === "zh" ? "核对快照与驱动，再进入模拟仓验证。" : "Review the snapshot and drivers, then validate on paper."}
        statuses={[
          { label: locale === "zh" ? "数据时间" : "As of", value: asOf },
          { label: locale === "zh" ? "快照" : "Snapshot", value: queryPending ? (locale === "zh" ? "待更新" : "UPDATING") : snapshotStatus === "unknown" ? (locale === "zh" ? "未确认" : "UNCONFIRMED") : snapshotStatus === "stale" ? (locale === "zh" ? "过期" : "STALE") : (locale === "zh" ? "有效" : "CURRENT"), tone: snapshotStatus !== "current" || queryPending ? "warning" : "positive" },
          { label: locale === "zh" ? "方向" : "Side", value: side === "short" ? (locale === "zh" ? "做空" : "SHORT") : (locale === "zh" ? "做多" : "LONG") },
        ]}
        action={<TmLinkButton href="/paper" variant="primary" size="md">{locale === "zh" ? "02 · 打开组合工作台" : "02 · OPEN PORTFOLIO WORKSPACE"}</TmLinkButton>}
      />
      <section className="border-b border-tm-rule bg-tm-bg px-4" aria-label={locale === "zh" ? "策略说明" : "Policy note"}>
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 py-2">
        <p className="text-sm leading-6 text-tm-fg-2">
          {locale === "zh"
            ? `${data.picks.length} 只候选 · ${directionalCount} 只方向评级。排名不是交易指令，HOLD 表示观望。`
            : `${data.picks.length} candidates · ${directionalCount} directional ratings. Rank is not an order; HOLD means wait.`}
        </p>
        <TmButton variant="ghost" size="sm" aria-expanded={showMethod} aria-controls="picks-method" onClick={() => setShowMethod(v => !v)}>{locale === "zh" ? "统计口径" : "Metric definitions"}</TmButton>
        </div>
        {showMethod ? <p id="picks-method" className="border-t border-tm-rule py-3 text-sm leading-6 text-tm-fg-2">{locale === "zh" ? "五日／一月列统计的是快照截至日之前的次日方向命中率，不是持有五日／一月的收益。缺失值下方显示有效样本数／最低要求；不完整信号的更新时间以对应行提示为准。" : "Trailing windows measure next-day direction hits as of the snapshot, not holding-period returns. Missing rates show evaluated samples / minimum required. Partial signals may be older; check each row's date warning."}</p> : null}
        {factorMode === "long" ? (
          <p className="border border-tm-warn/40 bg-tm-warn/10 px-3 py-2 font-tm-mono text-xs leading-5 text-tm-warn">
            {locale === "zh" ? "战略 60 日策略正在独立前瞻验证，未使用 5 日校准置信度，不应直接与战术榜单的置信度横向比较。" : "The strategic 60d policy is in independent forward validation. It does not use the 5d calibrated confidence and should not be compared as if both figures shared one basis."}
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
        <TmButton
          variant="secondary"
          size="xs"
          onClick={onModeToggle}
          title={copy.modeTip}
          className="rounded-[2px] border-tm-accent/40 bg-tm-accent/10 text-tm-accent hover:bg-tm-accent/20 focus:outline-none focus:ring-1 focus:ring-tm-accent"
          aria-label={copy.modeLabel}
        >
          <span className="opacity-70">{copy.modeLabel}</span>
          <span className="font-semibold">
            {factorMode === "short" ? copy.modeShort : copy.modeLong}
          </span>
        </TmButton>
        <TmSubbarSep />
        <TmButton
          variant="secondary"
          size="xs"
          onClick={onSideToggle}
          title={copy.sideTip}
          className={
            side === "short"
              ? "rounded-[2px] border-tm-neg/40 bg-tm-neg/10 text-tm-neg hover:bg-tm-neg/20 focus:outline-none focus:ring-1 focus:ring-tm-neg"
              : "rounded-[2px] border-tm-pos/40 bg-tm-pos/10 text-tm-pos hover:bg-tm-pos/20 focus:outline-none focus:ring-1 focus:ring-tm-pos"
          }
          aria-label={copy.sideLabel}
        >
          <span className="opacity-70">{copy.sideLabel}</span>
          <span className="font-semibold">
            {side === "short" ? copy.sideShort : copy.sideLong}
          </span>
        </TmButton>
        {snapshotStale ? (
          <>
            <TmSubbarSep />
            <TmStatusPill tone="err">{copy.stale}</TmStatusPill>
          </>
        ) : null}

      </TmSubbar>

      <>
        {requestError ? (
          <TmStatePane
            state="error"
            title={locale === "zh" ? "请求未成功，下方保留上次结果" : "Request failed; showing the previous result"}
            description={requestError}
            action={{ label: t(locale, "common.retry"), onClick: () => { void runSearch(search, factorMode, side); }, loading }}
            className="shrink-0 !min-h-0 !py-3"
          />
        ) : null}
        {!searching && !queryPending && data.changes ? (
          <section className="border-b border-tm-rule bg-tm-bg px-4 py-3" aria-labelledby="changes-heading">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 id="changes-heading" className="font-tm-mono text-xs font-semibold uppercase tracking-[0.08em] text-tm-fg">
                {locale === "zh" ? "相对上一快照的组合变化" : "PORTFOLIO CHANGES VS PRIOR SNAPSHOT"}
              </h2>
              {data.changes.available && data.changes.turnover != null ? <span className="font-tm-mono text-xs text-tm-muted">{locale === "zh" ? "名单换手" : "NAME TURNOVER"} {(data.changes.turnover * 100).toFixed(1)}%</span> : null}
            </div>
            {data.changes.available ? (
              <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
                <ChangeList tone="text-tm-pos" title={locale === "zh" ? "新增" : "ADDED"} empty={locale === "zh" ? "无新增" : "No additions"} items={data.changes.added.map((item) => `${item.ticker} #${item.current_rank ?? "—"}`)} />
                <ChangeList tone="text-tm-neg" title={locale === "zh" ? "移出" : "REMOVED"} empty={locale === "zh" ? "无移出" : "No removals"} items={data.changes.removed.map((item) => `${item.ticker} #${item.prior_rank ?? "—"}`)} />
                <ChangeList tone="text-tm-accent" title={locale === "zh" ? "评级变化" : "TIER CHANGES"} empty={locale === "zh" ? "无评级变化" : "No tier changes"} items={data.changes.tier_changes.map((item) => `${item.ticker} ${item.prior_tier ?? "—"}→${item.current_tier ?? "—"}`)} />
              </div>
            ) : (
              <p className="mt-2 font-tm-mono text-xs leading-5 text-tm-muted">{factorMode === "long" ? (locale === "zh" ? "独立战略政策尚未积累两个同政策快照，因此不伪造跨政策变化。" : "The independent strategic policy does not yet have two same-policy snapshots, so cross-policy changes are not fabricated.") : (locale === "zh" ? "尚无可比的上一份同政策快照。" : "No comparable prior snapshot exists for this policy.")}</p>
            )}
          </section>
        ) : null}
        {/* Keep personal context and policy evidence reachable without
            placing closed panel bodies ahead of the candidate table. */}
        <InvestmentProfile compact />
        <InvestmentNotebook compact />
        <InvestmentEvidence compact sleeve={data.run?.sleeve === "strategic" ? "strategic" : "tactical"} policyId={data.run?.policy_id} />

          {/* ★ Highest-Conviction hero band — top-3 of the current board as
              decision-first cards (ALPHACORE design). Hidden during an active
              search, where the result set is a lookup, not a conviction ranking. */}
          {!searching && !snapshotStale && !queryPending ? <ConvictionBand picks={data.picks} /> : null}

          <TmPane
            title={copy.paneTitle}
            meta={
              queryPending
                ? (locale === "zh"
                  ? `仍显示${resultQuery.mode === "short" ? copy.modeShort : copy.modeLong} · ${resultQuery.side === "long" ? copy.sideLong : copy.sideShort}；新条件未就绪`
                  : `Still showing ${resultQuery.mode === "short" ? copy.modeShort : copy.modeLong} · ${resultQuery.side === "long" ? copy.sideLong : copy.sideShort}; update pending`)
                : searching
                ? copy.paneMeta
                : side === "short"
                  ? copy.metaShort
                  : copy.metaLong
            }
          >
            {refreshing ? (
              <div className="mx-3 mt-2 rounded-[2px] border border-tm-accent/40 bg-tm-accent/10 px-3 py-1.5 font-tm-mono text-xs text-tm-accent">
                {refreshRemainingMin > 0
                  ? t(locale, "picks.freeze_banner").replace(
                      "{min}",
                      String(refreshRemainingMin),
                    )
                  : t(locale, "picks.verify_banner")}
              </div>
            ) : refreshResult?.status === "published" ? (
              <div className="mx-3 mt-2 rounded-[2px] border border-tm-pos/40 bg-tm-pos/10 px-3 py-1.5 font-tm-mono text-xs text-tm-pos">
                {t(locale, "picks.published_banner").replace(
                  "{run}",
                  refreshResult.runId == null ? "—" : `#${refreshResult.runId}`,
                )}
              </div>
            ) : refreshResult?.status === "no_op_same_market_date" ? (
              <div className="mx-3 mt-2 rounded-[2px] border border-tm-warn/40 bg-tm-warn/10 px-3 py-1.5 font-tm-mono text-xs text-tm-warn">
                {t(locale, "picks.noop_banner").replace(
                  "{date}",
                  refreshResult.marketDate ?? "—",
                )}
              </div>
            ) : refreshResult ? (
              <div className="mx-3 mt-2 rounded-[2px] border border-tm-neg/40 bg-tm-neg/10 px-3 py-1.5 font-tm-mono text-xs text-tm-neg">
                {t(
                  locale,
                  refreshResult.status === "health_gate_failed"
                    ? "picks.health_failed_banner"
                    : "picks.publish_failed_banner",
                )}
              </div>
            ) : snapshotStale ? (
              <div className="mx-3 mt-2 rounded-[2px] border border-tm-neg/40 bg-tm-neg/10 px-3 py-2 font-tm-mono text-xs leading-5 text-tm-neg">
                {t(locale, "picks.stale_freeze_banner")}
              </div>
            ) : null}
            <div className="flex flex-wrap items-center justify-between gap-3 px-3 py-3">
            <div className="flex flex-wrap items-center gap-3">
              <TmInput
                aria-label={copy.placeholder}
                value={search}
                onChange={setSearch}
                placeholder={copy.placeholder}
                maxLength={12}
                fieldSize="sm"
                className="w-64 max-w-full"
                inputClassName="rounded-[2px]"
              />
              {searching ? <TmButton variant="ghost" size="sm" onClick={() => setSearch("")}>{locale === "zh" ? "清除搜索" : "Clear search"}</TmButton> : null}
              {queryPending ? (
                <span role="status" className="font-tm-mono text-xs text-tm-muted">
                  {requestError ? (locale === "zh" ? "更新未完成，请重试" : "Update incomplete; retry") : copy.loading}
                </span>
              ) : null}
            </div>
            <RefreshButton />
            </div>
            {count === 0 && queryPending ? (
              <TmStatePane state={requestError ? "empty" : "loading"} title={requestError ? (locale === "zh" ? "尚未取得新结果，请重试" : "No new result yet; please retry") : copy.loading} />
            ) : count === 0 && searching ? (
              <div className="px-3 py-6 font-tm-mono text-xs text-tm-muted">
                {copy.empty}
              </div>
            ) : count === 0 ? (
              <TmStatePane state="empty" title={locale === "zh" ? "当前快照暂无可用候选" : "No candidates in this snapshot"} />
            ) : (
              <PicksTable
                picks={data.picks}
                pending={queryPending}
                isWatched={isWatched}
                simPositions={simPositions}
                cash={paperCash}
                onOrderPlaced={loadSimPositions}
                ranked={data.ranked && !searching}
                ordersDisabled={snapshotStale || !data.tradable || searching || queryPending || !!requestError}
              />
            )}
          </TmPane>
          <TmDisclosureButton expanded={showResearch} aria-controls="picks-research" onClick={() => setShowResearch(v => !v)} label={locale === "zh" ? "辅助研究指标" : "Research diagnostics"} meta={locale === "zh" ? "非当前策略跟随收益" : "Not this policy's following return"} />
          {showResearch ? <div id="picks-research"><BasketEdgeStrip /></div> : null}
        </>
    </>
  );
}

function ChangeList({ title, items, empty, tone }: { readonly title: string; readonly items: readonly string[]; readonly empty: string; readonly tone: string }) {
  return <div className="rounded-[2px] border border-tm-rule bg-tm-bg-2 px-3 py-2"><div className={`font-tm-mono text-xs font-semibold uppercase ${tone}`}>{title}</div><p className="mt-1 truncate font-tm-mono text-xs text-tm-fg-2" title={items.join(" · ")}>{items.length ? items.slice(0, 5).join(" · ") : empty}</p></div>;
}
