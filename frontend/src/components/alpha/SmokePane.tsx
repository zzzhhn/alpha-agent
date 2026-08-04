"use client";

import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { buildSmokeScorecard, type QcStatus } from "@/lib/factorQc";
import type { FactorBacktestResponse, SmokeReport } from "@/lib/types";
import { PanePlaceholder } from "./PanePlaceholder";
import type { PaneState } from "./types";

interface Props {
  state: PaneState;
  data: SmokeReport | null;
  errorMessage: string | null;
  backtest?: FactorBacktestResponse | null;
  onRetry?: () => void;
}

// Status → status-dot color. pass=green, caution=amber, block=red, mirroring the
// terminal palette used across the workstation.
const DOT: Record<QcStatus, string> = {
  pass: "bg-tm-pos",
  caution: "bg-tm-warn",
  block: "bg-tm-neg",
};

// Verdict → badge classes (the one primary visual of the pane).
const VERDICT_BADGE: Record<QcStatus, string> = {
  pass: "border-tm-pos/40 bg-tm-pos/10 text-tm-pos",
  caution: "border-tm-warn/40 bg-tm-warn/10 text-tm-warn",
  block: "border-tm-neg/40 bg-tm-neg/10 text-tm-neg",
};

function pct(x: number | undefined): string {
  return x === undefined ? "—" : `${(x * 100).toFixed(0)}%`;
}
function num(x: number | undefined, digits: number): string {
  return x === undefined ? "—" : x.toFixed(digits);
}

function Skeleton() {
  return (
    <div className="flex flex-col gap-2">
      <div className="h-3 w-2/3 animate-pulse rounded bg-tm-bg-3" />
      <div className="h-12 w-full animate-pulse rounded bg-tm-bg-3" />
      <div className="h-3 w-1/2 animate-pulse rounded bg-tm-bg-3" />
    </div>
  );
}

function DimRow({
  label,
  value,
  status,
}: {
  label: string;
  value: string;
  status: QcStatus;
}) {
  return (
    <div className="flex items-center justify-between font-tm-mono text-[11px]">
      <span className="text-tm-fg-2">{label}</span>
      <span className="flex items-center gap-1.5">
        <span className="font-mono text-tm-fg">{value}</span>
        <span className={`h-1.5 w-1.5 rounded-full ${DOT[status]}`} />
      </span>
    </div>
  );
}

export function SmokePane({ state, data, errorMessage, onRetry, backtest }: Props) {
  const { locale } = useLocale();
  const tk = (k: string) => t(locale, k as Parameters<typeof t>[1]);
  // Pure + total, so safe to compute before branching (no IIFE in JSX that could
  // throw and unmount the subtree — see feedback_render_throw_unmounts_subtree).
  const sc = data ? buildSmokeScorecard(data) : null;

  return (
    <section className="flex min-h-[260px] flex-col gap-3 border border-tm-rule bg-tm-bg-2 p-4">
      <h3 className="font-tm-mono text-xs font-semibold uppercase tracking-[0.08em] text-tm-accent">
        {tk("alpha.pane.smoke")}
      </h3>
      {state === "waiting" ? (
        <PanePlaceholder hint={tk("alpha.pane.waitingSmoke")} />
      ) : state === "loading" ? (
        <Skeleton />
      ) : state === "error" ? (
        <div className="flex flex-col gap-2 text-xs text-tm-neg">
          <div className="break-words font-tm-mono">{errorMessage}</div>
          {onRetry ? (
            <button
              onClick={onRetry}
              className="w-fit rounded border border-tm-neg/40 px-2 py-0.5 font-tm-mono text-tm-neg hover:bg-tm-neg/10"
            >
              {tk("alpha.pane.retry")}
            </button>
          ) : null}
        </div>
      ) : data && sc ? (
        <>
          {/* Verdict badge — the single primary visual. PASS means the cheap
              structural pre-checks passed (not "good factor"); the subtitle keeps
              that honest: real validity is the backtest's call. */}
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded border px-2 py-0.5 font-tm-mono text-xs font-semibold uppercase ${VERDICT_BADGE[sc.verdict]}`}
            >
              {tk(`alpha.qc.verdict.${sc.verdict}`)}
            </span>
            <span className="text-[11px] text-tm-muted">{tk("alpha.qc.subtitle")}</span>
          </div>

          {/* Three structural dimensions — each value IS its own justification
              (no fabricated composite score). */}
          <div className="flex flex-col gap-1 border-t border-tm-rule pt-2">
            <DimRow
              label={tk("alpha.qc.dim.integrity")}
              value={`σ ${num(data.factor_std, 3)}`}
              status={sc.integrity}
            />
            <DimRow
              label={tk("alpha.qc.dim.stability")}
              value={num(data.rank_stability, 2)}
              status={sc.stability}
            />
            <DimRow
              label={tk("alpha.qc.dim.robustness")}
              value={num(data.robustness, 2)}
              status={sc.robustness}
            />
          </div>

          {/* Actionable detail for whatever tripped — keeps the "how to fix"
              guidance (Forgiveness). Degenerate is blocking and shown alone; the
              two advisories show only when not already blocked. */}
          {data.degenerate ? (
            <div className="rounded border border-tm-neg/40 bg-tm-neg/10 px-2 py-1 font-tm-mono text-[11px] text-tm-neg">
              {tk("alpha.degenerateBlocked")}
            </div>
          ) : null}
          {data.high_turnover && !data.degenerate ? (
            <div className="rounded border border-tm-warn/40 bg-tm-warn/10 px-2 py-1 font-tm-mono text-[11px] text-tm-warn">
              {tk("alpha.highTurnoverWarn")}
            </div>
          ) : null}
          {data.low_robustness && !data.degenerate ? (
            <div className="rounded border border-tm-warn/40 bg-tm-warn/10 px-2 py-1 font-tm-mono text-[11px] text-tm-warn">
              {tk("alpha.lowRobustnessWarn")}
            </div>
          ) : null}
          {/* Only when stability is tripped by full-distribution rank churn that
              the quantile-book turnover did NOT catch — otherwise the turnover
              warning already covers it (the two co-fire on most factors). */}
          {data.low_stability && !data.high_turnover && !data.degenerate ? (
            <div className="rounded border border-tm-warn/40 bg-tm-warn/10 px-2 py-1 font-tm-mono text-[11px] text-tm-warn">
              {tk("alpha.lowStabilityWarn")}
            </div>
          ) : null}

          {/* Diagnostic footer: synthetic IC (indicative only) + turnover (the
              cost-relevant churn number) + run meta. */}
          <div className="font-tm-mono text-[11px] text-tm-muted">
            IC <span className="font-mono">{data.ic_spearman.toFixed(4)}</span>
            {data.turnover !== undefined ? (
              <>
                {" "}&bull;{" "}
                {tk("alpha.pane.turnover")}=<span className={`font-mono ${data.high_turnover ? "text-tm-warn" : ""}`}>{pct(data.turnover)}</span>
              </>
            ) : null}
            {" "}&bull;{" "}
            {tk("alpha.pane.rowsValid")}=<span className="font-mono">{data.rows_valid}</span>
            {" "}&bull;{" "}
            {tk("alpha.pane.runtime")}=<span className="font-mono">{data.runtime_ms}ms</span>
          </div>
          {backtest ? <EvidenceCurve result={backtest} locale={locale} /> : null}
        </>
      ) : null}
    </section>
  );
}

function EvidenceCurve({ result, locale }: { readonly result: FactorBacktestResponse; readonly locale: "zh" | "en" }) {
  const factor = result.equity_curve;
  const benchmark = result.benchmark_curve;
  if (factor.length < 2) return null;
  const values = [...factor.map((point) => point.value), ...benchmark.map((point) => point.value)];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 0.001);
  const points = (series: readonly { date: string; value: number }[]) => series.map((point, index) => {
    const x = 12 + (index / Math.max(series.length - 1, 1)) * 336;
    const y = 100 - ((point.value - min) / range) * 78;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const splitX = 12 + (result.train_end_index / Math.max(factor.length - 1, 1)) * 336;

  return (
    <div className="mt-auto border-t border-tm-rule pt-3">
      <div className="mb-2 flex items-center justify-between text-[9px] uppercase tracking-[0.08em] text-tm-muted">
        <span>{locale === "zh" ? "样本内／样本外证据" : "In-sample / out-of-sample evidence"}</span>
        <span>{result.benchmark_ticker}</span>
      </div>
      <svg viewBox="0 0 360 118" className="h-[132px] w-full border border-tm-rule bg-tm-bg" role="img" aria-label={locale === "zh" ? "因子与基准收益路径" : "Factor and benchmark equity paths"}>
        {[24, 50, 76, 102].map((y) => <line key={y} x1="12" x2="348" y1={y} y2={y} stroke="currentColor" className="text-tm-rule" strokeWidth="0.6" />)}
        <line x1={splitX} x2={splitX} y1="14" y2="104" stroke="currentColor" className="text-tm-warn" strokeDasharray="3 3" strokeWidth="0.8" />
        <polyline points={points(benchmark)} fill="none" stroke="currentColor" className="text-tm-muted" strokeWidth="1.5" />
        <polyline points={points(factor)} fill="none" stroke="currentColor" className="text-tm-pos" strokeWidth="2" />
        <text x="16" y="114" fill="currentColor" className="fill-tm-muted text-[8px]">TRAIN</text>
        <text x={Math.min(splitX + 5, 310)} y="114" fill="currentColor" className="fill-tm-accent text-[8px]">OOS</text>
      </svg>
      <div className="mt-2 flex gap-4 text-[9px] text-tm-muted"><span className="text-tm-pos">{locale === "zh" ? "因子组合" : "Factor"}</span><span>{result.benchmark_ticker}</span><span className="ml-auto">{factor[0].date} → {factor.at(-1)?.date}</span></div>
    </div>
  );
}
