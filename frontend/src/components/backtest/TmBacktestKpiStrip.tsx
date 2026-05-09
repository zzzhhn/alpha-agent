"use client";

/**
 * TmBacktestKpiStrip — workstation port of BacktestKpiStrip.
 *
 * 6-cell TmKpiGrid: total return / Sharpe / IC / max DD / turnover /
 * hit rate. Each cell tone-coded by significance:
 *   - Sharpe: green when PSR ≥ 0.95, red when PSR < 0.5 OR Sharpe CI
 *     spans zero, otherwise muted; hints carry CI [lo, hi] · PSR.
 *   - IC: green when p < 0.05 AND IC > 0; red when CI spans zero or
 *     p > 0.5; hints carry CI [lo, hi] · p.
 *   - Total return: green vs benchmark, hint with bench delta.
 *   - Hit rate: green when > 50%.
 *   - MaxDD: always red (negative metric).
 *
 * Survivorship + overfit warnings render in the pane subbar; legacy
 * version inlined them inside the card header. Subbar slot is more
 * scannable across consecutive runs.
 */

import { TmPane } from "@/components/tm/TmPane";
import { TmKpi, TmKpiGrid } from "@/components/tm/TmKpi";
import { TmStatusPill } from "@/components/tm/TmSubbar";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { FactorBacktestResponse } from "@/lib/types";

export function TmBacktestKpiStrip({
  result,
}: {
  readonly result: FactorBacktestResponse;
}) {
  const { locale } = useLocale();
  const m = result.test_metrics;
  const eq = result.equity_curve;
  const bm = result.benchmark_curve;
  const fullRet =
    eq.length > 0 ? eq[eq.length - 1].value / eq[0].value - 1 : 0;
  const benchRet =
    bm.length > 0 ? bm[bm.length - 1].value / bm[0].value - 1 : 0;
  const dd = m.max_drawdown ?? 0;
  const turnover = m.turnover ?? 0;
  const hitRate = m.hit_rate ?? 0;

  const icir = m.icir ?? 0;
  const icP = m.ic_pvalue ?? 1;
  const icAccent: "pos" | "neg" | "default" =
    icP < 0.05 && m.ic_spearman > 0
      ? "pos"
      : icP > 0.5
        ? "neg"
        : "default";

  const psr = m.psr ?? 0.5;
  const luckyMax = m.lucky_max_sr ?? 0;
  const sharpeLo = m.sharpe_ci_low ?? 0;
  const sharpeHi = m.sharpe_ci_high ?? 0;
  const sharpeCiSpansZero = sharpeLo < 0 && sharpeHi > 0;
  const icLo = m.ic_ci_low ?? 0;
  const icHi = m.ic_ci_high ?? 0;
  const icCiSpansZero = icLo < 0 && icHi > 0;
  const sharpeAccent: "pos" | "neg" | "default" =
    psr >= 0.95
      ? "pos"
      : psr < 0.5 || sharpeCiSpansZero
        ? "neg"
        : m.sharpe >= 1.0
          ? "pos"
          : m.sharpe < 0
            ? "neg"
            : "default";

  return (
    <TmPane
      title="BACKTEST.KPI"
      meta={t(locale, "backtest.kpi.subtitle")
        .replace("{ret}", `${(fullRet * 100).toFixed(1)}%`)
        .replace("{bench}", `${(benchRet * 100).toFixed(1)}%`)}
    >
      {(result.survivorship_corrected !== undefined ||
        result.overfit_flag) && (
        <div className="flex flex-wrap items-center gap-1.5 border-b border-tm-rule bg-tm-bg-2 px-3 py-1.5">
          <TmStatusPill
            tone={result.survivorship_corrected ? "ok" : "warn"}
          >
            {result.survivorship_corrected
              ? `SP500-AS-OF · ${result.membership_as_of ?? "—"}`
              : "LEGACY (NO MEMBERSHIP MASK)"}
          </TmStatusPill>
          {result.overfit_flag && (
            <TmStatusPill tone="err">
              OVERFIT · OOS DECAY{" "}
              {((result.oos_decay ?? 0) * 100).toFixed(0)}%
            </TmStatusPill>
          )}
        </div>
      )}
      <TmKpiGrid>
        <TmKpi
          label={t(locale, "backtest.kpi.totalReturn")}
          value={`${(fullRet * 100).toFixed(1)}%`}
          tone={fullRet > benchRet ? "pos" : "neg"}
          sub={`vs ${(benchRet * 100).toFixed(1)}% bench`}
        />
        <TmKpi
          label={t(locale, "backtest.kpi.testSharpe")}
          value={m.sharpe.toFixed(2)}
          tone={sharpeAccent}
          sub={
            sharpeHi !== sharpeLo
              ? `[${sharpeLo.toFixed(2)}, ${sharpeHi.toFixed(2)}] PSR ${psr.toFixed(2)}`
              : luckyMax > 0
                ? `PSR ${psr.toFixed(2)} · max ${luckyMax.toFixed(2)}`
                : `PSR ${psr.toFixed(2)}`
          }
        />
        <TmKpi
          label="IC"
          value={m.ic_spearman.toFixed(4)}
          tone={icCiSpansZero ? "neg" : icAccent}
          sub={
            icHi !== icLo
              ? `[${icLo.toFixed(3)}, ${icHi.toFixed(3)}] p=${icP < 0.001 ? "<0.001" : icP.toFixed(3)}`
              : `ICIR ${icir.toFixed(2)} p=${icP < 0.001 ? "<0.001" : icP.toFixed(3)}`
          }
        />
        <TmKpi
          label={t(locale, "backtest.kpi.maxDD")}
          value={`${(dd * 100).toFixed(1)}%`}
          tone="neg"
        />
        <TmKpi
          label={t(locale, "backtest.kpi.turnover")}
          value={turnover.toFixed(3)}
          sub={t(locale, "backtest.kpi.turnoverHint")}
        />
        <TmKpi
          label={t(locale, "backtest.kpi.hitRate")}
          value={`${(hitRate * 100).toFixed(0)}%`}
          tone={hitRate > 0.5 ? "pos" : "neg"}
        />
      </TmKpiGrid>
    </TmPane>
  );
}
