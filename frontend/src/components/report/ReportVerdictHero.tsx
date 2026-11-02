"use client";

import { useLocale } from "@/components/layout/LocaleProvider";
import { classifyFactorTier } from "@/lib/factor-tier";
import type { FactorBacktestResponse } from "@/lib/types";

interface HeroFactor {
  readonly name: string;
  readonly expression: string;
  readonly backtest: FactorBacktestResponse;
}

function fmt(value: number | null | undefined, digits: number, signed = false): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return (signed && value >= 0 ? "+" : "") + value.toFixed(digits);
}

/** Only the completed run supplies a verdict. Source fixtures never populate this strip. */
export function ReportVerdictHero({ primary, running }: { readonly primary: HeroFactor | null; readonly running: boolean }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  if (!primary) return null;
  const bt = primary.backtest;
  const overfit = bt.overfit_flag || (bt.oos_decay != null && Number.isFinite(bt.oos_decay) && bt.oos_decay > 0.5);
  const tier = classifyFactorTier(bt.alpha_pvalue, bt.beta_market);
  const labels: Record<string, string> = { "PURE ALPHA": "低市场暴露 Alpha", "LEVERED ALPHA": "带市场暴露 Alpha", "MARGINAL": "边际证据", "NOISE": "未见显著 Alpha", "UNKNOWN": "证据不足" };
  const verdict = overfit ? (zh ? "过拟合风险" : "Overfit risk") : zh ? (labels[tier.label] ?? "证据不足") : tier.label;
  const tone = overfit || tier.label === "NOISE" ? "text-tm-neg" : tier.label === "MARGINAL" ? "text-tm-warn" : tier.label === "PURE ALPHA" || tier.label === "LEVERED ALPHA" ? "text-tm-pos" : "text-tm-muted";
  const reading = overfit ? (zh ? "样本外表现衰减，需复核后再作判断。" : "Out-of-sample performance decayed. Review before drawing a conclusion.") : tier.label === "NOISE" ? (zh ? "本次样本内未达到 Alpha 显著性门槛，收益不等于有效证据。" : "Alpha is not significant in this sample. A positive return alone is not sufficient evidence.") : tier.label === "MARGINAL" ? (zh ? "统计证据偏弱，结合回撤、成本和样本范围复核。" : "Statistical evidence is marginal. Review drawdown, costs and sample scope.") : tier.label === "PURE ALPHA" || tier.label === "LEVERED ALPHA" ? (zh ? "通过本次 Alpha 显著性检查，不代表未来收益或可直接交易。" : "Passes this run’s alpha significance check, not a forecast or trading approval.") : (zh ? "风险归因数据不足，暂不作有效性判断。" : "Insufficient risk-attribution evidence for an effectiveness verdict.");
  return (
    <section className="grid min-w-0 gap-4 border-l-[3px] border-l-tm-rule-2 bg-tm-bg-2/40 px-4 py-4 xl:grid-cols-[minmax(0,1fr)_auto]" aria-label={zh ? "本次报告结论" : "Current report verdict"}>
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="font-tm-mono text-xs text-tm-muted">{zh ? "本次结论" : "Run verdict"}</span>
          <h2 className={"font-tm-serif text-[18px] " + tone}>{verdict}</h2>
          {running && <span className="font-tm-mono text-xs text-tm-warn">{zh ? "上次完成的报告" : "Previous completed report"}</span>}
        </div>
        <p className="mt-1 text-xs leading-5 text-tm-fg-2">{reading}</p>
      </div>
      <dl className="flex flex-wrap items-center gap-x-6 gap-y-2 font-tm-mono text-xs">
        {[{ label: zh ? "样本外夏普" : "OOS Sharpe", value: fmt(bt.test_metrics?.sharpe, 2, true) }, { label: zh ? "Alpha p 值" : "Alpha p-value", value: fmt(bt.alpha_pvalue, 3) }, { label: zh ? "市场 Beta" : "Market beta", value: fmt(bt.beta_market, 2, true) }].map(({ label, value }) => <div key={label}><dt className="text-tm-muted">{label}</dt><dd className="mt-1 text-base tabular-nums text-tm-fg">{value}</dd></div>)}
      </dl>
    </section>
  );
}
