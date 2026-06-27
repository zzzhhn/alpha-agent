"use client";

import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { buildSmokeScorecard, type QcStatus } from "@/lib/factorQc";
import type { SmokeReport } from "@/lib/types";
import type { PaneState } from "./types";

interface Props {
  state: PaneState;
  data: SmokeReport | null;
  errorMessage: string | null;
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

export function SmokePane({ state, data, errorMessage, onRetry }: Props) {
  const { locale } = useLocale();
  const tk = (k: string) => t(locale, k as Parameters<typeof t>[1]);
  // Pure + total, so safe to compute before branching (no IIFE in JSX that could
  // throw and unmount the subtree — see feedback_render_throw_unmounts_subtree).
  const sc = data ? buildSmokeScorecard(data) : null;

  return (
    <section className="flex flex-col gap-2 rounded border border-tm-rule bg-tm-bg-2 p-3">
      <h3 className="font-tm-mono text-xs font-semibold uppercase text-tm-fg-2">
        {tk("alpha.pane.smoke")}
      </h3>
      {state === "waiting" || state === "loading" ? (
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
        </>
      ) : null}
    </section>
  );
}
