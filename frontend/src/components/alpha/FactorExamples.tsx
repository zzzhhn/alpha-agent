"use client";

import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";

export interface FactorExample {
  readonly name: string;
  readonly hypothesisZh: string;
  readonly hypothesisEn: string;
  readonly expression: string;
  readonly totalReturn: number;   // decimal, e.g. 0.5326 for +53.26%
  readonly testSharpe: number;
  readonly testIC: number;
  readonly intuitionZh: string;
  readonly intuitionEn: string;
}

// All five have been empirically re-verified in long_only mode on the live
// SP100 v2 panel (100 tickers, 2025-04-25 → 2026-04-24, SPY test +31.14%).
// Re-run scripts/verify_factor_examples.py if the panel schema changes.
export const FACTOR_EXAMPLES: readonly FactorExample[] = [
  {
    name: "12 日动量",
    hypothesisZh: "过去两周累计收益最高的股票倾向于持续上涨",
    hypothesisEn: "Stocks with highest 2-week cumulative return tend to keep rising",
    expression: "rank(ts_mean(returns, 12))",
    totalReturn: 0.3798,
    testSharpe: 3.04,
    testIC: 0.045,
    intuitionZh:
      "经典趋势跟随。12 日窗口在短期噪音和中期趋势之间取平衡，适合捕捉 sector rotation。",
    intuitionEn:
      "Classic trend-following. 12-day window balances short-term noise vs medium trend — good for sector rotation capture.",
  },
  {
    name: "VWAP 追涨因子",
    hypothesisZh: "收盘价相对 VWAP 偏高的股票，当日买盘推动力强",
    hypothesisEn: "When close is high vs VWAP, intraday buy pressure pushes the price up",
    expression: "rank(div(close, vwap))",
    totalReturn: 0.3665,
    testSharpe: 0.93,
    testIC: 0.020,
    intuitionZh:
      "close / vwap > 1 意味着日内交易加权后买盘占优。在 SP100 上 Sharpe 较低，但累计收益仍跑赢 SPY。",
    intuitionEn:
      "close/vwap > 1 means volume-weighted buying dominated. Lower Sharpe on SP100 but cumulative return still beats SPY.",
  },
  {
    name: "10 日 VWAP 偏离率",
    hypothesisZh: "相对 10 日 VWAP 均值偏离越大，说明资金推动越强",
    hypothesisEn: "The larger the deviation from 10-day VWAP mean, the stronger the capital flow",
    expression:
      "rank(div(sub(close, ts_mean(vwap, 10)), ts_mean(vwap, 10)))",
    totalReturn: 0.3301,
    testSharpe: 1.14,
    testIC: 0.025,
    intuitionZh:
      "把 VWAP 拉长到 10 日均值后，捕捉的是中期资金沉淀而非日内噪音。",
    intuitionEn:
      "A 10-day VWAP mean smooths out intraday noise and captures medium-term capital positioning.",
  },
  {
    name: "7 日短期动量",
    hypothesisZh: "一周累计收益最高的股票延续走强",
    hypothesisEn: "Stocks with highest 1-week cumulative return keep their momentum",
    expression: "rank(ts_mean(returns, 7))",
    totalReturn: 0.3321,
    testSharpe: 1.58,
    testIC: 0.029,
    intuitionZh:
      "7 日窗口比 12 日更激进——捕捉短期 news catalyst 带动的 momentum，换手会更高。",
    intuitionEn:
      "7-day is more aggressive than 12-day — captures momentum driven by short-term news catalysts, with higher turnover.",
  },
  {
    name: "VWAP × 动量组合",
    hypothesisZh: "资金推动 + 趋势确认双重信号叠加",
    hypothesisEn: "Capital flow × trend confirmation stacked signal",
    expression: "rank(mul(div(close, vwap), ts_mean(returns, 10)))",
    totalReturn: 0.3717,
    testSharpe: 1.99,
    testIC: 0.036,
    intuitionZh:
      "两个独立信号的乘积——需要 VWAP 偏离和动量同向才触发。降低 false positive 率。",
    intuitionEn:
      "Product of two independent signals — fires only when VWAP-skew and momentum align. Cuts false positives.",
  },
];

interface FactorExamplesProps {
  readonly onLoad: (example: FactorExample) => void;
}

export function FactorExamples({ onLoad }: FactorExamplesProps) {
  const { locale } = useLocale();
  return (
    <Card padding="md">
      <header className="mb-3">
        <h2 className="text-sm font-semibold text-text">
          {t(locale, "alpha.examples.title")}
        </h2>
        <p className="mt-1 text-[11px] leading-relaxed text-muted">
          {t(locale, "alpha.examples.subtitle")}
        </p>
      </header>
      <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
        {FACTOR_EXAMPLES.map((ex) => (
          <ExampleCard key={ex.name} example={ex} onLoad={onLoad} />
        ))}
      </div>
    </Card>
  );
}

function ExampleCard({
  example,
  onLoad,
}: {
  readonly example: FactorExample;
  readonly onLoad: (e: FactorExample) => void;
}) {
  const { locale } = useLocale();
  const hypothesis = locale === "zh" ? example.hypothesisZh : example.hypothesisEn;
  const intuition = locale === "zh" ? example.intuitionZh : example.intuitionEn;
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border bg-[var(--card-inner,transparent)] p-3">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-xs font-semibold text-text">{example.name}</h3>
        <span className="rounded bg-accent/10 px-2 py-0.5 font-mono text-[10px] text-accent">
          +{(example.totalReturn * 100).toFixed(1)}%
        </span>
      </div>
      <p className="text-[11px] leading-relaxed text-text/90">{hypothesis}</p>
      <code className="block overflow-x-auto rounded bg-[var(--toggle-bg)] px-2 py-1 font-mono text-[10px] text-muted">
        {example.expression}
      </code>
      <p className="text-[10px] leading-relaxed text-muted">{intuition}</p>
      <div className="mt-1 flex items-center justify-between gap-2 border-t border-border pt-2">
        <div className="flex gap-3 text-[10px]">
          <span className="text-muted">
            {t(locale, "alpha.examples.sharpeLabel")}:{" "}
            <span className="font-mono text-text">{example.testSharpe.toFixed(2)}</span>
          </span>
          <span className="text-muted">
            IC:{" "}
            <span className="font-mono text-text">{example.testIC.toFixed(3)}</span>
          </span>
        </div>
        <Button variant="ghost" size="sm" onClick={() => onLoad(example)}>
          {t(locale, "alpha.examples.useBtn")}
        </Button>
      </div>
    </div>
  );
}
