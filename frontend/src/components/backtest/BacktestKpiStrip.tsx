"use client";

import { Card } from "@/components/ui/Card";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { FactorBacktestResponse } from "@/lib/types";

interface BacktestKpiStripProps {
  readonly result: FactorBacktestResponse;
}

export function BacktestKpiStrip({ result }: BacktestKpiStripProps) {
  const { locale } = useLocale();
  const m = result.test_metrics;
  const eq = result.equity_curve;
  const bm = result.benchmark_curve;
  // Total return on the FULL equity curve (test_metrics.total_return is on
  // the test slice only — usually different and shorter window).
  const fullRet = eq.length > 0 ? eq[eq.length - 1].value / eq[0].value - 1 : 0;
  const benchRet = bm.length > 0 ? bm[bm.length - 1].value / bm[0].value - 1 : 0;
  const dd = m.max_drawdown ?? 0;
  const turnover = m.turnover ?? 0;
  const hitRate = m.hit_rate ?? 0;
  // T1.4 v4 — IC significance. p<0.05 = "real signal"; p>0.5 = noise.
  // Honest verdict beats a green Sharpe number every time.
  const icir = m.icir ?? 0;
  const icP = m.ic_pvalue ?? 1;
  const icAccent: "green" | "red" | undefined =
    icP < 0.05 && m.ic_spearman > 0 ? "green" : icP > 0.5 ? "red" : undefined;
  // T2.1 v4 — Bailey-LdP deflated Sharpe. PSR > 0.95 ≈ Sharpe convincingly
  // beats the multiple-testing null; PSR < 0.5 ≈ realized SR is below the
  // lucky-max-of-N-trials baseline.
  const psr = m.psr ?? 0.5;
  const luckyMax = m.lucky_max_sr ?? 0;
  const sharpeAccent: "green" | "red" | undefined =
    psr >= 0.95 ? "green" : psr < 0.5 ? "red"
    : m.sharpe >= 1.0 ? "green" : m.sharpe < 0 ? "red" : undefined;

  return (
    <Card padding="md">
      <header className="mb-3">
        <h2 className="text-base font-semibold text-text">
          {t(locale, "backtest.kpi.title")}
        </h2>
        <p className="mt-0.5 text-[12px] text-muted">
          {t(locale, "backtest.kpi.subtitle")
            .replace("{ret}", `${(fullRet * 100).toFixed(1)}%`)
            .replace("{bench}", `${(benchRet * 100).toFixed(1)}%`)}
        </p>
        {result.overfit_flag && (
          <p className="mt-2 rounded-md border border-red/40 bg-red/10 px-2 py-1 text-[12px] text-red">
            {t(locale, "backtest.kpi.overfitWarning")
              .replace("{decay}", `${((result.oos_decay ?? 0) * 100).toFixed(0)}%`)}
          </p>
        )}
      </header>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <Kpi
          label={t(locale, "backtest.kpi.totalReturn")}
          value={`${(fullRet * 100).toFixed(1)}%`}
          accent={fullRet > benchRet ? "green" : "red"}
          hint={`${t(locale, "backtest.kpi.vsBench")}: ${(benchRet * 100).toFixed(1)}%`}
        />
        <Kpi
          label={t(locale, "backtest.kpi.testSharpe")}
          value={m.sharpe.toFixed(2)}
          accent={sharpeAccent}
          hint={
            luckyMax > 0
              ? `PSR ${psr.toFixed(2)} · luckyMax ${luckyMax.toFixed(2)}`
              : `PSR ${psr.toFixed(2)}`
          }
        />
        <Kpi
          label="IC"
          value={m.ic_spearman.toFixed(4)}
          accent={icAccent}
          hint={`ICIR ${icir.toFixed(2)} · p=${icP < 0.001 ? "<0.001" : icP.toFixed(3)}`}
        />
        <Kpi
          label={t(locale, "backtest.kpi.maxDD")}
          value={`${(dd * 100).toFixed(1)}%`}
          accent="red"
        />
        <Kpi
          label={t(locale, "backtest.kpi.turnover")}
          value={turnover.toFixed(3)}
          hint={t(locale, "backtest.kpi.turnoverHint")}
        />
        <Kpi
          label={t(locale, "backtest.kpi.hitRate")}
          value={`${(hitRate * 100).toFixed(0)}%`}
          accent={hitRate > 0.5 ? "green" : "red"}
        />
      </div>
    </Card>
  );
}

function Kpi({
  label, value, accent, hint,
}: {
  label: string;
  value: string;
  accent?: "green" | "red";
  hint?: string;
}) {
  const color = accent === "green" ? "text-green" : accent === "red" ? "text-red" : "text-text";
  return (
    <div>
      <div className="text-[12px] uppercase tracking-wide text-muted">{label}</div>
      <div className={`mt-0.5 font-mono text-lg font-semibold ${color}`}>{value}</div>
      {hint && <div className="mt-0.5 text-[12px] text-muted">{hint}</div>}
    </div>
  );
}
