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
  // 2026-05-08, train_ratio=0.70 to match the form's default slider).
  //
  // HONEST FINDING under STRICT (long_only, sector-neutral, RSP):
  //   - 0 of 22 candidates clear α-p<0.05 (the SIG_ALPHA tier)
  //   - 1 reaches MARGINAL (α-p<0.10): E/P at α-p=0.058, top 20%
  //   - 5 are NOISE: high_dvol, trend_sharpe_120, momo_6_1,
  //     vol_zscore_20, cash_buffer
  //
  // Why so few hits: sector-neutralization on a long_only basket
  // strips away the sector tilt that classic value/quality factors
  // (E/P, B/P, gross_prof) load on. RSP is itself the equal-weighted
  // SP500, which already does sector balancing — beating it WITHOUT
  // sector tilts is genuinely hard. Without sector-neutral, E/P
  // clears α-p=0.009 vs RSP top 10% — the dropped constraint is
  // doing all the work.
  //
  // The verdict bars are correct, not too high. Empirically the
  // alpha is concentrated in (long_only, NONE, RSP) configs once you
  // remove sector-neutral. See intuition text per pick.
  {
    name: "E/P · LO·SN·RSP",
    hypothesisZh: "E/P 在严格 (long_only, sector-neutral, RSP) 下唯一进入 MARGINAL 等级——sector 中性化抹掉了价值因子的行业 tilt",
    hypothesisEn: "E/P is the strongest factor under STRICT (long_only, sector-neutral, RSP) but only reaches MARGINAL — sector-neutralization strips the sector tilt that drives value factor alpha",
    expression: "rank(divide(net_income_adjusted, multiply(close, shares_outstanding)))",
    totalReturn: 0.025,
    testSharpe: 1.80,
    testIC: 0.0071,
    direction: "long_only",
    neutralize: "sector",
    benchmarkTicker: "RSP",
    topPct: 0.20,
    intuitionZh:
      "MARGINAL 等级 (α-p=0.058, 差 0.008)。α-t=+1.89, β=+1.106, SR=+1.80, α-ann=+4.90%。Bull α-t=+0.30 / sideways α-t=+1.54。把同样表达式去掉 sector-neutral (改成 none) → α-p 跳到 0.009——sector 中性化抹掉了价值因子的行业 tilt（E/P 集中在金融/能源），是真 alpha 的来源。",
    intuitionEn:
      "MARGINAL tier (α-p=0.058, just misses 0.05). α-t=+1.89, β=+1.106, SR=+1.80, α-ann=+4.90%. Bull α-t=+0.30 / sideways α-t=+1.54. Drop sector-neutral on the same expression and α-p collapses to 0.009 — sector-neutralization strips the sector tilt (E/P concentrates in financials / energy) that was carrying the alpha.",
  },
  {
    name: "High DVol · LO·SN·RSP",
    hypothesisZh: "60 日美元成交量排名 sector-neutral top 10%——大流动性股票偏向 mega-cap 倾斜，p=0.103 边缘 NOISE",
    hypothesisEn: "60d dollar-volume rank sector-neutral top-10% — high-liquidity tilt, borderline NOISE at p=0.103",
    expression: "rank(adv60)",
    totalReturn: 0.018,
    testSharpe: 1.87,
    testIC: 0.0132,
    direction: "long_only",
    neutralize: "sector",
    benchmarkTicker: "RSP",
    topPct: 0.10,
    intuitionZh:
      "NOISE tier (α-p=0.103)。α-t=+1.63, β=+0.938, SR=+1.87 (batch 第二高), α-ann=+6.72%, PSR=0.96。Bull α-t=+0.51 / sideways α-t=+1.31 都正。本质是「sector 内最深流动性名字」long — vs RSP 等权篮子时大盘股加权效应贡献正 α。SR 高但显著性边缘。",
    intuitionEn:
      "NOISE tier (α-p=0.103). α-t=+1.63, β=+0.938, SR=+1.87 (2nd highest in batch), α-ann=+6.72%, PSR=0.96. Bull α-t=+0.51 / sideways α-t=+1.31 both positive. Essentially longs the deepest-liquidity names within each sector — vs equal-weighted RSP the implicit mega-cap weighting drives positive α. High SR, borderline significance.",
  },
  {
    name: "Trend Sharpe 120d · LO·SN·RSP",
    hypothesisZh: "120 日 return/vol 比率 sector-neutral top 10%——batch 内 SR 最高 (+2.05)，但 α 显著性 NOISE",
    hypothesisEn: "120d return/vol sector-neutral top-10% — highest SR in batch (+2.05) but α not significant",
    expression: "rank(divide(ts_mean(returns, 120), ts_std(returns, 120)))",
    totalReturn: 0.030,
    testSharpe: 2.05,
    testIC: 0.0186,
    direction: "long_only",
    neutralize: "sector",
    benchmarkTicker: "RSP",
    topPct: 0.10,
    intuitionZh:
      "NOISE tier (α-p=0.152)。α-t=+1.43, β=+0.771 (batch 内最低 β), SR=+2.05, α-ann=+7.93%, PSR=0.97。典型 momentum: SR 高 + α 不显著 = SR 来自 trend β 而非 stock-selection α。Bull α-t=+0.17 / sideways α-t=+1.83。",
    intuitionEn:
      "NOISE tier (α-p=0.152). α-t=+1.43, β=+0.771 (lowest β in batch), SR=+2.05, α-ann=+7.93%, PSR=0.97. Classic momentum signature: high SR + low α-significance = SR rides trend β rather than stock-selection α. Bull α-t=+0.17 / sideways α-t=+1.83.",
  },
  {
    name: "Momo 6-1 · LO·SN·RSP",
    hypothesisZh: "6-1 月 momentum sector-neutral top 20%——经典 Jegadeesh-Titman 在 sector-neutral 下被中和",
    hypothesisEn: "6-1 month momentum sector-neutral top-20% — classic Jegadeesh-Titman muted by sector-neutralization",
    expression: "rank(subtract(ts_mean(returns, 126), ts_mean(returns, 21)))",
    totalReturn: 0.018,
    testSharpe: 1.22,
    testIC: 0.0135,
    direction: "long_only",
    neutralize: "sector",
    benchmarkTicker: "RSP",
    topPct: 0.20,
    intuitionZh:
      "NOISE tier (α-p=0.389)。α-t=+0.86, β=+1.036, SR=+1.22, α-ann=+4.45%。Bull α-t=-1.14 反向 / sideways α-t=+1.19 正——典型 momentum 在 mega-cap 牛市中跟不上。Sector-neutral 进一步剥夺了 momentum 的板块 rotation 效应。作为 momentum 类目代表保留，仅供对照。",
    intuitionEn:
      "NOISE tier (α-p=0.389). α-t=+0.86, β=+1.036, SR=+1.22, α-ann=+4.45%. Bull α-t=-1.14 negative / sideways α-t=+1.19 positive — momentum struggles to keep pace in mega-cap-led bulls. Sector-neutral further strips momentum's sector-rotation effect. Kept as momentum-family representative.",
  },
  {
    name: "Vol Z-Score 20d · LO·SN·RSP",
    hypothesisZh: "20 日成交量 z-score sector-neutral top 20%——异常活跃度，long_only/sector-neutral 后 α 弱化",
    hypothesisEn: "20d volume z-score sector-neutral top-20% — abnormal-trading attention; α weakens under long_only/sector-neutral",
    expression: "ts_zscore(volume, 20)",
    totalReturn: 0.020,
    testSharpe: 1.85,
    testIC: 0.0107,
    direction: "long_only",
    neutralize: "sector",
    benchmarkTicker: "RSP",
    topPct: 0.20,
    intuitionZh:
      "NOISE tier (α-p=0.397)。α-t=+0.85, β=+1.000, SR=+1.85, α-ann=+2.12%。Bull α-t=-0.98 / sideways α-t=+2.73——震荡市极强但 bull 拖累。同表达式在 long_short 上是 alpha-agent 第一个 p<0.05 的因子（参考 Volume Z-Score 20d 例子）；long_only 把短头去掉，α 依赖结构下降一半。",
    intuitionEn:
      "NOISE tier (α-p=0.397). α-t=+0.85, β=+1.000, SR=+1.85, α-ann=+2.12%. Bull α-t=-0.98 / sideways α-t=+2.73 — strong in chop, dragged in bull. Same expression on long_short was alpha-agent's first p<0.05 factor (see the Volume Z-Score 20d example above); long_only drops the short leg and halves the α structurally.",
  },
  {
    name: "Cash Buffer · LO·SN·RSP",
    hypothesisZh: "现金/股东权益 sector-neutral top 30%——defensive 因子，sector-neutral 抹掉了行业差异",
    hypothesisEn: "Cash/equity sector-neutral top-30% — defensive factor; sector-neutral strips the cross-sector spread",
    expression: "rank(divide(cash_and_equivalents, equity))",
    totalReturn: 0.012,
    testSharpe: 1.21,
    testIC: 0.0140,
    direction: "long_only",
    neutralize: "sector",
    benchmarkTicker: "RSP",
    topPct: 0.30,
    intuitionZh:
      "NOISE tier (α-p=0.418)。α-t=+0.81, β=+1.091, SR=+1.21, α-ann=+1.92%。Bull α-t=-0.90 / sideways α-t=+0.64。Tech / health-care 通常现金多，sector-neutral 把这个差异抹掉了。底仓 placeholder，无 α 证据。如改成 neutralize=none, top 10%，α-p 升到 ~0.077（仍未达 0.05）。",
    intuitionEn:
      "NOISE tier (α-p=0.418). α-t=+0.81, β=+1.091, SR=+1.21, α-ann=+1.92%. Bull α-t=-0.90 / sideways α-t=+0.64. Tech / healthcare typically run cash-rich; sector-neutralization erases the cross-sector spread. Placeholder, no α evidence. Same expression with neutralize=none top 10% improves to α-p≈0.077, still not significant.",
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
