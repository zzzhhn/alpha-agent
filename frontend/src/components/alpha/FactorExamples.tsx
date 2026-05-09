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
  readonly totalReturn: number;
  readonly testSharpe: number;
  readonly testIC: number;
  readonly intuitionZh: string;
  readonly intuitionEn: string;
  // v3 cross-page parity: each example carries the EXACT config under
  // which it was discovered/validated. /backtest's loadExample now also
  // applies this config to the form so the user reproduces the proven
  // verdict (Pure Alpha / Levered Alpha) from RISK.ATTRIBUTION rather
  // than running with default config and getting a different result.
  // All optional for back-compat; missing fields fall back to platform
  // defaults at the form layer.
  readonly direction?: "long_short" | "long_only" | "short_only";
  readonly neutralize?: "none" | "sector";
  readonly benchmarkTicker?: "SPY" | "RSP";
  readonly topPct?: number;       // decimal, e.g. 0.30
  readonly bottomPct?: number;    // decimal
  readonly transactionCostBps?: number;
}

// Top 6 long_short factor picks from SP500 v3 selection workflow
// (scripts/select_long_only_factors.py --direction long_short --alpha-t 1.0).
//
// All 6 passed full 4-stage filter: α-t > 1.0, PSR > 0.65, ≥2 of 4 mode
// variants positive, at least one regime with positive α-t. Top 3 (ep,
// vol_zscore_20, dvol_zscore_60) clear the rigorous α-t > 1.5 + p < 0.10
// threshold. Family diversity enforced: max 2 picks per category.
//
// CONTEXT: long_short means top-30% long basket netted against bottom-30%
// short basket. Returns are market-neutral — strategy SR / α/β are
// independent of SPY's path. This is why these factors look strong while
// the same expressions in long_only mode underperform cap-weighted SPY.
export const FACTOR_EXAMPLES: readonly FactorExample[] = [
  {
    name: "Earnings Yield (E/P)",
    hypothesisZh: "高盈利收益率（净利润/市值）股 long、低 EY 股 short——经典 Basu 1977 价值因子的多空版",
    hypothesisEn: "Long high earnings yield (net income / market cap), short low — long_short version of Basu 1977 value",
    expression: "rank(divide(net_income_adjusted, multiply(close, shares_outstanding)))",
    totalReturn: 0.066,
    testSharpe: 1.85,
    testIC: 0.030,
    direction: "long_short",
    neutralize: "none",
    benchmarkTicker: "SPY",
    topPct: 0.30,
    bottomPct: 0.30,
    intuitionZh:
      "6 个 picks 中 α-t 最强（+2.73, p=0.006）。Bull α-t=+1.08, sideways α-t=+1.58——两个 regime 都显著。4/4 模式变体正向，PSR=0.93。学术 Basu 价值因子在 long_short 上至今仍 work，证明 cap-weighted bull 稀释的不是因子本身而是 long_only 的结构。",
    intuitionEn:
      "Strongest pick: α-t=+2.73, p=0.006. Bull α-t=+1.08, sideways α-t=+1.58 — significant in BOTH regimes. 4/4 mode variants positive, PSR=0.93. Basu value factor still works in long_short — confirming that cap-weighted bull dilutes long_only structure, not the factor itself.",
  },
  {
    name: "Volume Z-Score 20d",
    hypothesisZh: "20 日成交量 z-score——异常活跃度信号，sector-neutral 模式下剥离行业 rotation 噪声",
    hypothesisEn: "20-day volume z-score — abnormal-trading signal; sector-neutral strips sector-rotation noise",
    expression: "ts_zscore(volume, 20)",
    totalReturn: 0.038,
    testSharpe: 3.85,
    testIC: 0.015,
    direction: "long_short",
    neutralize: "sector",
    benchmarkTicker: "SPY",
    topPct: 0.30,
    bottomPct: 0.30,
    intuitionZh:
      "α-t=+2.20 (p=0.028)。Sector-neutral top-30% 模式下 SR=+3.85（很高），bull α-t=+1.59, sideways α-t=+2.09——bull 期都显著。这是 alpha-agent 引擎首个跨过 p<0.05 的因子。「不寻常的成交量先于价格」的微观市场行为信号。",
    intuitionEn:
      "α-t=+2.20 (p=0.028). Sector-neutral top-30% mode delivers SR=+3.85. Bull α-t=+1.59, sideways α-t=+2.09 — significant even in bull. First factor on alpha-agent to clear p<0.05. Microstructure: 'unusual volume precedes price'.",
  },
  {
    name: "Dollar Volume Z-Score 60d",
    hypothesisZh: "60 日美元成交量 z-score——比裸成交量更准的市场关注度指标",
    hypothesisEn: "60-day dollar volume z-score — better attention proxy than raw volume since it weights by price",
    expression: "ts_zscore(dollar_volume, 60)",
    totalReturn: 0.069,
    testSharpe: 3.29,
    testIC: 0.020,
    direction: "long_short",
    neutralize: "none",
    benchmarkTicker: "SPY",
    topPct: 0.30,
    bottomPct: 0.30,
    intuitionZh:
      "α-t=+1.88 (p=0.060) 边缘显著。Plain top-30% 模式下 PSR=1.00 (deflated SR 完全跑赢 lucky max)。Bull α-t=+0.62 略弱，sideways α-t=+2.33 极强。和 vol_zscore_20 高度相关，组合不要同时用两个。",
    intuitionEn:
      "α-t=+1.88 (p=0.060), borderline significant. Plain top-30% mode: PSR=1.00 (deflated SR fully clears lucky-max threshold). Bull α-t=+0.62 weaker, sideways α-t=+2.33 very strong. Correlates with vol_zscore_20 — don't combine both.",
  },
  {
    name: "60d Trend Sharpe",
    hypothesisZh: "60 日 return/vol 比率——风险调整后的趋势强度，long 高 Sharpe 股、short 低 Sharpe 股",
    hypothesisEn: "60d return/vol ratio — risk-adjusted trend strength; long high-Sharpe, short low-Sharpe",
    expression: "rank(divide(ts_mean(returns, 60), ts_std(returns, 60)))",
    totalReturn: 0.030,
    testSharpe: 1.57,
    testIC: 0.010,
    direction: "long_short",
    neutralize: "sector",
    benchmarkTicker: "SPY",
    topPct: 0.30,
    bottomPct: 0.30,
    intuitionZh:
      "α-t=+1.23 (p=0.22)，4/4 模式变体正向。Bull α-t=-0.27 略负，sideways α-t=+1.30 强——典型 momentum 信号在震荡里赚钱、牛市跟不上 mega-cap 的特征。Sector-neutral 模式表现最佳。",
    intuitionEn:
      "α-t=+1.23 (p=0.22), 4/4 mode variants positive. Bull α-t=-0.27 weak, sideways α-t=+1.30 strong — classic momentum: works in chop, lags in mega-cap-led bull. Best in sector-neutral mode.",
  },
  {
    name: "Book Yield (B/P)",
    hypothesisZh: "经典 Fama-French 价值因子，long 高 B/M、short 低 B/M",
    hypothesisEn: "Classic Fama-French B/M value — long high book-to-market, short low",
    expression: "rank(divide(equity, multiply(close, shares_outstanding)))",
    totalReturn: 0.030,
    testSharpe: 1.76,
    testIC: 0.005,
    direction: "long_short",
    neutralize: "none",
    benchmarkTicker: "SPY",
    topPct: 0.30,
    bottomPct: 0.30,
    intuitionZh:
      "α-t=+1.09 (p=0.28)。Bull α-t=+0.82, sideways α-t=+1.49——两个 regime 都正。Plain top-30% 模式 PSR=0.92。B/P 在 long_only 跑输 SPY 严重，但 long_short 把 growth 高估部分 short 掉就翻身了。",
    intuitionEn:
      "α-t=+1.09 (p=0.28). Bull α-t=+0.82, sideways α-t=+1.49 — positive in both. Plain top-30% mode PSR=0.92. B/P long-only crushed by SPY, but long_short extracts the spread by shorting overpriced growth.",
  },
  {
    name: "Cash Buffer (Cash/Equity)",
    hypothesisZh: "现金缓冲比例（cash/equity）——high cash 公司财务韧性更强，sector-neutral 后凸显",
    hypothesisEn: "Cash buffer (cash/equity) — high-cash firms more resilient; sector-neutral reveals the signal",
    expression: "rank(divide(cash_and_equivalents, equity))",
    totalReturn: 0.018,
    testSharpe: 0.63,
    testIC: 0.008,
    direction: "long_short",
    neutralize: "sector",
    benchmarkTicker: "SPY",
    topPct: 0.30,
    bottomPct: 0.30,
    intuitionZh:
      "α-t=+1.39 (p=0.16)。Bull α-t=+0.95, sideways α-t=-0.20——和其他几个相反，bull 比 sideways 强。SR 偏低 (+0.63) 但 α-t 不低，说明 alpha 是市场中性提取的。Sector-neutral top-30% 模式最佳。",
    intuitionEn:
      "α-t=+1.39 (p=0.16). Bull α-t=+0.95, sideways α-t=-0.20 — opposite of others, bull stronger. SR low (+0.63) but α-t solid — alpha is market-neutral extraction. Sector-neutral top-30% mode best.",
  },

  // ── Long-only · sector-neutral · RSP picks ─────────────────────────────
  // Sourced from scripts/select_pure_alpha_long_only_rsp.py (run
  // 2026-05-08). Under (direction=long_only, neutralize=sector,
  // benchmark=RSP), |β|≈1 is structural — every long_only basket vs an
  // equity benchmark has β around 1 by construction, so RISK.ATTRIBUTION's
  // "Pure Alpha" verdict (|β|<0.30) is unreachable. The verdict that
  // matters here is significance alone: α-p<0.05.
  // Result: only 1 of 22 candidates clears α-p<0.05. The other 5 picks
  // are top-α-t directionals — useful as starting points, but their
  // verdict on RISK.ATTRIBUTION will read MARGINAL or NOISE, not
  // PURE_ALPHA. Honest labeling in intuition text below.
  {
    name: "E/P · LO·SN·RSP",
    hypothesisZh: "E/P 在 (long_only, sector-neutral, RSP) 下唯一通过 α-p<0.05 的因子——top 10% sector-neutral 篮子相对等权 RSP 显著超额",
    hypothesisEn: "E/P is the only factor clearing α-p<0.05 under (long_only, sector-neutral, RSP) — top-10% sector-neutral basket significantly beats equal-weighted RSP",
    expression: "rank(divide(net_income_adjusted, multiply(close, shares_outstanding)))",
    totalReturn: 0.030,
    testSharpe: 1.86,
    testIC: 0.0084,
    direction: "long_only",
    neutralize: "sector",
    benchmarkTicker: "RSP",
    topPct: 0.10,
    intuitionZh:
      "★ 唯一在该 hostile config 下通过显著性的因子。α-t=+2.59, p=0.009 (高度显著)。β=+1.17 (long_only 结构性 ≈ 1)，α-ann=+10.88%, PSR=0.92。Bull α-t=+0.89 / sideways α-t=+1.06——两个 regime 都正。RISK.ATTRIBUTION verdict 在 long_only 上不会读 Pure Alpha（|β|<0.30 结构上不可能），但显著正 α 仍证明因子有效。",
    intuitionEn:
      "★ Only factor clearing significance under this hostile config. α-t=+2.59, p=0.009 (highly significant). β=+1.17 (≈1 structural for long_only), α-ann=+10.88%, PSR=0.92. Bull α-t=+0.89 / sideways α-t=+1.06 — positive both regimes. RISK.ATTRIBUTION won't read Pure Alpha on long_only (|β|<0.30 structurally impossible) but significant positive α proves the factor works.",
  },
  {
    name: "Cash Buffer · LO·SN·RSP",
    hypothesisZh: "现金/股东权益 long-only top 10% sector-neutral——边缘显著（p=0.077），对市场尾部风险有韧性",
    hypothesisEn: "Cash/equity long-only top-10% sector-neutral — marginally significant (p=0.077), resilient under tail risk",
    expression: "rank(divide(cash_and_equivalents, equity))",
    totalReturn: 0.014,
    testSharpe: 0.58,
    testIC: 0.0090,
    direction: "long_only",
    neutralize: "sector",
    benchmarkTicker: "RSP",
    topPct: 0.10,
    intuitionZh:
      "MARGINAL 等级。α-t=+1.77, p=0.077 (差一点 0.05)。bull α-t=-1.90 反向, sideways α-t=+1.13 正——震荡市才是它的舞台，bull 反而拖后腿。RISK.ATTRIBUTION verdict 会读 Marginal。如果用户偏好低风险防御类持仓做底仓可参考。",
    intuitionEn:
      "MARGINAL tier. α-t=+1.77, p=0.077 (just misses 0.05). Bull α-t=-1.90 negative, sideways α-t=+1.13 positive — chop-market factor; bull actually drags. RISK.ATTRIBUTION verdict reads Marginal. Useful as defensive sleeve in long_only book.",
  },
  {
    name: "High DVol · LO·SN·RSP",
    hypothesisZh: "60 日美元成交量排名 long-only top 10%——大流动性股票偏向 mega-cap 倾斜，p=0.10 边缘",
    hypothesisEn: "60d dollar-volume rank long-only top-10% — high-liquidity tilt, borderline at p=0.10",
    expression: "rank(adv60)",
    totalReturn: 0.010,
    testSharpe: 1.01,
    testIC: 0.0097,
    direction: "long_only",
    neutralize: "sector",
    benchmarkTicker: "RSP",
    topPct: 0.10,
    intuitionZh:
      "α-t=+1.63, p=0.103 边缘不显著。β=+0.94 (相对其他 picks 略低)。本质上是把「流动性最深的名字」long——和 RSP 等权篮子比时 mega-cap 加权效应贡献正 α。Verdict 会读 NOISE 但方向稳定。",
    intuitionEn:
      "α-t=+1.63, p=0.103 borderline. β=+0.94 (lower than peers). Essentially longs deepest-liquidity names — vs equal-weighted RSP the mega-cap concentration drives the spread. Verdict reads NOISE but direction is stable.",
  },
  {
    name: "Trend Sharpe 120d · LO·SN·RSP",
    hypothesisZh: "120 日 return/vol 比率——风险调整后趋势强度，sector-neutral top 10% 模式 SR 最高 (+2.11)",
    hypothesisEn: "120d return/vol — risk-adjusted trend; sector-neutral top-10% mode hits SR=+2.11 (highest in batch)",
    expression: "rank(divide(ts_mean(returns, 120), ts_std(returns, 120)))",
    totalReturn: 0.030,
    testSharpe: 2.11,
    testIC: 0.0185,
    direction: "long_only",
    neutralize: "sector",
    benchmarkTicker: "RSP",
    topPct: 0.10,
    intuitionZh:
      "Batch 内 SR 最高 (+2.11)，但 α-t=+1.43, p=0.152——SR 高 + α 不显著的典型 momentum: 系统性吃了趋势 tilt 的 β. β=+0.77 (相对其他 picks 最低，因为 momentum 排除了 reversion 名字)。Sideways α-t=+2.05 极强，bull α-t=-0.07 平。",
    intuitionEn:
      "Highest SR in batch (+2.11), but α-t=+1.43, p=0.152 — classic high-SR-low-significance momentum: SR rides trend β rather than stock-selection α. β=+0.77 (lowest in batch since momentum excludes mean-reverters). Sideways α-t=+2.05 strong, bull α-t=-0.07 flat.",
  },
  {
    name: "B/P · LO·SN·RSP",
    hypothesisZh: "Book yield long-only top 20% sector-neutral——SR=+1.98 强但 α 不显著",
    hypothesisEn: "Book yield long-only top-20% sector-neutral — SR=+1.98 strong but α not significant",
    expression: "rank(divide(equity, multiply(close, shares_outstanding)))",
    totalReturn: 0.025,
    testSharpe: 1.98,
    testIC: 0.0144,
    direction: "long_only",
    neutralize: "sector",
    benchmarkTicker: "RSP",
    topPct: 0.20,
    intuitionZh:
      "α-t=+1.23, p=0.217。Bull α-t=+1.48 强 / sideways α-t=+0.54 弱——和经典 value 反着来 (value 通常震荡市强)。可能是当前 SP500 v3 panel 里 bull 期价值股回归。Verdict NOISE 但 SR 高。",
    intuitionEn:
      "α-t=+1.23, p=0.217. Bull α-t=+1.48 strong / sideways α-t=+0.54 weak — opposite of classic value (value usually wins chop). Plausibly value mean-reversion in the current panel's bull. Verdict NOISE but SR high.",
  },
  {
    name: "ROE · LO·SN·RSP",
    hypothesisZh: "Return on equity long-only top 20% sector-neutral——quality 因子，α 弱但作为 long_only 多样化候选",
    hypothesisEn: "Return on equity long-only top-20% sector-neutral — quality candidate, weak α but useful for diversification",
    expression: "rank(divide(net_income_adjusted, equity))",
    totalReturn: 0.012,
    testSharpe: 0.72,
    testIC: 0.0027,
    direction: "long_only",
    neutralize: "sector",
    benchmarkTicker: "RSP",
    topPct: 0.20,
    intuitionZh:
      "α-t=+1.20, p=0.230。两个 regime 都偏负 (bull -0.10, sideways -0.83)，依靠 OOS 期间未覆盖的小段时间贡献。verdict NOISE。仅作为 quality 类目的 placeholder 候选；真正 quality alpha 需要等待 IC.HORIZON.DECAY 后端引入更长 horizon 检验。",
    intuitionEn:
      "α-t=+1.20, p=0.230. Both regimes slightly negative (bull -0.10, sideways -0.83); residual α from a small uncovered slice. Verdict NOISE. Placeholder for quality family; real quality α likely needs the backend backlog's IC.HORIZON.DECAY to test at longer horizons.",
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
