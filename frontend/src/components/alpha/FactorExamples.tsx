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
  // which it was discovered/validated. /backtest's loadExample applies
  // this config to the form so the user reproduces the proven verdict
  // from RISK.ATTRIBUTION rather than running with default config.
  readonly direction?: "long_short" | "long_only" | "short_only";
  readonly neutralize?: "none" | "sector";
  readonly benchmarkTicker?: "SPY" | "RSP";
  readonly topPct?: number;       // decimal, e.g. 0.30
  readonly bottomPct?: number;    // decimal
  readonly transactionCostBps?: number;
}

// 10 unique factor expressions, deduped across three selection passes:
//   - long_short / SPY (the original v3 selection workflow)
//   - long_only / sector-neutral / RSP (strict spec from user)
//   - long_only / NONE / RSP (sector-neutralization dropped)
//
// For each unique expression, the variant with the strongest verdict
// is kept. Verdict tier hierarchy:
//   PURE_ALPHA   (p<0.05 AND |β|<0.30) > LEVERED_ALPHA (p<0.05) >
//   MARGINAL     (p<0.10) > NOISE      (otherwise)
//
// All metrics re-measured 2026-05-08 against the cap-backfilled v3
// panel with train_ratio=0.70 (matches the form's slider default).
//
// Naming convention: when the proven config differs from the form's
// default (long_short / none / SPY / 30%), the chip name carries a
// suffix like "· LO/RSP" or "· LO/SN/RSP" so the user knows what's
// going to load.
export const FACTOR_EXAMPLES: readonly FactorExample[] = [
  // ── Pure Alpha tier (|β|<0.30 AND p<0.05) ──────────────────────────────
  {
    name: "Earnings Yield (E/P)",
    hypothesisZh: "高盈利收益率（净利润/市值）股 long、低 EY 股 short——经典 Basu 1977 价值因子的多空版",
    hypothesisEn: "Long high earnings yield (net income / market cap), short low — long_short Basu 1977 value",
    expression: "rank(divide(net_income_adjusted, multiply(close, shares_outstanding)))",
    totalReturn: 0.258,
    testSharpe: 1.52,
    testIC: 0.0110,
    direction: "long_short",
    neutralize: "none",
    benchmarkTicker: "SPY",
    topPct: 0.30,
    bottomPct: 0.30,
    intuitionZh:
      "★ PURE ALPHA tier。α-t=+2.29, α-p=0.022, β=-0.10——|β|<0.30 且 p<0.05 双重通过 RISK.ATTRIBUTION 严格判定。SR=+1.52, total return=+25.8%。Basu 价值因子在 long_short 上至今仍 work——shorting overvalued growth 把 sector beta 抵消，alpha 暴露纯净。",
    intuitionEn:
      "★ PURE ALPHA tier. α-t=+2.29, α-p=0.022, β=-0.10 — clears both |β|<0.30 and p<0.05 on RISK.ATTRIBUTION strict verdict. SR=+1.52, total return=+25.8%. Basu value works in long_short — shorting overvalued growth nets out sector beta, leaving clean alpha exposure.",
  },
  {
    name: "Volume Z-Score 20d",
    hypothesisZh: "20 日成交量 z-score——异常活跃度信号，sector-neutral long_short 模式下 alpha 净化",
    hypothesisEn: "20-day volume z-score — abnormal-trading signal; long_short + sector-neutral isolates the alpha",
    expression: "ts_zscore(volume, 20)",
    totalReturn: 0.186,
    testSharpe: 2.93,
    testIC: 0.0107,
    direction: "long_short",
    neutralize: "sector",
    benchmarkTicker: "SPY",
    topPct: 0.30,
    bottomPct: 0.30,
    intuitionZh:
      "★ PURE ALPHA tier。α-t=+2.03, α-p=0.043, β=+0.03——sector-neutral 把行业 rotation 噪声剥离，β 几乎为零，alpha 完全来自 stock-selection。SR=+2.93 (batch 最高)。微观信号「不寻常成交量先于价格」。",
    intuitionEn:
      "★ PURE ALPHA tier. α-t=+2.03, α-p=0.043, β=+0.03 — sector-neutral strips industry-rotation noise; near-zero β means alpha is pure stock-selection. SR=+2.93 (highest in batch). Microstructure signal: 'unusual volume precedes price'.",
  },

  // ── Marginal tier (p<0.10, with reasonable β) ──────────────────────────
  {
    name: "Dollar Volume Z-Score 60d",
    hypothesisZh: "60 日美元成交量 z-score——比裸成交量更准的市场关注度指标，β 接近 0",
    hypothesisEn: "60-day dollar volume z-score — better attention proxy than raw volume; β near zero",
    expression: "ts_zscore(dollar_volume, 60)",
    totalReturn: 0.131,
    testSharpe: 2.04,
    testIC: 0.0119,
    direction: "long_short",
    neutralize: "none",
    benchmarkTicker: "SPY",
    topPct: 0.30,
    bottomPct: 0.30,
    intuitionZh:
      "MARGINAL tier。α-t=+1.88, α-p=0.060 (差 0.010 没到 PURE ALPHA), β=-0.087, SR=+2.04。|β|<0.30 但 p 略超 0.05。和 Volume Z-Score 20d 高度相关，组合不要同时用。",
    intuitionEn:
      "MARGINAL tier. α-t=+1.88, α-p=0.060 (just misses PURE ALPHA by 0.010), β=-0.087, SR=+2.04. |β|<0.30 ✓ but p just over 0.05. Highly correlated with Volume Z-Score 20d — don't stack both.",
  },
  {
    name: "Cash Buffer · LO/RSP",
    hypothesisZh: "现金/股东权益 long_only top 10%——drop sector-neutral 后从 NOISE 升到 MARGINAL，因为 cash 因子有天然 sector tilt",
    hypothesisEn: "Cash/equity long_only top-10% — drops from NOISE to MARGINAL when sector-neutral is removed; cash factor has natural sector tilt",
    expression: "rank(divide(cash_and_equivalents, equity))",
    totalReturn: 0.072,
    testSharpe: 1.11,
    testIC: 0.0128,
    direction: "long_only",
    neutralize: "none",
    benchmarkTicker: "RSP",
    topPct: 0.10,
    intuitionZh:
      "MARGINAL tier (long_only context — |β|<0.30 在 long_only 上结构不可达)。α-t=+1.77, α-p=0.077, β=+1.17, SR=+1.11, α-ann=+7.18%。Tech / health-care 通常现金多，sector-neutral 抹掉这个差异 (α-p 升到 0.418, NOISE)。Bull α-t=-1.49 / sideways α-t=+1.40——震荡市才是它的舞台。",
    intuitionEn:
      "MARGINAL tier (long_only context — |β|<0.30 unreachable structurally for long_only). α-t=+1.77, α-p=0.077, β=+1.17, SR=+1.11, α-ann=+7.18%. Tech/healthcare run cash-rich; sector-neutralization erases this spread (α-p jumps to 0.418, NOISE). Bull α-t=-1.49 / sideways α-t=+1.40 — chop-market factor.",
  },

  // ── NOISE tier (p>0.10) — directional but not statistically confirmed ──
  {
    name: "60d Trend Sharpe",
    hypothesisZh: "60 日 return/vol 比率——风险调整后的趋势强度，sector-neutral 下保留了 momentum 内核",
    hypothesisEn: "60-day return/vol — risk-adjusted trend strength; sector-neutral keeps the momentum core",
    expression: "rank(divide(ts_mean(returns, 60), ts_std(returns, 60)))",
    totalReturn: 0.124,
    testSharpe: 1.54,
    testIC: 0.0136,
    direction: "long_short",
    neutralize: "sector",
    benchmarkTicker: "SPY",
    topPct: 0.30,
    bottomPct: 0.30,
    intuitionZh:
      "NOISE tier (α-p=0.205)。α-t=+1.27, β=-0.18 (|β|<0.30 ✓), SR=+1.54。典型 momentum：bull 时 mega-cap 跑得更快，long_short 中性化反而拖累；震荡市才能赚钱。本期 α 不显著，但作为 momentum 类目代表保留。",
    intuitionEn:
      "NOISE tier (α-p=0.205). α-t=+1.27, β=-0.18 (|β|<0.30 ✓), SR=+1.54. Classic momentum: in bulls mega-cap outpaces, sector-neutral long_short drags; alpha only in chop. α not significant this slice but kept as momentum-family representative.",
  },
  {
    name: "Book Yield (B/P) · LO/RSP",
    hypothesisZh: "Fama-French B/P value long_only top 20%——SR=+2.14 但 p=0.217 不显著，β≈1 是结构性",
    hypothesisEn: "Fama-French B/P value long_only top-20% — SR=+2.14 strong but p=0.217 not significant; β≈1 is structural",
    expression: "rank(divide(equity, multiply(close, shares_outstanding)))",
    totalReturn: 0.062,
    testSharpe: 2.14,
    testIC: 0.0132,
    direction: "long_only",
    neutralize: "none",
    benchmarkTicker: "RSP",
    topPct: 0.20,
    intuitionZh:
      "NOISE tier。α-t=+1.23, α-p=0.217, β=+1.14, SR=+2.14, α-ann=+4.82%。Bull α-t=+1.26 / sideways α-t=+1.23——两个 regime 都正。SR 高但显著性不足，可能受 PIT 短窗口限制。如要更可靠的 value α，参考 E/P (long_short 上 PURE ALPHA)。",
    intuitionEn:
      "NOISE tier. α-t=+1.23, α-p=0.217, β=+1.14, SR=+2.14, α-ann=+4.82%. Bull α-t=+1.26 / sideways α-t=+1.23 — positive in both. High SR but underpowered statistically; PIT window may be limiting. For reliable value α, see E/P (PURE ALPHA on long_short).",
  },
  {
    name: "Trend Sharpe 120d · LO/SN/RSP",
    hypothesisZh: "120 日 return/vol——长 horizon 趋势，sector-neutral 后 β 降到 0.77 (long_only 偏低)",
    hypothesisEn: "120-day return/vol — long-horizon trend; sector-neutral pushes β down to 0.77 (low for long_only)",
    expression: "rank(divide(ts_mean(returns, 120), ts_std(returns, 120)))",
    totalReturn: 0.030,
    testSharpe: 2.05,
    testIC: 0.0186,
    direction: "long_only",
    neutralize: "sector",
    benchmarkTicker: "RSP",
    topPct: 0.10,
    intuitionZh:
      "NOISE tier (α-p=0.152)。α-t=+1.43, β=+0.77 (long_only 中较低), SR=+2.05, α-ann=+7.93%。SR 高 + α 不显著 = 收益主要来自 trend β 而非 stock-selection α。Bull α-t=+0.17 / sideways α-t=+1.83。",
    intuitionEn:
      "NOISE tier (α-p=0.152). α-t=+1.43, β=+0.77 (low for long_only), SR=+2.05, α-ann=+7.93%. High SR + low α-significance = returns ride trend β rather than stock-selection α. Bull α-t=+0.17 / sideways α-t=+1.83.",
  },
  {
    name: "High DVol · LO/SN/RSP",
    hypothesisZh: "60 日美元成交量排名 sector-neutral top 10%——sector 内最深流动性的名字",
    hypothesisEn: "60d dollar-volume rank sector-neutral top-10% — deepest-liquidity names within each sector",
    expression: "rank(adv60)",
    totalReturn: 0.018,
    testSharpe: 1.87,
    testIC: 0.0132,
    direction: "long_only",
    neutralize: "sector",
    benchmarkTicker: "RSP",
    topPct: 0.10,
    intuitionZh:
      "NOISE tier (α-p=0.103)。α-t=+1.63 (临界), β=+0.94, SR=+1.87, α-ann=+6.72%。每个 sector 的「头部最被关注」名字 long——vs RSP 等权时大盘股加权效应贡献正 α。Bull α-t=+0.51 / sideways α-t=+1.31。",
    intuitionEn:
      "NOISE tier (α-p=0.103). α-t=+1.63 (borderline), β=+0.94, SR=+1.87, α-ann=+6.72%. Longs the most-watched names within each sector — implicit mega-cap weighting drives spread vs equal-weighted RSP. Bull α-t=+0.51 / sideways α-t=+1.31.",
  },
  {
    name: "Momo 6-1 · LO/SN/RSP",
    hypothesisZh: "Jegadeesh-Titman 6-1 月 momentum sector-neutral top 20%——经典 momentum 在 sector-neutral + long_only 下被双重打折",
    hypothesisEn: "Jegadeesh-Titman 6-1 month momentum sector-neutral top-20% — classic momentum doubly muted by sector-neutral + long_only",
    expression: "rank(subtract(ts_mean(returns, 126), ts_mean(returns, 21)))",
    totalReturn: 0.018,
    testSharpe: 1.22,
    testIC: 0.0135,
    direction: "long_only",
    neutralize: "sector",
    benchmarkTicker: "RSP",
    topPct: 0.20,
    intuitionZh:
      "NOISE tier (α-p=0.389)。α-t=+0.86, β=+1.04, SR=+1.22, α-ann=+4.45%。Bull α-t=-1.14 反向 / sideways α-t=+1.19 正——典型 momentum 在 mega-cap 牛市跟不上 cap-weighted SPY。Sector-neutral 进一步剥夺板块 rotation 效应。仅作为 momentum 家族对照保留。",
    intuitionEn:
      "NOISE tier (α-p=0.389). α-t=+0.86, β=+1.04, SR=+1.22, α-ann=+4.45%. Bull α-t=-1.14 negative / sideways α-t=+1.19 positive — momentum struggles in mega-cap-led bulls. Sector-neutral further strips sector-rotation effect. Kept as momentum-family contrast.",
  },
  {
    name: "ROE · LO/RSP",
    hypothesisZh: "Return on equity long_only top 20%——quality 因子，short 期表现弱，需更长 horizon 验证",
    hypothesisEn: "Return on equity long_only top-20% — quality factor, weak in short test slice, needs longer-horizon validation",
    expression: "rank(divide(net_income_adjusted, equity))",
    totalReturn: 0.012,
    testSharpe: 1.05,
    testIC: -0.0003,
    direction: "long_only",
    neutralize: "none",
    benchmarkTicker: "RSP",
    topPct: 0.20,
    intuitionZh:
      "NOISE tier (α-p=0.230)。α-t=+1.20, β=+1.01, SR=+1.05, α-ann=+3.03%。Bull α-t=+0.41 / sideways α-t=-1.16——sideways 期反向。IC 接近 0（-0.0003）表示因子在横截面上几乎没有排序信号。仅作为 quality 家族 placeholder，等后端 IC.HORIZON.DECAY 上线后看更长 horizon 表现。",
    intuitionEn:
      "NOISE tier (α-p=0.230). α-t=+1.20, β=+1.01, SR=+1.05, α-ann=+3.03%. Bull α-t=+0.41 / sideways α-t=-1.16. IC near zero (-0.0003) means almost no cross-sectional ranking signal. Placeholder for quality family; revisit when backend IC.HORIZON.DECAY lands for longer-horizon validation.",
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
