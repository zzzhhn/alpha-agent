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

// All six factors empirically verified in long_only mode on the live SP100 v2
// panel (99 tickers + SPY, 2025-04-25 → 2026-04-24, SPY test split +31.14%).
// Selected from a 21-candidate sweep covering quality / value / momentum /
// sector-neutral / smoothed / combo themes. Re-run the sweep if the panel
// schema or universe composition changes.
export const FACTOR_EXAMPLES: readonly FactorExample[] = [
  {
    name: "Hump 平滑动量",
    hypothesisZh: "12 日动量套上 3% 阈值平滑器，过滤每日排名的微小变动",
    hypothesisEn: "12-day momentum gated by a 3% relative-change smoother to suppress micro-rebalances",
    expression: "hump(rank(ts_mean(returns, 12)), 0.03)",
    totalReturn: 0.3835,
    testSharpe: 2.97,
    testIC: 0.046,
    intuitionZh:
      "hump 算子让排名只在变化超过 3% 时更新，把噪声驱动的换手清理掉。Sharpe 与原始 mom_12 (+3.04) 持平，扣手续费后保留的 alpha 显著更多。这是 T3 实装算子的典型用法。",
    intuitionEn:
      "hump only refreshes rank when the change exceeds 3%, eliminating noise-driven turnover. Sharpe matches raw mom_12 (+3.04); post-cost alpha retention is materially higher. Canonical usage of a T3-promoted operator.",
  },
  {
    name: "资产周转率 (Asset Turnover)",
    hypothesisZh: "高资产周转率的公司单位资产产出更多收入，资本效率更高",
    hypothesisEn: "Companies with higher asset turnover generate more revenue per dollar of assets — capital-efficient operators",
    expression: "rank(div(revenue, assets))",
    totalReturn: 0.4232,
    testSharpe: 2.11,
    testIC: 0.026,
    intuitionZh:
      "经典 quality 因子。营收/总资产衡量管理层把账面资产变成现金流的能力。在 SP100 上跑赢 SPY 11pp、IC 显著正——demo 时强调 T2 fundamental 字段的可用性。",
    intuitionEn:
      "Classic quality factor. Revenue / total assets measures management's ability to convert balance-sheet assets into cash flow. Beats SPY by 11pp on SP100 with significantly positive IC — showcases T2 fundamental fields in action.",
  },
  {
    name: "营业利润 × 动量",
    hypothesisZh: "高营业利润率 × 强近期动量的双信号乘积",
    hypothesisEn: "Operating margin × recent momentum — companies that are both profitable and trending",
    expression: "rank(mul(div(operating_income, revenue), ts_mean(returns, 12)))",
    totalReturn: 0.3327,
    testSharpe: 1.96,
    testIC: 0.031,
    intuitionZh:
      "学术 Quality + Momentum 因子的轻量版。乘积要求两个独立信号同时为正，过滤掉「价差大但低利润」和「高利润但停滞」两类伪 alpha。混合因子的设计示范。",
    intuitionEn:
      "Lightweight version of the academic Quality + Momentum factor. The product requires both signals positive, filtering out 'wide spread / low margin' and 'high margin / stagnant' false positives. Demo of multi-source factor design.",
  },
  {
    name: "线性衰减动量",
    hypothesisZh: "10 日动量但近期收益权重更高，比等权 ts_mean 更敏感",
    hypothesisEn: "10-day momentum with linearly increasing weights — recent returns count more",
    expression: "rank(ts_decay_linear(returns, 10))",
    totalReturn: 0.3970,
    testSharpe: 1.63,
    testIC: 0.031,
    intuitionZh:
      "权重 [1,2,…,10] 让最近 1-2 天权重各占 ~20%。比 ts_mean 等权更早捕捉趋势反转，代价是被噪声打断的概率上升。展示 ts_decay_linear T1 算子。",
    intuitionEn:
      "Weights [1..10] give the last 1-2 days ~20% each. Catches trend reversals earlier than equal-weighted ts_mean, at the cost of more whipsaw exposure. Showcases the ts_decay_linear T1 operator.",
  },
  {
    name: "行业中性 ROA",
    hypothesisZh: "在每个 sector 内部找最高 ROA 的公司，剥离 sector beta",
    hypothesisEn: "Highest-ROA stocks within each sector, with sector beta removed",
    expression: "group_neutralize(rank(div(operating_income, assets)), sector)",
    totalReturn: 0.3927,
    testSharpe: 1.18,
    testIC: 0.020,
    intuitionZh:
      "Tech 公司天然 ROA 比 Energy 高，直接横截面比对会变成对 Tech sector 的隐性赌注。group_neutralize 把信号收敛到行业内相对效率，sector 配置归零。这是 T2 group 算子的核心用法。",
    intuitionEn:
      "Tech's ROA is structurally higher than Energy's; cross-sectional ranking alone becomes an implicit Tech bet. group_neutralize collapses the signal to within-sector efficiency, zeroing sector exposure. Core usage of the T2 group operator family.",
  },
  {
    name: "ROA (经营资产收益率)",
    hypothesisZh: "经营利润相对总资产的比率——最简洁的 quality 因子",
    hypothesisEn: "Operating income as a fraction of total assets — the simplest quality factor",
    expression: "rank(div(operating_income, assets))",
    totalReturn: 0.4068,
    testSharpe: 1.27,
    testIC: 0.006,
    intuitionZh:
      "纯 fundamental 因子，无动量、无估值叠加。+40.7% 收益跑赢 SPY 9pp，体现 quality 在 2025-2026 区间的持续性。IC 偏低是因为月度财报与日度收益错配，但累计收益依然显著。",
    intuitionEn:
      "Pure fundamental factor with no momentum or valuation overlay. +40.7% return beats SPY by 9pp, demonstrating quality's persistence in 2025-2026. IC is low because quarterly fundamentals lag daily returns, but cumulative outperformance is substantial.",
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
          +{(example.totalReturn * 100).toFixed(1)}%
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
