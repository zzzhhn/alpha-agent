// Glossary of the abbreviations / status codes shown on the Factor Zoo page.
//
// In zh mode many of these stay in their conventional English short form
// (IC, Sharpe, LS/LO/SO, …) because that's how quants read them — but an
// abbreviation with no way to see its full meaning is hostile to anyone who
// doesn't already know it. Each entry below is the plain-language expansion
// surfaced on hover (GlossaryTip), in both locales.

export interface GlossaryDef {
  readonly en: string;
  readonly zh: string;
}

export const ZOO_GLOSSARY: Record<string, GlossaryDef> = {
  IC: {
    en: "Information Coefficient — rank correlation between the factor score and forward returns. Higher = stronger cross-sectional predictive signal.",
    zh: "信息系数（Information Coefficient）：因子得分与未来收益的秩相关，越高代表横截面预测能力越强。",
  },
  ICIR: {
    en: "IC Information Ratio — mean(IC) / std(IC) × √252. The stability-adjusted strength of the IC signal.",
    zh: "IC 信息比率：mean(IC) / std(IC) × √252，衡量 IC 信号经稳定性调整后的强度。",
  },
  PSR: {
    en: "Probabilistic Sharpe Ratio — probability the true Sharpe beats a multiple-testing-corrected null benchmark.",
    zh: "概率夏普比率（Probabilistic Sharpe Ratio）：真实 Sharpe 超过经多重检验校正的零假设基准的概率。",
  },
  SHARPE: {
    en: "Sharpe ratio — annualized risk-adjusted return: excess return per unit of volatility.",
    zh: "夏普比率：年化风险调整后收益，即每单位波动率获得的超额收益。",
  },
  SR: {
    en: "Sharpe ratio — annualized risk-adjusted return: excess return per unit of volatility.",
    zh: "夏普比率：年化风险调整后收益，即每单位波动率获得的超额收益。",
  },
  MAXDD: {
    en: "Maximum drawdown — the largest peak-to-trough equity loss over the backtest period.",
    zh: "最大回撤：回测期内净值从峰值到谷值的最大跌幅。",
  },
  TURNOVER: {
    en: "Turnover — the fraction of the portfolio replaced each rebalance. Higher turnover means higher trading cost.",
    zh: "换手率：每次再平衡时被替换的组合比例，越高交易成本越大。",
  },
  OOS: {
    en: "Out-of-sample — the held-out test slice the model never trained on; the honest measure of an edge.",
    zh: "样本外（Out-of-sample）：模型未参与训练的留出测试段，是衡量真实边际最诚实的指标。",
  },
  ANN: {
    en: "Annualized — a rate scaled to a one-year horizon.",
    zh: "年化：换算到一年期限的比率。",
  },
  DIR: {
    en: "Direction — how the factor is traded: LS (long-short), LO (long-only), or SO (short-only).",
    zh: "方向：因子的交易方式，LS（多空）、LO（纯多头）或 SO（纯空头）。",
  },
  LS: {
    en: "Long-short — buys the top of the factor and shorts the bottom; roughly market-neutral.",
    zh: "多空（long-short）：买入因子高分端、卖空低分端，近似市场中性。",
  },
  LO: {
    en: "Long-only — buys the top of the factor; no shorting.",
    zh: "纯多头（long-only）：仅买入因子高分端，不做空。",
  },
  SO: {
    en: "Short-only — shorts the bottom of the factor; no longs.",
    zh: "纯空头（short-only）：仅卖空因子低分端，不做多。",
  },
  STALE: {
    en: "Stale — this factor hasn't been re-evaluated recently, so its saved metrics may be out of date.",
    zh: "沉睡（stale）：该因子近期未重新评测，已保存的指标可能已经过时。",
  },
  DECAYING: {
    en: "Decaying — the factor's IC has dropped by ≥50% from its peak; the edge may be fading.",
    zh: "衰减（decaying）：该因子 IC 较峰值下降 ≥50%，其预测边际可能正在消失。",
  },
  DS: {
    en: "Deflated Sharpe ratio — Sharpe adjusted for multiple testing and selection bias.",
    zh: "折减夏普比率（Deflated Sharpe）：对多重检验和择优偏差进行修正后的 Sharpe。",
  },
  "IC OOS": {
    en: "Out-of-sample Information Coefficient — factor-score correlation measured only on held-out data.",
    zh: "样本外信息系数：只在未参与拟合的留出数据上测量因子得分与未来收益的相关性。",
  },
  FOLDS: {
    en: "Validation folds — independent time splits used to test whether the signal persists across periods.",
    zh: "验证折数：用于检验信号能否跨时期保持有效的独立时间切片数量。",
  },
  TRIALS: {
    en: "Trials — the number of candidate variants explored; more trials increase selection-bias risk.",
    zh: "尝试次数：曾探索的候选变体数量，次数越多，择优偏差风险越高。",
  },
  "SELF-CORR": {
    en: "Self-correlation — similarity to an existing or prior factor. High values imply duplicated exposure.",
    zh: "自相关：与既有或历史因子的相似度，过高通常意味着暴露重复。",
  },
  BRIER: {
    en: "Brier score — mean squared error of probability forecasts. Lower is better calibrated.",
    zh: "Brier 分数：概率预测的均方误差，越低表示概率校准越好。",
  },
  N_UNIVERSE: {
    en: "Total number of securities in the source universe before filters are applied.",
    zh: "筛选前，源股票池中的证券总数。",
  },
  N_ELIGIBLE: {
    en: "Number of securities with sufficient data that remain after all universe filters.",
    zh: "通过全部股票池筛选且具有足够数据的证券数量。",
  },
  ELIG_RATE: {
    en: "Eligibility rate — eligible securities divided by the source-universe count.",
    zh: "合格率：合格证券数除以源股票池总数。",
  },
  TOP_SCORE: {
    en: "Highest composite factor score among the current candidates; it is a rank signal, not an expected return.",
    zh: "当前候选股中的最高综合因子分数，它是排序信号，不等同于预期收益率。",
  },
  AVG_SCORE: {
    en: "Mean composite factor score across the displayed candidate basket.",
    zh: "当前展示候选组合的综合因子分数均值。",
  },
};

/** Locale-resolved definition text for a term (falls back to the term itself). */
export function glossaryText(term: string, locale: "zh" | "en"): string {
  const def = ZOO_GLOSSARY[term.toUpperCase()];
  if (!def) return term;
  return locale === "zh" ? def.zh : def.en;
}
