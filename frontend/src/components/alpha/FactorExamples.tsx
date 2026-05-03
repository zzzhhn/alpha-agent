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

// Top 6 long-only factor picks from the SP500 v3 selection workflow
// (scripts/select_long_only_factors.py). 22 academic-classic candidates ×
// 4 mode variants (plain/sector-neutral × top30%/top10%) → ranked by
// composite score (alpha-t × PSR × cross-mode stability).
//
// HONEST DISCLAIMER: on the SP500 v3 panel (3y, 555 tickers, 2023-05 →
// 2026-04), no long-only factor on cap-weighted SPY benchmark clears the
// rigorous α-t > 1.0 threshold. The strongest pick (`ep`, top 10%) reaches
// α-t = +0.99. Cause: 2024-2026 was a Mag-7-concentrated bull market; SPY
// effectively IS the mega-cap basket, so any equal-weight basket lags.
//
// Per-regime breakdown shows the universal pattern: sideways α-t > 0,
// bull α-t < 0. Long-only factors are a sideways/bear regime tool. For
// rigorous alpha generation, use long_short with sector-neutral instead
// (e.g. zs_vol_20 → α-t = +2.20, p = 0.028 in long_short SN mode).
export const FACTOR_EXAMPLES: readonly FactorExample[] = [
  {
    name: "Earnings Yield (top 10%)",
    hypothesisZh: "高盈利收益率（净利润 / 市值）公司在 SP500 中长期跑赢——经典 Basu 1977 价值因子",
    hypothesisEn: "High earnings yield (net income / market cap) outperforms in SP500 — classic Basu 1977 value factor",
    expression: "rank(divide(net_income_adjusted, multiply(close, shares_outstanding)))",
    totalReturn: 0.066,
    testSharpe: 1.76,
    testIC: 0.012,
    intuitionZh:
      "6 个 long_only 因子里 α-t 最强（+0.99，~p<0.10）。集中持有 top 10%（top 55 股），SPY excess +6.6%/年，PSR=0.91。Regime 分解：bull α-t=+0.20，sideways α-t=+0.96——两个 regime 都正向，难得。这是唯一在 bull 期也没显著输 SPY 的因子。",
    intuitionEn:
      "Strongest α-t (+0.99, ~p<0.10) of the 6 long-only picks. Concentrated top 10% (top 55 stocks), SPY excess +6.6%/yr, PSR=0.91. Regime breakdown: bull α-t=+0.20, sideways α-t=+0.96 — positive in both, rare. The only pick that doesn't visibly underperform SPY in bull regime.",
  },
  {
    name: "120d Trend Sharpe (top 30%)",
    hypothesisZh: "120 日 return/vol 比率——风险调整后的趋势强度，类似 Sharpe ratio 在每只股票上的局部计算",
    hypothesisEn: "120d return / vol ratio — risk-adjusted trend strength, Sharpe-like per-stock metric",
    expression: "rank(divide(ts_mean(returns, 120), ts_std(returns, 120)))",
    totalReturn: 0.009,
    testSharpe: 1.79,
    testIC: 0.008,
    intuitionZh:
      "排序按「已实现 Sharpe」，挑出趋势平稳上行的股票。α-t=+0.21（不显著），但 PSR=0.91 说明 SR 高度稳定。3/4 模式变体都正——结构稳定的因子。在牛市集中度高的 2024-25 区间被 SPY 反超。",
    intuitionEn:
      "Ranks by realized Sharpe — picks stocks with steady upward trends. α-t=+0.21 (not significant), but PSR=0.91 indicates highly stable SR. 3/4 mode variants positive — structurally robust. Loses to SPY in 2024-25 mega-cap-concentrated bull.",
  },
  {
    name: "Low Vol 120d (top 10% sector-neut)",
    hypothesisZh: "低波动率异象（Frazzini-Pedersen）——低 β 股票长期跑赢高 β，行业中性化后强化",
    hypothesisEn: "Low-volatility anomaly (Frazzini-Pedersen) — low-β stocks outperform; sector-neutralized to remove sector tilt",
    expression: "rank(inverse(ts_std(returns, 120)))",
    totalReturn: 0.038,
    testSharpe: 1.16,
    testIC: 0.013,
    intuitionZh:
      "Top 10% 集中持有最低波动股，sector-neutralize 剔除「避险行业（公用事业、必需消费）」的隐性 beta。α-t=+0.70。Sideways α-t=+1.29 是亮点——震荡期最稳。bull 期 α-t=-0.55 印证教科书结论：低波在牛市跑输。",
    intuitionEn:
      "Top 10% concentrated low-vol; sector-neutral strips defensive-sector (utilities, staples) implicit beta. α-t=+0.70. Sideways α-t=+1.29 is the standout — most stable in chop. Bull α-t=-0.55 confirms textbook: low-vol underperforms in bull.",
  },
  {
    name: "Low Vol 60d (top 10% sector-neut)",
    hypothesisZh: "低波动 120d 的短期版（60 日）——更敏感但更易翻车",
    hypothesisEn: "60d version of low-vol — more responsive but noisier than 120d",
    expression: "rank(inverse(ts_std(returns, 60)))",
    totalReturn: 0.011,
    testSharpe: 1.00,
    testIC: 0.005,
    intuitionZh:
      "和 low_vol_120 同源，60 日窗口对最近波动更敏感。α-t=+0.20（弱信号）。在 sideways 期 α-t=+0.78，bull α-t=-0.88。组合里它和 low_vol_120 高度相关——别同时选两个 vol 因子做组合。",
    intuitionEn:
      "60d version of low-vol family. α-t=+0.20 (weak). Sideways α-t=+0.78, bull α-t=-0.88. Highly correlated with low_vol_120 — don't combine both in a portfolio.",
  },
  {
    name: "Volume Z-Score 20d (top 10%)",
    hypothesisZh: "20 日成交量 z-score 排名——异常活跃度信号，小盘股一旦放量短期表现强",
    hypothesisEn: "20d volume z-score rank — abnormal-volume signal; small-caps often outperform short-term after volume spikes",
    expression: "ts_zscore(volume, 20)",
    totalReturn: 0.006,
    testSharpe: 2.17,
    testIC: 0.015,
    intuitionZh:
      "[Tier C]——4 个变体里只 1 个 α-t 正，模式脆弱。但同一表达式在 long_short sector-neutral 模式下 α-t=+2.20（p=0.028）显著。提醒：因子在 long_short 比 long_only 强得多，因为它本质是「价差信号」而非「绝对收益信号」。",
    intuitionEn:
      "[Tier C] — only 1/4 mode variants positive, mode-fragile. But the SAME expression in long_short sector-neutral mode hits α-t=+2.20 (p=0.028). Lesson: factor is fundamentally a SPREAD signal, not an absolute-return signal — it shines in long_short, not long_only.",
  },
  {
    name: "Book Yield B/P (top 10%)",
    hypothesisZh: "经典 Fama-French 价值因子——book-to-market 比率高的股票长期跑赢",
    hypothesisEn: "Classic Fama-French B/M value factor — high book-to-market stocks outperform long-term",
    expression: "rank(divide(equity, multiply(close, shares_outstanding)))",
    totalReturn: 0.003,
    testSharpe: 1.51,
    testIC: 0.001,
    intuitionZh:
      "[Tier C]。α-t=+0.04 实质上是噪声，但 PSR=0.88 说明绝对 SR 不差。教科书 value 因子在 2024-2026 大型科技股牛市里失效——growth 跑赢 value 的「价值陷阱十年」延续。仅作组合多样性纳入。",
    intuitionEn:
      "[Tier C]. α-t=+0.04 is essentially noise but PSR=0.88. The textbook value factor has been crushed in the 2024-2026 mega-cap-tech bull market — the 'value trap decade' continues. Included for portfolio diversity, not signal strength.",
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
        <h2 className="text-base font-semibold text-text">
          {t(locale, "alpha.examples.title")}
        </h2>
        <p className="mt-1 text-[13px] leading-relaxed text-muted">
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
        <h3 className="text-sm font-semibold text-text">{example.name}</h3>
        <span className="rounded bg-accent/10 px-2 py-0.5 font-mono text-[12px] text-accent">
          {example.totalReturn >= 0 ? "+" : ""}{(example.totalReturn * 100).toFixed(1)}%
        </span>
      </div>
      <p className="text-[13px] leading-relaxed text-text/90">{hypothesis}</p>
      <code className="block overflow-x-auto rounded bg-[var(--toggle-bg)] px-2 py-1 font-mono text-[12px] text-muted">
        {example.expression}
      </code>
      <p className="text-[12px] leading-relaxed text-muted">{intuition}</p>
      <div className="mt-1 flex items-center justify-between gap-2 border-t border-border pt-2">
        <div className="flex gap-3 text-[12px]">
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
