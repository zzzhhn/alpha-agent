"use client";

/**
 * Factors / Zoo page — workstation port v2 (Stage 3 · 5/9, density rework).
 *
 * v1 was an OVERVIEW + table page. v2 turns the page into an analyst
 * dashboard with 6 client-side aggregations layered on top of the same
 * server data:
 *
 *   1. ZOO.OVERVIEW           — 8 KPIs (was 4): adds AVG_SHARPE, MEDIAN_IC,
 *                               STALE_30D, DIR_LS%
 *   2. PERF.LEADERBOARD       — TmCols2: TOP 5 / BOTTOM 5 by Sharpe
 *   3. OPS.USAGE | DIR.MIX    — TmCols2: terminal-style horizontal bars
 *                               (operator frequency + direction split)
 *   4. PERF.DIST              — 3 fixed-bin histograms (Sharpe / Return / IC)
 *                               via recharts in tm-* token palette
 *   5. STALE.FACTORS (cond.)  — ≥ 30d untouched + last_sharpe ≥ 0.5
 *                               ("forgotten champions" surfacing)
 *   6. ZOO.CATALOG            — gains chip filter (direction × status) +
 *                               sortable column headers + inline DIR badge
 *
 * All aggregations are pure-client from the merged entries[] array. Zero
 * new backend endpoints. Server-merge logic, sessionStorage prefill keys,
 * removeFromZoo + refresh flow all preserved.
 */

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  AreaChart,
  Area,
} from "recharts";
import { useLocale } from "@/components/layout/LocaleProvider";
import { extractOps } from "@/lib/factor-spec";
import { t } from "@/lib/i18n";
import { listZoo, removeFromZoo, type ZooEntry } from "@/lib/factor-zoo";
import {
  runZooCorrelation,
  listServerFactors,
  getDecayAlerts,
  type ServerFactor,
  type DecayAlert,
} from "@/lib/api";
import type { ZooCorrelationResponse } from "@/lib/types";
import { TmScreen, TmPane, TmCols2 } from "@/components/tm/TmPane";
import {
  TmSubbar,
  TmSubbarKV,
  TmSubbarSep,
  TmSubbarSpacer,
  TmStatusPill,
  TmChip,
} from "@/components/tm/TmSubbar";
import { TmKpi, TmKpiGrid } from "@/components/tm/TmKpi";
import { TmButton } from "@/components/tm/TmButton";

/* ── Constants ────────────────────────────────────────────────────── */

const STALE_DAY_THRESHOLD = 30;
const STALE_SHARPE_THRESHOLD = 0.5;
const TOP_K = 5;
const OPS_TOP_N = 10;
// Hide TIMELINE.ACTIVITY when fewer than this many entries exist —
// a 3-bar sparkline is meaningless and visually empty.
const TIMELINE_MIN_ENTRIES = 5;

// Fixed histogram bins — picked to span typical SP500 long_short Sharpe
// (-1 → 3) and Compustat-era IC (-3% → 8%). Stable bin edges avoid the
// "single-bin spike" artifact that auto-ranged bins hit on small N.
const SHARPE_BINS: readonly { lo: number; hi: number; label: string }[] = [
  { lo: -Infinity, hi: -0.5, label: "<−0.5" },
  { lo: -0.5, hi: 0, label: "−0.5..0" },
  { lo: 0, hi: 0.5, label: "0..0.5" },
  { lo: 0.5, hi: 1.0, label: "0.5..1" },
  { lo: 1.0, hi: 1.5, label: "1..1.5" },
  { lo: 1.5, hi: 2.0, label: "1.5..2" },
  { lo: 2.0, hi: 2.5, label: "2..2.5" },
  { lo: 2.5, hi: Infinity, label: "≥2.5" },
];
const RETURN_BINS: readonly { lo: number; hi: number; label: string }[] = [
  { lo: -Infinity, hi: -0.25, label: "<−25%" },
  { lo: -0.25, hi: 0, label: "−25..0" },
  { lo: 0, hi: 0.25, label: "0..25%" },
  { lo: 0.25, hi: 0.5, label: "25..50%" },
  { lo: 0.5, hi: 1.0, label: "50..100%" },
  { lo: 1.0, hi: Infinity, label: "≥100%" },
];
const IC_BINS: readonly { lo: number; hi: number; label: string }[] = [
  { lo: -Infinity, hi: -0.025, label: "<−2.5%" },
  { lo: -0.025, hi: 0, label: "−2.5..0" },
  { lo: 0, hi: 0.025, label: "0..2.5%" },
  { lo: 0.025, hi: 0.05, label: "2.5..5%" },
  { lo: 0.05, hi: 0.075, label: "5..7.5%" },
  { lo: 0.075, hi: Infinity, label: "≥7.5%" },
];

/* ── Helpers ──────────────────────────────────────────────────────── */

function median(xs: readonly number[]): number {
  if (xs.length === 0) return NaN;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 === 0 ? (s[m - 1] + s[m]) / 2 : s[m];
}

function ageDays(savedAt: string): number {
  const ms = Date.now() - new Date(savedAt).getTime();
  return ms / (1000 * 60 * 60 * 24);
}

function bucketize<T extends { lo: number; hi: number }>(
  values: readonly number[],
  bins: readonly T[],
): readonly (T & { count: number })[] {
  return bins.map((b) => ({
    ...b,
    count: values.filter((v) => v > b.lo && v <= b.hi).length,
  }));
}

// Bucket entries into ISO-week buckets keyed by Monday's date string.
// Fills in zero-count gaps between min and max week so the area chart
// reads as a continuous timeline rather than a staircase of present-only
// weeks.
interface ActivityWeek {
  readonly week: string; // "YYYY-MM-DD" (Monday of that week)
  readonly count: number;
}
function mondayOf(d: Date): Date {
  const day = d.getDay();
  // 0 = Sunday → roll back 6; 1..6 → roll back day-1
  const offset = day === 0 ? 6 : day - 1;
  const monday = new Date(d);
  monday.setDate(d.getDate() - offset);
  monday.setHours(0, 0, 0, 0);
  return monday;
}
function bucketByWeek(entries: readonly ZooEntry[]): readonly ActivityWeek[] {
  if (entries.length === 0) return [];
  const counts = new Map<string, number>();
  let minMs = Infinity;
  let maxMs = -Infinity;
  for (const e of entries) {
    const d = new Date(e.savedAt);
    if (Number.isNaN(d.getTime())) continue;
    const monday = mondayOf(d);
    const ms = monday.getTime();
    if (ms < minMs) minMs = ms;
    if (ms > maxMs) maxMs = ms;
    const key = monday.toISOString().slice(0, 10);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  if (!Number.isFinite(minMs) || !Number.isFinite(maxMs)) return [];
  // Walk weeks from min to max, filling 0s. Cap at 104 weeks (2y) to
  // avoid an absurdly long timeline if a v1 entry has a savedAt from
  // years ago — visually unhelpful and slows the chart.
  const out: ActivityWeek[] = [];
  const WEEK_MS = 7 * 24 * 60 * 60 * 1000;
  const maxWeeks = 104;
  const start = Math.max(minMs, maxMs - (maxWeeks - 1) * WEEK_MS);
  for (let ms = start; ms <= maxMs; ms += WEEK_MS) {
    const key = new Date(ms).toISOString().slice(0, 10);
    out.push({ week: key, count: counts.get(key) ?? 0 });
  }
  return out;
}

function mergeFactors(
  server: readonly ServerFactor[],
  local: readonly ZooEntry[],
): readonly ZooEntry[] {
  const serverExprs = new Set(server.map((f) => f.expression));
  const fromServer: ZooEntry[] = server.map((f) => ({
    id: f.id,
    name: f.name,
    expression: f.expression,
    hypothesis: f.hypothesis ?? "",
    intuition: f.intuition ?? undefined,
    direction:
      (f.last_direction as ZooEntry["direction"]) ?? "long_short",
    savedAt: f.updated_at ?? f.created_at ?? new Date().toISOString(),
    headlineMetrics: {
      testSharpe: f.last_test_sharpe ?? undefined,
      testIc: f.last_test_ic ?? undefined,
    },
    neutralize:
      (f.last_neutralize as "none" | "sector" | undefined) ?? undefined,
    benchmarkTicker:
      (f.last_benchmark as "SPY" | "RSP" | undefined) ?? undefined,
  }));
  return [
    ...fromServer,
    ...local.filter((e) => !serverExprs.has(e.expression)),
  ];
}

interface Aggregates {
  readonly avgSharpe: number | null;
  readonly medianIC: number | null;
  readonly staleCount: number;
  readonly dirSplit: ReadonlyMap<string, number>;
  readonly opsCount: ReadonlyArray<readonly [string, number]>;
  readonly top5: readonly ZooEntry[];
  readonly bottom5: readonly ZooEntry[];
  readonly sharpeDist: readonly { label: string; count: number }[];
  readonly returnDist: readonly { label: string; count: number }[];
  readonly icDist: readonly { label: string; count: number }[];
  readonly staleEntries: readonly ZooEntry[];
  readonly activityWeeks: readonly ActivityWeek[];
  readonly activeWeekCount: number;   // weeks with ≥1 activity
  readonly peakWeek: { week: string; count: number } | null;
}

function computeAggregates(entries: readonly ZooEntry[]): Aggregates {
  const sharpes = entries
    .map((e) => e.headlineMetrics?.testSharpe)
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  const ics = entries
    .map((e) => e.headlineMetrics?.testIc)
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  const returns = entries
    .map((e) => e.headlineMetrics?.totalReturn)
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v));

  const dirSplit = new Map<string, number>();
  for (const e of entries) {
    const d = e.direction ?? "long_short";
    dirSplit.set(d, (dirSplit.get(d) ?? 0) + 1);
  }

  const opsMap = new Map<string, number>();
  for (const e of entries) {
    for (const op of extractOps(e.expression)) {
      opsMap.set(op, (opsMap.get(op) ?? 0) + 1);
    }
  }
  const opsCount = Array.from(opsMap.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, OPS_TOP_N);

  // Sort entries by sharpe (desc) for top/bottom; use -Infinity for missing
  // so they sink to the bottom of the desc list (and "bottom" picks them up).
  const sortedBySharpe = [...entries].sort(
    (a, b) =>
      (b.headlineMetrics?.testSharpe ?? -Infinity) -
      (a.headlineMetrics?.testSharpe ?? -Infinity),
  );
  const ranked = sortedBySharpe.filter(
    (e) => typeof e.headlineMetrics?.testSharpe === "number",
  );
  const top5 = ranked.slice(0, TOP_K);
  const bottom5 = ranked.slice(-TOP_K).reverse();

  const staleEntries = entries.filter((e) => {
    const sharpe = e.headlineMetrics?.testSharpe;
    return (
      ageDays(e.savedAt) >= STALE_DAY_THRESHOLD &&
      typeof sharpe === "number" &&
      sharpe >= STALE_SHARPE_THRESHOLD
    );
  });

  const activityWeeks = bucketByWeek(entries);
  const activeWeekCount = activityWeeks.filter((w) => w.count > 0).length;
  const peakWeek =
    activityWeeks.length === 0
      ? null
      : activityWeeks.reduce(
          (best, w) => (w.count > best.count ? w : best),
          activityWeeks[0],
        );

  return {
    avgSharpe: sharpes.length ? sharpes.reduce((a, b) => a + b, 0) / sharpes.length : null,
    medianIC: ics.length ? median(ics) : null,
    staleCount: entries.filter((e) => ageDays(e.savedAt) >= STALE_DAY_THRESHOLD).length,
    dirSplit,
    opsCount,
    top5,
    bottom5,
    sharpeDist: bucketize(sharpes, SHARPE_BINS).map((b) => ({ label: b.label, count: b.count })),
    returnDist: bucketize(returns, RETURN_BINS).map((b) => ({ label: b.label, count: b.count })),
    icDist: bucketize(ics, IC_BINS).map((b) => ({ label: b.label, count: b.count })),
    staleEntries,
    activityWeeks,
    activeWeekCount,
    peakWeek: peakWeek && peakWeek.count > 0 ? peakWeek : null,
  };
}

/* ── Page ─────────────────────────────────────────────────────────── */

type SortCol = "sharpe" | "return" | "ic" | "savedAt" | "name";
type SortDir = "asc" | "desc";
type DirFilter = "all" | "long_short" | "long_only" | "short_only";
type StatusFilter = "all" | "decaying" | "stale" | "champion";

export default function FactorsPage() {
  const { locale } = useLocale();
  const router = useRouter();
  const [entries, setEntries] = useState<readonly ZooEntry[]>([]);
  const [serverCount, setServerCount] = useState(0);
  const [localCount, setLocalCount] = useState(0);
  const [decay, setDecay] = useState<readonly DecayAlert[]>([]);

  async function refresh() {
    try {
      const [r1, r2] = await Promise.all([
        listServerFactors(200),
        getDecayAlerts({ min_runs: 3, decay_threshold: 0.5 }),
      ]);
      const local = listZoo();
      setLocalCount(local.length);
      if (r1.data) {
        setServerCount(r1.data.length);
        setEntries(mergeFactors(r1.data, local));
      } else {
        setServerCount(0);
        setEntries(local);
      }
      if (r2.data) setDecay(r2.data);
    } catch {
      const local = listZoo();
      setEntries(local);
      setLocalCount(local.length);
      setServerCount(0);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const aggregates = useMemo(() => computeAggregates(entries), [entries]);
  const decayIds = useMemo(
    () => new Set(decay.map((d) => d.factor_id)),
    [decay],
  );
  const staleIds = useMemo(
    () => new Set(aggregates.staleEntries.map((e) => e.id)),
    [aggregates.staleEntries],
  );

  function loadIntoBacktest(e: ZooEntry) {
    if (typeof window === "undefined") return;
    try {
      window.sessionStorage.setItem(
        "alphacore.backtest.prefill.v1",
        JSON.stringify({
          name: e.name,
          expression: e.expression,
          operators_used: [...extractOps(e.expression)],
          lookback: 12,
          hypothesis: e.hypothesis,
          direction: e.direction,
          neutralize: e.neutralize,
          benchmarkTicker: e.benchmarkTicker,
          mode: e.mode,
          topPct: e.topPct,
          bottomPct: e.bottomPct,
          transactionCostBps: e.transactionCostBps,
        }),
      );
    } catch {
      /* ignore */
    }
    router.push("/backtest");
  }

  function loadIntoReport(e: ZooEntry) {
    if (typeof window === "undefined") return;
    try {
      window.sessionStorage.setItem(
        "alphacore.report.prefill.v1",
        JSON.stringify(e),
      );
    } catch {
      /* ignore */
    }
    router.push("/report");
  }

  function loadIntoScreener(e: ZooEntry) {
    if (typeof window === "undefined") return;
    try {
      window.sessionStorage.setItem(
        "alphacore.screener.prefill.v1",
        JSON.stringify({ ids: [e.id] }),
      );
    } catch {
      /* ignore */
    }
    router.push("/screener");
  }

  function deleteEntry(id: string) {
    removeFromZoo(id);
    void refresh();
  }

  /* ── correlation panel ────────────────────────────────────────── */
  const [corrLoading, setCorrLoading] = useState(false);
  const [corrError, setCorrError] = useState<string | null>(null);
  const [corrResult, setCorrResult] =
    useState<ZooCorrelationResponse | null>(null);

  async function checkCorrelation() {
    if (entries.length < 2) return;
    setCorrLoading(true);
    setCorrError(null);
    setCorrResult(null);
    const res = await runZooCorrelation({
      factors: entries.map((e) => ({
        spec: {
          name: e.name,
          hypothesis: e.hypothesis ?? "",
          expression: e.expression,
          operators_used: [...extractOps(e.expression)],
          lookback: 12,
          universe: "SP500",
          justification: e.intuition ?? e.hypothesis ?? "zoo entry",
        },
        label: e.name,
      })),
    });
    if (res.error || !res.data) {
      setCorrError(res.error ?? "unknown error");
    } else {
      setCorrResult(res.data);
    }
    setCorrLoading(false);
  }

  const dirLsPct =
    entries.length > 0
      ? Math.round(((aggregates.dirSplit.get("long_short") ?? 0) / entries.length) * 100)
      : 0;

  return (
    <TmScreen>
      <TmSubbar>
        <span className="text-tm-muted">FACTORS · ZOO</span>
        <TmSubbarSep />
        <TmSubbarKV label="ENTRIES" value={entries.length.toString()} />
        <TmSubbarSep />
        <TmSubbarKV label="SERVER" value={serverCount.toString()} />
        <TmSubbarSep />
        <TmSubbarKV label="LOCAL" value={localCount.toString()} />
        <TmSubbarSpacer />
        {decay.length > 0 && (
          <TmStatusPill tone="warn">{`${decay.length} DECAYING`}</TmStatusPill>
        )}
        {aggregates.staleEntries.length > 0 && (
          <TmStatusPill tone="warn">{`${aggregates.staleEntries.length} STALE`}</TmStatusPill>
        )}
        {corrLoading && <TmStatusPill tone="warn">RUNNING…</TmStatusPill>}
        <TmButton
          variant="ghost"
          onClick={checkCorrelation}
          disabled={corrLoading || entries.length < 2}
          className="-my-1 px-2"
          title={
            entries.length < 2
              ? t(locale, "zoo.corr.disabledHint")
              : undefined
          }
        >
          {corrLoading
            ? t(locale, "zoo.corr.running")
            : t(locale, "zoo.corr.run")}
        </TmButton>
      </TmSubbar>

      {/* 1. OVERVIEW — 8 KPIs */}
      <TmPane
        title="ZOO.OVERVIEW"
        meta={`${entries.length} TOTAL · ${serverCount} SERVER · ${localCount} LOCAL`}
      >
        <TmKpiGrid>
          <TmKpi label="ENTRIES" value={entries.length.toString()} sub="merged" />
          <TmKpi
            label="DECAYING"
            value={decay.length.toString()}
            tone={decay.length > 0 ? "warn" : "default"}
            sub="IC drop ≥ 50%"
          />
          <TmKpi label="FROM_SERVER" value={serverCount.toString()} sub="auto-saved" />
          <TmKpi label="FROM_LOCAL" value={localCount.toString()} sub="offline-only" />
          <TmKpi
            label="AVG_SHARPE"
            value={aggregates.avgSharpe != null ? aggregates.avgSharpe.toFixed(2) : "—"}
            tone={
              aggregates.avgSharpe == null
                ? "default"
                : aggregates.avgSharpe > 0
                  ? "pos"
                  : "neg"
            }
            sub="test"
          />
          <TmKpi
            label="MEDIAN_IC"
            value={aggregates.medianIC != null ? `${(aggregates.medianIC * 100).toFixed(2)}%` : "—"}
            tone={
              aggregates.medianIC == null
                ? "default"
                : aggregates.medianIC > 0
                  ? "pos"
                  : "neg"
            }
            sub="spearman"
          />
          <TmKpi
            label="STALE_30D"
            value={aggregates.staleCount.toString()}
            tone={aggregates.staleCount > 0 ? "warn" : "default"}
            sub="≥30d untouched"
          />
          <TmKpi
            label="DIR_LS"
            value={`${dirLsPct}%`}
            sub="long_short share"
          />
        </TmKpiGrid>
      </TmPane>

      {/* 2. PERF.LEADERBOARD */}
      {entries.length > 0 && (aggregates.top5.length > 0 || aggregates.bottom5.length > 0) && (
        <TmCols2>
          <LeaderSide
            title="TOP 5 SHARPE"
            tone="pos"
            entries={aggregates.top5}
            onPick={loadIntoBacktest}
          />
          <LeaderSide
            title="BOTTOM 5 SHARPE"
            tone="neg"
            entries={aggregates.bottom5}
            onPick={loadIntoBacktest}
          />
        </TmCols2>
      )}

      {/* 3. OPS.USAGE | DIR.MIX */}
      {entries.length > 0 && (
        <TmCols2>
          <OperatorUsagePane opsCount={aggregates.opsCount} totalEntries={entries.length} />
          <DirectionMixPane dirSplit={aggregates.dirSplit} totalEntries={entries.length} />
        </TmCols2>
      )}

      {/* 4. PERF.DIST */}
      {entries.length > 0 && (
        <TmPane
          title="PERF.DIST"
          meta={`${entries.length} ENTRIES · 3 METRICS`}
        >
          <div className="grid grid-cols-1 gap-px bg-tm-rule lg:grid-cols-3">
            <DistChart title="SHARPE" data={aggregates.sharpeDist} accent="var(--tm-accent)" />
            <DistChart title="TOTAL RETURN" data={aggregates.returnDist} accent="var(--tm-pos)" />
            <DistChart title="IC" data={aggregates.icDist} accent="var(--tm-info)" />
          </div>
        </TmPane>
      )}

      {/* 7. TIMELINE.ACTIVITY — only when ≥5 entries (sparkline of fewer
          weeks is meaningless and looks empty). savedAt reflects most-
          recent touch (created_at fallback) so this is "factor activity
          heartbeat", not just minting rate. */}
      {entries.length >= TIMELINE_MIN_ENTRIES &&
        aggregates.activityWeeks.length > 0 && (
          <TimelineActivityPane
            weeks={aggregates.activityWeeks}
            activeWeekCount={aggregates.activeWeekCount}
            peakWeek={aggregates.peakWeek}
            totalEntries={entries.length}
          />
        )}

      {/* DECAY.ALERTS (existing) */}
      {decay.length > 0 && (
        <TmPane
          title="DECAY.ALERTS"
          meta={`${decay.length} FACTOR${decay.length === 1 ? "" : "S"}`}
        >
          <ul className="flex flex-col">
            {decay.map((d) => (
              <li
                key={d.factor_id}
                className="flex flex-wrap items-center gap-3 border-b border-tm-rule px-3 py-1.5 font-tm-mono text-[11px] last:border-b-0"
              >
                <span className="text-tm-warn">▸</span>
                <span className="text-tm-fg">{d.name}</span>
                <span className="text-tm-muted">IC</span>
                <span className="tabular-nums text-tm-fg-2">
                  {(d.baseline_ic * 100).toFixed(2)}%
                </span>
                <span className="text-tm-muted">→</span>
                <span className="tabular-nums text-tm-neg">
                  {(d.latest_ic * 100).toFixed(2)}%
                </span>
              </li>
            ))}
          </ul>
        </TmPane>
      )}

      {/* 5. STALE.FACTORS — forgotten champions */}
      {aggregates.staleEntries.length > 0 && (
        <TmPane
          title="STALE.FACTORS"
          meta={`${aggregates.staleEntries.length} FORGOTTEN · ≥${STALE_DAY_THRESHOLD}d & SHARPE ≥ ${STALE_SHARPE_THRESHOLD}`}
        >
          <ul className="flex flex-col">
            {aggregates.staleEntries.map((e) => (
              <li
                key={e.id}
                className="flex flex-wrap items-center gap-3 border-b border-tm-rule px-3 py-1.5 font-tm-mono text-[11px] last:border-b-0"
              >
                <span className="text-tm-info">⏱</span>
                <span className="flex-1 truncate text-tm-fg">{e.name}</span>
                <span className="text-tm-muted">AGE</span>
                <span className="tabular-nums text-tm-fg-2">
                  {Math.round(ageDays(e.savedAt))}d
                </span>
                <span className="text-tm-muted">SHARPE</span>
                <span className="tabular-nums text-tm-pos">
                  {(e.headlineMetrics?.testSharpe ?? 0).toFixed(2)}
                </span>
                <TmButton
                  variant="ghost"
                  onClick={() => loadIntoBacktest(e)}
                  className="h-6 px-1.5 text-[10px]"
                >
                  re-run
                </TmButton>
              </li>
            ))}
          </ul>
        </TmPane>
      )}

      {/* 6. CATALOG (with chip filter + sort) */}
      <ZooCatalogPane
        entries={entries}
        decayIds={decayIds}
        staleIds={staleIds}
        locale={locale}
        onLoadBacktest={loadIntoBacktest}
        onLoadReport={loadIntoReport}
        onLoadScreener={loadIntoScreener}
        onDelete={deleteEntry}
      />

      {(corrError || corrResult) && (
        <TmPane
          title="CORRELATION"
          meta={
            corrResult
              ? `${corrResult.names.length} FACTORS · ${corrResult.n_sessions} SESSIONS`
              : undefined
          }
        >
          {corrError && (
            <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-neg">
              {corrError}
            </p>
          )}
          {corrResult && <CorrelationPanel data={corrResult} />}
        </TmPane>
      )}
    </TmScreen>
  );
}

/* ── Leaderboard side ─────────────────────────────────────────────── */

function LeaderSide({
  title,
  tone,
  entries,
  onPick,
}: {
  readonly title: string;
  readonly tone: "pos" | "neg";
  readonly entries: readonly ZooEntry[];
  readonly onPick: (e: ZooEntry) => void;
}) {
  const accentClass = tone === "pos" ? "text-tm-pos" : "text-tm-neg";
  return (
    <TmPane title={title} meta={`${entries.length} SHOWN`}>
      {entries.length === 0 ? (
        <p className="px-3 py-3 font-tm-mono text-[11px] text-tm-muted">
          no ranked entries.
        </p>
      ) : (
        <div
          className="grid gap-px bg-tm-rule"
          style={{ gridTemplateColumns: "32px 1fr 64px 64px 60px" }}
        >
          <HCell>#</HCell>
          <HCell>NAME</HCell>
          <HCell align="right">SHARPE</HCell>
          <HCell align="right">IC</HCell>
          <HCell align="right">ACT</HCell>
          {entries.map((e, i) => {
            const sh = e.headlineMetrics?.testSharpe ?? 0;
            const ic = e.headlineMetrics?.testIc ?? 0;
            return (
              <LeaderRow
                key={e.id}
                rank={i + 1}
                name={e.name}
                expr={e.expression}
                sharpe={sh}
                ic={ic}
                accentClass={accentClass}
                onPick={() => onPick(e)}
              />
            );
          })}
        </div>
      )}
    </TmPane>
  );
}

function LeaderRow({
  rank,
  name,
  expr,
  sharpe,
  ic,
  accentClass,
  onPick,
}: {
  readonly rank: number;
  readonly name: string;
  readonly expr: string;
  readonly sharpe: number;
  readonly ic: number;
  readonly accentClass: string;
  readonly onPick: () => void;
}) {
  return (
    <>
      <DCell>{String(rank).padStart(2, "0")}</DCell>
      <DCell title={expr}>
        <span className={`block truncate font-semibold ${accentClass}`}>
          {name}
        </span>
      </DCell>
      <DCell align="right">
        <span className={`tabular-nums ${accentClass}`}>{sharpe.toFixed(2)}</span>
      </DCell>
      <DCell align="right">
        <span className="tabular-nums text-tm-fg-2">{ic.toFixed(3)}</span>
      </DCell>
      <DCell align="right">
        <button
          type="button"
          onClick={onPick}
          className="font-tm-mono text-[10px] text-tm-muted hover:text-tm-accent"
        >
          ▶
        </button>
      </DCell>
    </>
  );
}

/* ── Operator usage / direction mix ───────────────────────────────── */

function OperatorUsagePane({
  opsCount,
  totalEntries,
}: {
  readonly opsCount: ReadonlyArray<readonly [string, number]>;
  readonly totalEntries: number;
}) {
  const max = opsCount.reduce((m, [, c]) => Math.max(m, c), 0) || 1;
  return (
    <TmPane title="OPS.USAGE" meta={`TOP ${opsCount.length} OF UNIQUE OPS`}>
      {opsCount.length === 0 ? (
        <p className="px-3 py-3 font-tm-mono text-[11px] text-tm-muted">
          no operators detected.
        </p>
      ) : (
        <ul className="flex flex-col">
          {opsCount.map(([op, count]) => {
            const widthPct = (count / max) * 100;
            const sharePct = totalEntries > 0 ? (count / totalEntries) * 100 : 0;
            return (
              <li
                key={op}
                className="grid items-center gap-3 border-b border-tm-rule px-3 py-1 last:border-b-0"
                style={{ gridTemplateColumns: "minmax(120px, 140px) 1fr 60px 50px" }}
              >
                <span className="truncate font-tm-mono text-[11px] text-tm-accent">
                  {op}
                </span>
                <div className="relative h-3 w-full bg-tm-bg-2">
                  <div
                    className="h-full bg-tm-accent-soft"
                    style={{ width: `${widthPct}%` }}
                  />
                </div>
                <span className="text-right font-tm-mono text-[10.5px] tabular-nums text-tm-fg-2">
                  {count}
                </span>
                <span className="text-right font-tm-mono text-[10px] tabular-nums text-tm-muted">
                  {sharePct.toFixed(0)}%
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </TmPane>
  );
}

function DirectionMixPane({
  dirSplit,
  totalEntries,
}: {
  readonly dirSplit: ReadonlyMap<string, number>;
  readonly totalEntries: number;
}) {
  // Static class strings (Tailwind only ships classes that appear
  // verbatim in source — `bg-${tone}` interpolation gets tree-shaken).
  const dirs: {
    readonly code: string;
    readonly label: string;
    readonly textClass: string;
    readonly barClass: string;
  }[] = [
    { code: "long_short", label: "LONG_SHORT", textClass: "text-tm-accent", barClass: "bg-tm-accent" },
    { code: "long_only", label: "LONG_ONLY", textClass: "text-tm-pos", barClass: "bg-tm-pos" },
    { code: "short_only", label: "SHORT_ONLY", textClass: "text-tm-neg", barClass: "bg-tm-neg" },
  ];
  return (
    <TmPane title="DIR.MIX" meta={`${totalEntries} ENTRIES`}>
      <ul className="flex flex-col">
        {dirs.map((d) => {
          const count = dirSplit.get(d.code) ?? 0;
          const pct = totalEntries > 0 ? (count / totalEntries) * 100 : 0;
          return (
            <li
              key={d.code}
              className="grid items-center gap-3 border-b border-tm-rule px-3 py-1.5 last:border-b-0"
              style={{ gridTemplateColumns: "minmax(120px, 140px) 1fr 60px 60px" }}
            >
              <span className={`font-tm-mono text-[11px] ${d.textClass}`}>
                {d.label}
              </span>
              <div className="relative h-3 w-full bg-tm-bg-2">
                <div
                  className={`h-full opacity-60 ${d.barClass}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="text-right font-tm-mono text-[10.5px] tabular-nums text-tm-fg-2">
                {count}
              </span>
              <span className="text-right font-tm-mono text-[10.5px] tabular-nums text-tm-muted">
                {pct.toFixed(0)}%
              </span>
            </li>
          );
        })}
      </ul>
    </TmPane>
  );
}

/* ── Distribution chart ───────────────────────────────────────────── */

function DistChart({
  title,
  data,
  accent,
}: {
  readonly title: string;
  readonly data: readonly { label: string; count: number }[];
  readonly accent: string;
}) {
  return (
    <div className="flex flex-col bg-tm-bg">
      <div className="border-b border-tm-rule bg-tm-bg-2 px-3 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
        {title}
      </div>
      <div className="h-[180px] w-full px-1 pb-1 pt-2">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data as { label: string; count: number }[]} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="var(--tm-rule)" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 9, fill: "var(--tm-muted)" }}
              stroke="var(--tm-rule)"
              interval={0}
            />
            <YAxis
              tick={{ fontSize: 9, fill: "var(--tm-muted)" }}
              stroke="var(--tm-rule)"
              allowDecimals={false}
            />
            <Tooltip
              contentStyle={{
                background: "var(--tm-bg-2)",
                border: "1px solid var(--tm-rule)",
                fontSize: 11,
                fontFamily: "var(--font-jetbrains-mono)",
                color: "var(--tm-fg)",
              }}
            />
            <Bar dataKey="count" fill={accent}>
              {data.map((_, i) => (
                <Cell key={i} fill={accent} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/* ── Timeline activity (Stage 3 · 5/9 v2 add 7) ───────────────────── */

function TimelineActivityPane({
  weeks,
  activeWeekCount,
  peakWeek,
  totalEntries,
}: {
  readonly weeks: readonly ActivityWeek[];
  readonly activeWeekCount: number;
  readonly peakWeek: { week: string; count: number } | null;
  readonly totalEntries: number;
}) {
  // Density caption: avg entries per ACTIVE week (not per total — would
  // suppress the signal once you have a few quiet stretches).
  const avgPerActiveWeek =
    activeWeekCount > 0 ? totalEntries / activeWeekCount : 0;
  return (
    <TmPane
      title="TIMELINE.ACTIVITY"
      meta={`${weeks.length} WEEKS · ${activeWeekCount} ACTIVE`}
    >
      <TmKpiGrid>
        <TmKpi
          label="WINDOW"
          value={`${weeks.length}w`}
          sub={`${weeks[0].week} → ${weeks[weeks.length - 1].week}`}
        />
        <TmKpi
          label="ACTIVE"
          value={activeWeekCount.toString()}
          sub={`${((activeWeekCount / weeks.length) * 100).toFixed(0)}% of window`}
        />
        <TmKpi
          label="PEAK"
          value={peakWeek ? peakWeek.count.toString() : "—"}
          tone={peakWeek ? "pos" : "default"}
          sub={peakWeek ? peakWeek.week : "no activity"}
        />
        <TmKpi
          label="AVG / ACTIVE"
          value={avgPerActiveWeek.toFixed(1)}
          sub="entries per active week"
        />
      </TmKpiGrid>

      <div className="h-[160px] w-full px-1 pb-1 pt-2">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={weeks as ActivityWeek[]}
            margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
          >
            <defs>
              <linearGradient id="tm-activity-grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--tm-accent)" stopOpacity={0.6} />
                <stop offset="100%" stopColor="var(--tm-accent)" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="2 4"
              stroke="var(--tm-rule)"
              vertical={false}
            />
            <XAxis
              dataKey="week"
              tick={{ fontSize: 9, fill: "var(--tm-muted)" }}
              stroke="var(--tm-rule)"
              interval="preserveStartEnd"
              minTickGap={40}
            />
            <YAxis
              tick={{ fontSize: 9, fill: "var(--tm-muted)" }}
              stroke="var(--tm-rule)"
              allowDecimals={false}
            />
            <Tooltip
              contentStyle={{
                background: "var(--tm-bg-2)",
                border: "1px solid var(--tm-rule)",
                fontSize: 11,
                fontFamily: "var(--font-jetbrains-mono)",
                color: "var(--tm-fg)",
              }}
              labelFormatter={(label) => `Week of ${label}`}
            />
            <Area
              type="monotone"
              dataKey="count"
              stroke="var(--tm-accent)"
              strokeWidth={1.5}
              fill="url(#tm-activity-grad)"
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </TmPane>
  );
}

/* ── Catalog with filter + sort ───────────────────────────────────── */

function ZooCatalogPane({
  entries,
  decayIds,
  staleIds,
  locale,
  onLoadBacktest,
  onLoadReport,
  onLoadScreener,
  onDelete,
}: {
  readonly entries: readonly ZooEntry[];
  readonly decayIds: ReadonlySet<string>;
  readonly staleIds: ReadonlySet<string>;
  readonly locale: "zh" | "en";
  readonly onLoadBacktest: (e: ZooEntry) => void;
  readonly onLoadReport: (e: ZooEntry) => void;
  readonly onLoadScreener: (e: ZooEntry) => void;
  readonly onDelete: (id: string) => void;
}) {
  const [dirFilter, setDirFilter] = useState<DirFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sortCol, setSortCol] = useState<SortCol>("savedAt");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const filtered = useMemo(() => {
    let xs = [...entries];
    if (dirFilter !== "all") {
      xs = xs.filter((e) => (e.direction ?? "long_short") === dirFilter);
    }
    if (statusFilter === "decaying") xs = xs.filter((e) => decayIds.has(e.id));
    else if (statusFilter === "stale") xs = xs.filter((e) => staleIds.has(e.id));
    else if (statusFilter === "champion") {
      xs = xs.filter((e) => (e.headlineMetrics?.testSharpe ?? 0) >= 1.0);
    }
    xs.sort((a, b) => {
      const sign = sortDir === "asc" ? 1 : -1;
      switch (sortCol) {
        case "sharpe":
          return (
            sign *
            ((a.headlineMetrics?.testSharpe ?? -Infinity) -
              (b.headlineMetrics?.testSharpe ?? -Infinity))
          );
        case "return":
          return (
            sign *
            ((a.headlineMetrics?.totalReturn ?? -Infinity) -
              (b.headlineMetrics?.totalReturn ?? -Infinity))
          );
        case "ic":
          return (
            sign *
            ((a.headlineMetrics?.testIc ?? -Infinity) -
              (b.headlineMetrics?.testIc ?? -Infinity))
          );
        case "name":
          return sign * a.name.localeCompare(b.name);
        case "savedAt":
        default:
          return sign * (new Date(a.savedAt).getTime() - new Date(b.savedAt).getTime());
      }
    });
    return xs;
  }, [entries, dirFilter, statusFilter, sortCol, sortDir, decayIds, staleIds]);

  function toggleSort(col: SortCol) {
    if (sortCol === col) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortCol(col);
      setSortDir(col === "name" ? "asc" : "desc");
    }
  }

  const dirChips: { code: DirFilter; label: string }[] = [
    { code: "all", label: "all" },
    { code: "long_short", label: "long_short" },
    { code: "long_only", label: "long_only" },
    { code: "short_only", label: "short_only" },
  ];
  const statusChips: { code: StatusFilter; label: string; tone?: "warn" }[] = [
    { code: "all", label: "all" },
    { code: "champion", label: `champion (≥1.0 SR)` },
    { code: "decaying", label: "decaying", tone: "warn" },
    { code: "stale", label: "stale", tone: "warn" },
  ];

  return (
    <TmPane
      title="ZOO.CATALOG"
      meta={`${filtered.length}/${entries.length} ENTRIES`}
    >
      <div className="flex flex-wrap items-center gap-1.5 border-b border-tm-rule bg-tm-bg-2 px-3 py-1.5">
        <span className="font-tm-mono text-[10px] uppercase tracking-[0.06em] text-tm-muted">
          DIR
        </span>
        {dirChips.map((c) => (
          <TmChip
            key={c.code}
            on={dirFilter === c.code}
            onClick={() => setDirFilter(c.code)}
          >
            {c.label}
          </TmChip>
        ))}
        <span className="ml-3 font-tm-mono text-[10px] uppercase tracking-[0.06em] text-tm-muted">
          STATUS
        </span>
        {statusChips.map((c) => (
          <TmChip
            key={c.code}
            on={statusFilter === c.code}
            tone={c.tone}
            onClick={() => setStatusFilter(c.code)}
          >
            {c.label}
          </TmChip>
        ))}
      </div>

      {filtered.length === 0 ? (
        <p className="px-3 py-6 text-center font-tm-mono text-[11px] text-tm-muted">
          {entries.length === 0
            ? t(locale, "zoo.empty")
            : "no entries match the current filter."}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <div
            className="grid min-w-[1180px] gap-px bg-tm-rule"
            style={{
              gridTemplateColumns:
                "minmax(140px, 180px) 60px minmax(220px, 1fr) 80px 80px 80px minmax(120px, 140px) minmax(280px, 320px)",
            }}
          >
            <SortHeader col="name" current={sortCol} dir={sortDir} onClick={toggleSort}>
              {t(locale, "zoo.colName")}
            </SortHeader>
            <Header>DIR</Header>
            <Header>{t(locale, "zoo.colExpr")}</Header>
            <SortHeader col="sharpe" current={sortCol} dir={sortDir} onClick={toggleSort} align="right">
              {t(locale, "zoo.colSharpe")}
            </SortHeader>
            <SortHeader col="return" current={sortCol} dir={sortDir} onClick={toggleSort} align="right">
              {t(locale, "zoo.colReturn")}
            </SortHeader>
            <SortHeader col="ic" current={sortCol} dir={sortDir} onClick={toggleSort} align="right">
              {t(locale, "zoo.colIc")}
            </SortHeader>
            <SortHeader col="savedAt" current={sortCol} dir={sortDir} onClick={toggleSort}>
              {t(locale, "zoo.colSavedAt")}
            </SortHeader>
            <Header align="right">ACTIONS</Header>
            {filtered.map((e) => (
              <ZooRow
                key={e.id}
                entry={e}
                locale={locale}
                isDecaying={decayIds.has(e.id)}
                isStale={staleIds.has(e.id)}
                onLoadBacktest={() => onLoadBacktest(e)}
                onLoadReport={() => onLoadReport(e)}
                onLoadScreener={() => onLoadScreener(e)}
                onDelete={() => onDelete(e.id)}
              />
            ))}
          </div>
        </div>
      )}
    </TmPane>
  );
}

function Header({
  children,
  align = "left",
}: {
  readonly children: React.ReactNode;
  readonly align?: "left" | "right";
}) {
  return (
    <div
      className={`bg-tm-bg-2 px-2 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted ${
        align === "right" ? "text-right" : ""
      }`}
    >
      {children}
    </div>
  );
}

function SortHeader({
  children,
  col,
  current,
  dir,
  onClick,
  align = "left",
}: {
  readonly children: React.ReactNode;
  readonly col: SortCol;
  readonly current: SortCol;
  readonly dir: SortDir;
  readonly onClick: (col: SortCol) => void;
  readonly align?: "left" | "right";
}) {
  const active = col === current;
  const arrow = active ? (dir === "asc" ? "▲" : "▼") : "·";
  return (
    <button
      type="button"
      onClick={() => onClick(col)}
      className={`flex items-center gap-1 bg-tm-bg-2 px-2 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] hover:text-tm-fg ${
        align === "right" ? "justify-end" : ""
      } ${active ? "text-tm-accent" : "text-tm-muted"}`}
    >
      <span>{children}</span>
      <span className="text-[8px]">{arrow}</span>
    </button>
  );
}

function HCell({
  children,
  align = "left",
}: {
  readonly children: React.ReactNode;
  readonly align?: "left" | "right";
}) {
  return (
    <div
      className={`bg-tm-bg-2 px-2 py-1 font-tm-mono text-[9.5px] font-semibold uppercase tracking-[0.06em] text-tm-muted ${
        align === "right" ? "text-right" : ""
      }`}
    >
      {children}
    </div>
  );
}

function DCell({
  children,
  align = "left",
  title,
}: {
  readonly children: React.ReactNode;
  readonly align?: "left" | "right";
  readonly title?: string;
}) {
  return (
    <div
      className={`flex min-w-0 items-center bg-tm-bg px-2 py-1 font-tm-mono text-[11px] ${
        align === "right" ? "justify-end" : ""
      }`}
      title={title}
    >
      {children}
    </div>
  );
}

function DirBadge({ direction }: { readonly direction: "long_short" | "long_only" | "short_only" }) {
  const map = {
    long_short: { label: "LS", tone: "text-tm-accent" },
    long_only: { label: "LO", tone: "text-tm-pos" },
    short_only: { label: "SO", tone: "text-tm-neg" },
  } as const;
  const { label, tone } = map[direction];
  return (
    <span className={`inline-block border border-current px-1 py-px font-tm-mono text-[9.5px] tabular-nums ${tone}`}>
      {label}
    </span>
  );
}

function ZooRow({
  entry,
  locale,
  isDecaying,
  isStale,
  onLoadBacktest,
  onLoadReport,
  onLoadScreener,
  onDelete,
}: {
  readonly entry: ZooEntry;
  readonly locale: "zh" | "en";
  readonly isDecaying: boolean;
  readonly isStale: boolean;
  readonly onLoadBacktest: () => void;
  readonly onLoadReport: () => void;
  readonly onLoadScreener: () => void;
  readonly onDelete: () => void;
}) {
  const sharpe = entry.headlineMetrics?.testSharpe;
  const totalRet = entry.headlineMetrics?.totalReturn;
  const ic = entry.headlineMetrics?.testIc;
  const dir = entry.direction ?? "long_short";
  return (
    <>
      <div className="flex min-w-0 items-center gap-1.5 bg-tm-bg px-2 py-1 font-tm-mono text-[11px]">
        <span className="truncate text-tm-accent">{entry.name}</span>
        {isDecaying && <span title="decaying" className="text-tm-warn">⚠</span>}
        {isStale && <span title="stale" className="text-tm-info">⏱</span>}
      </div>
      <div className="flex items-center bg-tm-bg px-2 py-1">
        <DirBadge direction={dir} />
      </div>
      <div
        className="flex min-w-0 items-center bg-tm-bg px-2 py-1 font-tm-mono text-[11px]"
        title={entry.expression}
      >
        <span className="block truncate text-tm-fg-2">{entry.expression}</span>
      </div>
      <NumCell value={sharpe} format={(v) => v.toFixed(2)} />
      <NumCell value={totalRet} format={(v) => `${(v * 100).toFixed(1)}%`} />
      <NumCell value={ic} format={(v) => v.toFixed(3)} />
      <DCell>
        <span className="text-tm-muted">
          {new Date(entry.savedAt).toLocaleString(
            locale === "zh" ? "zh-CN" : "en-US",
            {
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            },
          )}
        </span>
      </DCell>
      <DCell align="right">
        <div className="flex justify-end gap-1">
          <TmButton variant="ghost" onClick={onLoadBacktest} className="h-6 px-1.5 text-[10px]">
            {t(locale, "zoo.actLoadBacktest")}
          </TmButton>
          <TmButton variant="ghost" onClick={onLoadReport} className="h-6 px-1.5 text-[10px]">
            {t(locale, "zoo.actLoadReport")}
          </TmButton>
          <TmButton variant="ghost" onClick={onLoadScreener} className="h-6 px-1.5 text-[10px]">
            {t(locale, "zoo.actLoadScreener")}
          </TmButton>
          <TmButton variant="ghost" onClick={onDelete} className="h-6 px-1.5 text-[10px]">
            {t(locale, "zoo.actDelete")}
          </TmButton>
        </div>
      </DCell>
    </>
  );
}

function NumCell({
  value,
  format,
}: {
  readonly value: number | undefined;
  readonly format: (v: number) => string;
}) {
  if (value == null) {
    return (
      <DCell align="right">
        <span className="text-tm-muted">—</span>
      </DCell>
    );
  }
  const tone =
    value > 0 ? "text-tm-pos" : value < 0 ? "text-tm-neg" : "text-tm-fg";
  return (
    <DCell align="right">
      <span className={`tabular-nums ${tone}`}>{format(value)}</span>
    </DCell>
  );
}

/* ── Correlation panel (unchanged) ────────────────────────────────── */

function CorrelationPanel({
  data,
}: {
  readonly data: ZooCorrelationResponse;
}) {
  const { locale } = useLocale();
  const { names, matrix, warnings } = data;

  function cellTone(v: number): string {
    if (v >= 0.95) return "bg-tm-neg-soft text-tm-neg";
    if (v >= 0.8) return "bg-tm-warn-soft text-tm-warn";
    if (v >= 0.5) return "bg-tm-warn-soft text-tm-warn";
    if (v >= -0.5) return "text-tm-fg-2";
    return "bg-tm-accent-soft text-tm-accent";
  }

  return (
    <div className="flex flex-col">
      {warnings.length > 0 && (
        <div className="border-b border-tm-rule bg-tm-bg-2 px-3 py-2.5">
          <div className="mb-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-neg">
            {t(locale, "zoo.corr.warningsHeader").replace(
              "{n}",
              String(warnings.length),
            )}
          </div>
          <ul className="flex flex-col gap-1">
            {warnings.map((w) => (
              <li
                key={`${w.a}|${w.b}`}
                className="flex items-center gap-2 font-tm-mono text-[11px]"
              >
                <span className="text-tm-fg">{w.a}</span>
                <span className="text-tm-muted">↔</span>
                <span className="text-tm-fg">{w.b}</span>
                <span className="ml-2 tabular-nums text-tm-neg">
                  corr = {w.corr >= 0 ? "+" : ""}
                  {w.corr.toFixed(3)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="overflow-x-auto px-3 py-3">
        <table className="font-tm-mono text-[10.5px]">
          <thead>
            <tr>
              <th className="px-2 py-1"></th>
              {names.map((n) => (
                <th
                  key={n}
                  className="whitespace-nowrap px-2 py-1 text-left text-tm-muted"
                >
                  {n}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.map((row, i) => (
              <tr key={names[i]}>
                <td className="whitespace-nowrap px-2 py-1 text-tm-muted">
                  {names[i]}
                </td>
                {row.map((v, j) => (
                  <td
                    key={j}
                    className={`px-2 py-1 text-center tabular-nums ${cellTone(v)}`}
                  >
                    {v >= 0 ? "+" : ""}
                    {v.toFixed(2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
