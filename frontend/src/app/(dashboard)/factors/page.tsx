"use client";

// Catalog-first workstation view. Analytics summarize stored snapshots, not a new backtest.

import { useEffect, useMemo, useRef, useState } from "react";
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
import { exportZooJson, importZooJson, listZoo, removeFromZoo, seedZooIfFirstRun, type ZooEntry } from "@/lib/factor-zoo";
import { runZooCorrelation } from "@/lib/api";
import type { ZooCorrelationResponse } from "@/lib/types";
import { TmScreen, TmPane, TmCols2 } from "@/components/tm/TmPane";
import { TmKpi, TmKpiGrid } from "@/components/tm/TmKpi";
import { TmButton, TmIconButton } from "@/components/tm/TmButton";
import {
  TmTable,
  TmTableBody,
  TmTableCell,
  TmTableFrame,
  TmTableHead,
  TmTableHeaderCell,
  TmTableRow,
  TmTableRowHeader,
} from "@/components/tm/TmTable";
import { SegmentedTabs } from "@/components/ui/SegmentedTabs";
import { ZooCatalog } from "@/components/zoo/ZooCatalog";
import { isFiniteZooMetric } from "@/components/zoo/zoo-catalog";
import { GlossaryTip } from "@/components/zoo/GlossaryTip";
import { WorkbenchHeader } from "@/components/workbench/WorkbenchHeader";

/* ── Constants ────────────────────────────────────────────────────── */

const STALE_DAY_THRESHOLD = 30;
const STALE_SHARPE_THRESHOLD = 0.5;
const TOP_K = 5;
const OPS_TOP_N = 10;
const MIN_DISTRIBUTION_SAMPLES = 10;
const MAX_CORRELATION_FACTORS = 20;
const EMPTY_ENTRIES: readonly ZooEntry[] = [];

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
    count: values.filter((v) => v >= b.lo && v < b.hi).length,
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
  const day = d.getUTCDay();
  // 0 = Sunday → roll back 6; 1..6 → roll back day-1
  const offset = day === 0 ? 6 : day - 1;
  const monday = new Date(d);
  monday.setUTCDate(d.getUTCDate() - offset);
  monday.setUTCHours(0, 0, 0, 0);
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

interface Aggregates {
  readonly avgSharpe: number | null;
  readonly medianIC: number | null;
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

  const ranked = entries.flatMap((entry) => {
    const sharpe = entry.headlineMetrics?.testSharpe;
    return isFiniteZooMetric(sharpe) ? [{ entry, sharpe }] : [];
  }).sort((a, b) => b.sharpe - a.sharpe).map(({ entry }) => entry);
  // Separate leaderboards only when both can show distinct entries.
  const top5 = ranked.length >= TOP_K * 2 ? ranked.slice(0, TOP_K) : [];
  const bottom5 = ranked.length >= TOP_K * 2 ? ranked.slice(-TOP_K).reverse() : [];

  const staleEntries = entries.filter((e) => {
    const sharpe = e.headlineMetrics?.testSharpe;
    return (
      ageDays(e.savedAt) >= STALE_DAY_THRESHOLD &&
      isFiniteZooMetric(sharpe) &&
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


export default function FactorsPage() {
  const { locale } = useLocale();
  const router = useRouter();
  const zh = locale === "zh";
  const [storedEntries, setEntries] = useState<readonly ZooEntry[] | null>(null);
  const entries = storedEntries ?? EMPTY_ENTRIES;
  const [prefillError, setPrefillError] = useState(false);

  useEffect(() => {
    seedZooIfFirstRun();
    setEntries(listZoo());
  }, []);

  const aggregates = useMemo(() => computeAggregates(entries), [entries]);
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
      setPrefillError(true);
      return;
    }
    setPrefillError(false);
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
      setPrefillError(true);
      return;
    }
    setPrefillError(false);
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
      setPrefillError(true);
      return;
    }
    setPrefillError(false);
    router.push("/screener");
  }

  const [zooView, setZooView] = useState<"analytics" | "manage">("manage");
  const [corrLoading, setCorrLoading] = useState(false);
  const [corrSnapshot, setCorrSnapshot] = useState<(
    { result: ZooCorrelationResponse; error?: never } | { error: string; result?: never }
  ) & { entries: readonly ZooEntry[] } | null>(null);
  const currentCorrelation = corrSnapshot?.entries === entries ? corrSnapshot : null;
  const corrResult = currentCorrelation?.result;
  const corrError = currentCorrelation?.error;
  const corrEntries = entries.slice(0, MAX_CORRELATION_FACTORS);

  const [zooTransfer, setZooTransfer] = useState<string | null>(null);
  const importInput = useRef<HTMLInputElement>(null);

  function downloadZoo() {
    const blob = new Blob([exportZooJson()], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `alphacore-factor-zoo-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(url);
    setZooTransfer(zh ? `已导出 ${entries.length} 个因子` : `Exported ${entries.length} factors`);
  }

  async function uploadZoo(file: File) {
    try {
      const { added, skipped } = importZooJson(await file.text());
      setEntries(listZoo());
      setCorrSnapshot(null);
      setZooTransfer(zh ? `已导入 ${added} 个，跳过 ${skipped} 个（重复或格式不符）` : `Imported ${added}, skipped ${skipped} (duplicate or malformed)`);
    } catch {
      setZooTransfer(zh ? "文件不是有效的因子库 JSON，未做任何改动" : "Not a valid factor library JSON; nothing changed");
    }
  }

  function deleteEntry(id: string) {
    removeFromZoo(id);
    const next = listZoo();
    if (next.some((entry) => entry.id === id)) return false;
    setEntries(next);
    setCorrSnapshot(null);
    return true;
  }

  async function checkCorrelation() {
    if (corrEntries.length < 2 || corrLoading) return;
    setCorrLoading(true);
    setCorrSnapshot(null);
    try {
      const res = await runZooCorrelation({
        factors: corrEntries.map((entry) => ({
          spec: {
            name: entry.name,
            hypothesis: entry.hypothesis ?? "",
            expression: entry.expression,
            operators_used: [...extractOps(entry.expression)],
            lookback: 12,
            universe: "SP500",
            justification: entry.intuition ?? entry.hypothesis ?? "zoo entry",
          },
          label: entry.name,
        })),
      });
      if (res.error || !res.data) setCorrSnapshot({ entries, error: res.error ?? (zh ? "未返回结果。" : "No result returned.") });
      else setCorrSnapshot({ entries, result: res.data });
    } catch {
      setCorrSnapshot({ entries, error: zh ? "未能读取计算结果。" : "Could not read the correlation result." });
    } finally {
      setCorrLoading(false);
    }
  }

  const distributions = [
    { title: zh ? "测试夏普" : "Test Sharpe", data: aggregates.sharpeDist, accent: "var(--tm-accent)" },
    { title: zh ? "总收益" : "Total return", data: aggregates.returnDist, accent: "var(--tm-pos)" },
    { title: "IC", data: aggregates.icDist, accent: "var(--tm-info)" },
  ].map((item) => ({ ...item, samples: item.data.reduce((sum, bin) => sum + bin.count, 0) }));

  return (
    <TmScreen className="!h-auto min-h-full">
      <WorkbenchHeader
        eyebrow={zh ? "研究 · 因子资产" : "Research · Factor assets"}
        title={zh ? "因子库" : "Factor Zoo"}
        subtitle={zh ? "复用本地因子，比较保存时的回测快照。" : "Reuse local factors and compare saved backtest snapshots."}
        statuses={[
          { label: zh ? "本地因子" : "Local factors", value: storedEntries ? String(entries.length) : "—" },
          ...(staleIds.size ? [{ label: zh ? "待复测" : "Review due", value: String(staleIds.size), tone: "warning" as const }] : []),
        ]}
      />
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-y-2 bg-tm-bg-2">
        <SegmentedTabs
          idBase="zoo"
          items={[
            { key: "manage", label: zh ? "因子目录" : "Catalog" },
            { key: "analytics", label: entries.length < MIN_DISTRIBUTION_SAMPLES ? (zh ? `库内分析 ${entries.length}/${MIN_DISTRIBUTION_SAMPLES}` : `Library analysis ${entries.length}/${MIN_DISTRIBUTION_SAMPLES}`) : (zh ? "库内分析" : "Library analysis") },
          ]}
          active={zooView}
          onChange={setZooView}
          ariaLabel={zh ? "因子库视图" : "Factor library view"}
          className="min-w-0 !border-b-0 [&_button]:focus-visible:ring-1 [&_button]:focus-visible:ring-inset [&_button]:focus-visible:ring-tm-accent"
        />
        <div className="flex flex-wrap items-center gap-2 px-3 py-1">
          <TmButton size="sm" variant="secondary" onClick={downloadZoo} disabled={entries.length === 0}
            title={zh ? "因子库只存在本浏览器，账户导出不包含它；可在此下载 JSON 备份。" : "The library lives only in this browser and is not part of the account export; download a JSON backup here."}>
            {zh ? "导出 JSON" : "Export JSON"}
          </TmButton>
          <TmButton size="sm" variant="secondary" onClick={() => importInput.current?.click()}>
            {zh ? "导入 JSON" : "Import JSON"}
          </TmButton>
          {/* File pickers have no TM primitive; the visible control is the TmButton above. */}
          <input ref={importInput} type="file" accept="application/json,.json" className="sr-only" tabIndex={-1} aria-hidden="true" onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void uploadZoo(file); }} />
          {zooTransfer ? <span role="status" className="text-xs text-tm-muted">{zooTransfer}</span> : null}
          <TmButton
            size="sm"
            onClick={() => {
              setZooView("analytics");
              document.getElementById("zoo-tab-analytics")?.focus();
              void checkCorrelation();
            }}
            loading={corrLoading}
            loadingLabel={t(locale, "zoo.corr.running")}
            disabled={entries.length < 2}
            title={entries.length < 2 ? t(locale, "zoo.corr.disabledHint") : undefined}
          >
            {entries.length > MAX_CORRELATION_FACTORS
              ? (zh ? `检查最近 ${MAX_CORRELATION_FACTORS} 个因子` : `Check correlation · latest ${MAX_CORRELATION_FACTORS}`)
              : t(locale, "zoo.corr.run")}
          </TmButton>
        </div>
      </div>

      {prefillError && (
        <p role="alert" className="border-b border-tm-rule px-3 py-2 text-xs text-tm-neg">
          {zh ? "未能传递因子。请允许此浏览器使用会话存储后重试。" : "Could not pass the factor to the next page. Allow session storage in this browser and try again."}
        </p>
      )}
      <div id="zoo-panel-manage" role="tabpanel" aria-labelledby="zoo-tab-manage" hidden={zooView !== "manage"}>
        <ZooCatalog
          entries={storedEntries}
          staleIds={staleIds}
          locale={locale}
          onLoadBacktest={loadIntoBacktest}
          onLoadReport={loadIntoReport}
          onLoadScreener={loadIntoScreener}
          onDelete={deleteEntry}
        />
      </div>

      <div id="zoo-panel-analytics" role="tabpanel" aria-labelledby="zoo-tab-analytics" hidden={zooView !== "analytics"}>
        {zooView === "analytics" && (
          <div className="min-w-0 [&>*+*]:border-t [&>*+*]:border-tm-rule">
            <TmPane title="CORRELATION" meta={corrResult
              ? (zh ? `${corrResult.names.length} 个因子 · 面板 ${corrResult.n_sessions} 个交易日` : `${corrResult.names.length} factors · ${corrResult.n_sessions} panel sessions`)
              : undefined}>
              <p className="border-b border-tm-rule px-3 py-2 text-xs leading-5 text-tm-muted">
                {entries.length < 2 ? t(locale, "zoo.corr.disabledHint") : zh
                  ? `按统一的等权多空口径计算日收益相关性（做多前 30%、做空后 30%），不使用各自保存的回测设置。${entries.length > MAX_CORRELATION_FACTORS ? ` 本次范围为最近保存的 ${MAX_CORRELATION_FACTORS} / ${entries.length} 个因子。` : ""}`
                  : `Uses one equal-weight long/short strategy (top and bottom 30%) for all expressions, not each factor's saved settings.${entries.length > MAX_CORRELATION_FACTORS ? ` Includes the ${MAX_CORRELATION_FACTORS} most recently saved of ${entries.length} factors.` : ""}`}
              </p>
              {corrLoading && <p role="status" className="px-3 py-3 text-xs text-tm-muted">{t(locale, "zoo.corr.running")}</p>}
              {corrError && (
                <div role="alert" className="px-3 py-3 text-xs text-tm-neg">
                  <p>{zh ? "相关性计算失败，请重试。" : "Correlation check failed. Try again."}</p>
                  <p className="mt-1 break-words text-tm-muted">{corrError}</p>
                </div>
              )}
              {corrResult && <CorrelationPanel data={corrResult} />}
            </TmPane>
            {entries.length > 0 && (
              <>
                <TmPane
                  title={zh ? "保存指标概览" : "Saved metrics"}
                  meta={zh ? "仅描述已记录值，不代表当前回测" : "Recorded values only · not a current backtest"}
                >
                  <TmKpiGrid>
                    <TmKpi label={zh ? "平均测试夏普" : "Mean test Sharpe"} value={aggregates.avgSharpe?.toFixed(2) ?? "—"}
                      sub={zh ? `已记录 ${distributions[0].samples} / ${entries.length}` : `${distributions[0].samples} / ${entries.length} recorded`} />
                    <TmKpi label={zh ? "测试 IC 中位数" : "Median test IC"} value={aggregates.medianIC?.toFixed(3) ?? "—"}
                      sub={zh ? `已记录 ${distributions[2].samples} / ${entries.length}` : `${distributions[2].samples} / ${entries.length} recorded`} />
                  </TmKpiGrid>
                </TmPane>
                {aggregates.bottom5.length > 0 && (
                  <TmCols2>
                    <LeaderSide title={zh ? "测试夏普前 5" : "Top 5 test Sharpe"} tone="pos" entries={aggregates.top5} onPick={loadIntoBacktest} />
                    <LeaderSide title={zh ? "测试夏普后 5" : "Bottom 5 test Sharpe"} tone="neg" entries={aggregates.bottom5} onPick={loadIntoBacktest} />
                  </TmCols2>
                )}
                <TmCols2>
                  <OperatorUsagePane opsCount={aggregates.opsCount} totalEntries={entries.length} />
                  <DirectionMixPane dirSplit={aggregates.dirSplit} totalEntries={entries.length} />
                </TmCols2>
                <TmPane title="PERF.DIST">
                  <div className="grid grid-cols-1 gap-px bg-tm-rule xl:grid-cols-3">
                    {distributions.map(({ title, data, accent, samples }) => samples >= MIN_DISTRIBUTION_SAMPLES
                      ? <DistChart key={title} title={title} data={data} accent={accent} />
                      : <p key={title} className="bg-tm-bg px-3 py-3 text-xs text-tm-muted">
                          {zh ? `${title}：${samples} 个已记录，满 ${MIN_DISTRIBUTION_SAMPLES} 个后显示分布。` : `${title}: ${samples} recorded; distribution shown from ${MIN_DISTRIBUTION_SAMPLES} values.`}
                        </p>)}
                  </div>
                </TmPane>
                {aggregates.activeWeekCount > 1 && (
                  <TimelineActivityPane weeks={aggregates.activityWeeks} activeWeekCount={aggregates.activeWeekCount} peakWeek={aggregates.peakWeek} totalEntries={aggregates.activityWeeks.reduce((sum, week) => sum + week.count, 0)} />
                )}
              </>
            )}
          </div>
        )}
      </div>
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
  const { locale } = useLocale();
  const zh = locale === "zh";
  const accentClass = tone === "pos" ? "text-tm-accent" : "text-tm-fg-2";
  return (
    <TmPane title={title} className="min-w-0">
      {entries.length === 0 ? (
        <p className="px-3 py-3 font-tm-mono text-xs text-tm-muted">
          {zh ? "没有可排名的因子。" : "No ranked factors."}
        </p>
      ) : (
        <div
          className="grid gap-px bg-tm-rule"
          style={{ gridTemplateColumns: "32px 1fr 64px 64px 60px" }}
        >
          <HCell>#</HCell>
          <HCell>{t(locale, "zoo.colName")}</HCell>
          <HCell align="right">
            <GlossaryTip term="SHARPE">{zh ? "夏普" : "Sharpe"}</GlossaryTip>
          </HCell>
          <HCell align="right">
            <GlossaryTip term="IC">IC</GlossaryTip>
          </HCell>
          <HCell align="right">{zh ? "回测" : "Test"}</HCell>
          {entries.map((e, i) => {
            const sh = e.headlineMetrics?.testSharpe;
            const ic = e.headlineMetrics?.testIc;
            return (
              <LeaderRow
                key={e.id}
                rank={i + 1}
                name={e.name}
                expr={e.expression}
                sharpe={sh}
                ic={ic}
                accentClass={accentClass}
                actionLabel={t(locale, "zoo.actLoadBacktest")}
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
  actionLabel,
  onPick,
}: {
  readonly rank: number;
  readonly name: string;
  readonly expr: string;
  readonly sharpe: number | undefined;
  readonly ic: number | undefined;
  readonly accentClass: string;
  readonly actionLabel: string;
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
        <span className={`tabular-nums ${accentClass}`}>{isFiniteZooMetric(sharpe) ? sharpe.toFixed(2) : "—"}</span>
      </DCell>
      <DCell align="right">
        <span className="tabular-nums text-tm-fg-2">{isFiniteZooMetric(ic) ? ic.toFixed(3) : "—"}</span>
      </DCell>
      <DCell align="right">
        <TmIconButton
          onClick={onPick}
          label={`${actionLabel}: ${name}`}
          variant="ghost"
          icon={<span aria-hidden="true">▶</span>}
        />
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
  const { locale } = useLocale();
  const zh = locale === "zh";
  return (
    <TmPane title="OPS.USAGE" meta={zh ? "按因子出现次数" : "By number of factors"}>
      {opsCount.length === 0 ? (
        <p className="px-3 py-3 font-tm-mono text-xs text-tm-muted">
          {zh ? "未发现运算符。" : "No operators detected."}
        </p>
      ) : (
        <ul className="flex flex-col">
          {opsCount.map(([op, count]) => {
            const sharePct = totalEntries > 0 ? (count / totalEntries) * 100 : 0;
            return (
              <li
                key={op}
                className="grid items-center gap-3 border-b border-tm-rule px-3 py-1 last:border-b-0"
                style={{ gridTemplateColumns: "minmax(120px, 140px) 1fr 60px 50px" }}
              >
                <span className="truncate font-tm-mono text-xs text-tm-accent">
                  {op}
                </span>
                <div className="relative h-3 w-full bg-tm-bg-2">
                  <div
                    className="h-full bg-tm-accent-soft"
                    style={{ width: `${sharePct}%` }}
                  />
                </div>
                <span className="text-right font-tm-mono text-xs tabular-nums text-tm-fg-2">
                  {count}
                </span>
                <span className="text-right font-tm-mono text-xs tabular-nums text-tm-muted">
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
  const { locale } = useLocale();
  const zh = locale === "zh";
  // Static class strings (Tailwind only ships classes that appear
  // verbatim in source — `bg-${tone}` interpolation gets tree-shaken).
  const dirs: {
    readonly code: string;
    readonly label: string;
    readonly textClass: string;
    readonly barClass: string;
  }[] = [
    { code: "long_short", label: zh ? "多空" : "Long/short", textClass: "text-tm-accent", barClass: "bg-tm-accent" },
    { code: "long_only", label: zh ? "仅多头" : "Long only", textClass: "text-tm-fg-2", barClass: "bg-tm-accent" },
    { code: "short_only", label: zh ? "仅空头" : "Short only", textClass: "text-tm-fg-2", barClass: "bg-tm-accent" },
  ];
  return (
    <TmPane title="DIR.MIX">
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
              <span className={`font-tm-mono text-xs ${d.textClass}`}>
                {d.label}
              </span>
              <div className="relative h-3 w-full bg-tm-bg-2">
                <div
                  className={`h-full opacity-60 ${d.barClass}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="text-right font-tm-mono text-xs tabular-nums text-tm-fg-2">
                {count}
              </span>
              <span className="text-right font-tm-mono text-xs tabular-nums text-tm-muted">
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
  const { locale } = useLocale();
  const zh = locale === "zh";
  return (
    <div className="flex min-w-0 flex-col bg-tm-bg">
      <div className="border-b border-tm-rule bg-tm-bg-2 px-3 py-1.5 font-tm-mono text-xs font-semibold uppercase tracking-[0.06em] text-tm-muted">
        {title} · {zh ? `${data.reduce((sum, bin) => sum + bin.count, 0)} 个已记录` : `${data.reduce((sum, bin) => sum + bin.count, 0)} recorded`}
      </div>
      <div className="h-[180px] w-full px-1 pb-1 pt-2">
        <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
          <BarChart data={data as { label: string; count: number }[]} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="var(--tm-rule)" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 12, fill: "var(--tm-muted)" }}
              stroke="var(--tm-rule)"
              interval={0}
            />
            <YAxis
              tick={{ fontSize: 12, fill: "var(--tm-muted)" }}
              stroke="var(--tm-rule)"
              allowDecimals={false}
            />
            <Tooltip
              contentStyle={{
                background: "var(--tm-bg-2)",
                border: "1px solid var(--tm-rule)",
                fontSize: 12,
                fontFamily: "var(--font-jetbrains-mono)",
                color: "var(--tm-fg)",
              }}
            />
            <Bar dataKey="count" name={zh ? "因子数" : "Factors"} fill={accent} isAnimationActive={false}>
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
  const { locale } = useLocale();
  const zh = locale === "zh";
  // Density caption: avg entries per ACTIVE week (not per total — would
  // suppress the signal once you have a few quiet stretches).
  const avgPerActiveWeek =
    activeWeekCount > 0 ? totalEntries / activeWeekCount : 0;
  return (
    <TmPane
      title="TIMELINE.ACTIVITY"
      meta={zh ? "按目录记录的最后保存时间（UTC）" : "By latest save per catalog entry (UTC)"}
    >
      <TmKpiGrid>
        <TmKpi
          label={zh ? "统计周数" : "Weeks in window"}
          value={weeks.length.toString()}
          sub={`${weeks[0].week} → ${weeks[weeks.length - 1].week}`}
        />
        <TmKpi
          label={zh ? "有保存的周数" : "Active weeks"}
          value={activeWeekCount.toString()}
          sub={zh ? `占统计窗口 ${((activeWeekCount / weeks.length) * 100).toFixed(0)}%` : `${((activeWeekCount / weeks.length) * 100).toFixed(0)}% of window`}
        />
        <TmKpi
          label={zh ? "单周最多保存" : "Peak saves per week"}
          value={peakWeek ? peakWeek.count.toString() : "—"}
          tone={peakWeek ? "pos" : "default"}
          sub={peakWeek?.week}
        />
        <TmKpi
          label={zh ? "活跃周平均保存" : "Mean per active week"}
          value={avgPerActiveWeek.toFixed(1)}
        />
      </TmKpiGrid>

      <div className="h-[160px] w-full px-1 pb-1 pt-2">
        <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
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
              tick={{ fontSize: 12, fill: "var(--tm-muted)" }}
              stroke="var(--tm-rule)"
              interval="preserveStartEnd"
              minTickGap={40}
            />
            <YAxis
              tick={{ fontSize: 12, fill: "var(--tm-muted)" }}
              stroke="var(--tm-rule)"
              allowDecimals={false}
            />
            <Tooltip
              contentStyle={{
                background: "var(--tm-bg-2)",
                border: "1px solid var(--tm-rule)",
                fontSize: 12,
                fontFamily: "var(--font-jetbrains-mono)",
                color: "var(--tm-fg)",
              }}
              labelFormatter={(label) => zh ? `${label} 当周` : `Week of ${label}`}
            />
            <Area
              type="monotone"
              dataKey="count"
              name={zh ? "因子数" : "Factors"}
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


function HCell({
  children,
  align = "left",
}: {
  readonly children: React.ReactNode;
  readonly align?: "left" | "right";
}) {
  return (
    <div
      className={`bg-tm-bg-2 px-2 py-1 font-tm-mono text-xs font-semibold uppercase tracking-[0.06em] text-tm-muted ${
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
      className={`flex min-w-0 items-center bg-tm-bg px-2 py-1 font-tm-mono text-xs ${
        align === "right" ? "justify-end" : ""
      }`}
      title={title}
    >
      {children}
    </div>
  );
}


/* ── Correlation panel ────────────────────────────────────────────── */

function CorrelationPanel({
  data,
}: {
  readonly data: ZooCorrelationResponse;
}) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { names, matrix, warnings } = data;
  const ambiguousZero = matrix.some((row, i) => row.some((value, j) => i !== j && value === 0));

  function cellTone(v: number): string {
    if (Math.abs(v) >= 0.95) return "bg-tm-neg-soft text-tm-neg";
    if (Math.abs(v) >= 0.8) return "bg-tm-warn-soft text-tm-warn";
    return "text-tm-fg-2";
  }

  return (
    <div className="flex flex-col">
      {warnings.length > 0 && (
        <details className="border-b border-tm-rule bg-tm-bg-2 px-3 py-2.5">
          <summary className="cursor-pointer font-tm-mono text-xs font-semibold text-tm-warn">
            {zh ? `${warnings.length} 对需复查（|相关系数| ≥ 0.8）` : `${warnings.length} pairs to review (|correlation| ≥ 0.8)`}
          </summary>
          <ul className="mt-2 flex max-h-44 flex-col gap-1 overflow-y-auto">
            {warnings.map((w) => (
              <li
                key={`${w.a}|${w.b}`}
                className="flex flex-wrap items-center gap-2 break-all font-tm-mono text-xs"
              >
                <span className="text-tm-fg">{w.a}</span>
                <span className="text-tm-muted">↔</span>
                <span className="text-tm-fg">{w.b}</span>
                <span className="ml-2 tabular-nums text-tm-neg">
                  {w.corr >= 0 ? "+" : ""}
                  {w.corr.toFixed(3)}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {ambiguousZero && (
        <p className="px-3 py-2 text-xs text-tm-muted">
          {zh ? "—：接口的零值可能来自重叠数据不足，不能据此判断因子不相关。" : "—: The API also returns zero for insufficient overlap, so this does not establish no correlation."}
        </p>
      )}
      <TmTableFrame className="max-h-96 overflow-y-auto px-3 py-3" tabIndex={0} role="region" aria-label={t(locale, "zoo.corr.title")}>
        <TmTable
          density="compact"
          caption={t(locale, "zoo.corr.title")}
          className="w-auto text-xs"
        >
          <TmTableHead>
            <TmTableRow>
              <TmTableHeaderCell className="px-2 py-1" />
              {names.map((n) => (
                <TmTableHeaderCell key={n} className="whitespace-nowrap px-2 py-1">
                  {n}
                </TmTableHeaderCell>
              ))}
            </TmTableRow>
          </TmTableHead>
          <TmTableBody>
            {matrix.map((row, i) => (
              <TmTableRow key={names[i]}>
                <TmTableRowHeader className="whitespace-nowrap px-2 py-1 text-tm-muted">
                  {names[i]}
                </TmTableRowHeader>
                {row.map((v, j) => (
                  <TmTableCell
                    key={j}
                    numeric
                    textAlign="center"
                    className={`px-2 py-1 ${i === j ? "bg-tm-bg-2 text-tm-muted" : cellTone(v)}`}
                  >
                    {i !== j && v === 0 ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}`}
                  </TmTableCell>
                ))}
              </TmTableRow>
            ))}
          </TmTableBody>
        </TmTable>
      </TmTableFrame>
    </div>
  );
}
