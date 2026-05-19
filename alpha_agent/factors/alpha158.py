"""Alpha158 short-horizon subset (B7, 2026-05-19).

Phase 3 backlog item B7. Source: synthesizer T1 re-scoped — Qlib's
Alpha158 factor library is academic-monthly-rebalance heritage that
would trigger the mega-cap-bull-hostility memory if shipped wholesale;
this module ports the SHORT-HORIZON SUBSET ONLY (lookback ≤ 20 trading
days, ~30 entries) so factor-library bootstrap works for the user's
swing/intraday workflow without dragging the composite toward monthly.

Each entry is a self-contained tuple:
  - name      : URL-safe short identifier
  - expression: alpha-agent DSL expression (must validate against
                core/factor_ast.py operator surface)
  - lookback  : maximum trading-day lookback the expression references
                (used by the surgical filter — UI defaults to ≤20d)
  - category  : "momentum" / "trend" / "volatility" / "low_vol" /
                "liquidity" / "oscillator" / "reversal" / "confirmation"
                / "composite"

LLM-dedup hook (synthesizer asked, deferred to v2): a cosine-sim
service comparing a user-/LLM-generated expression's
(operators_used, lookback) signature against this library would catch
duplicates before the user spends LLM tokens regenerating a known
factor. Out of scope for v1; the library + endpoint alone unblock the
preset-gallery UX.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Category = Literal[
    "momentum", "trend", "volatility", "low_vol", "liquidity",
    "oscillator", "reversal", "confirmation", "composite",
]


@dataclass(frozen=True)
class AlphaSeed:
    name: str
    expression: str
    lookback: int
    category: Category
    description_zh: str
    description_en: str


# Short-horizon Alpha158 subset. All lookback ≤ 20 trading days so the
# library defaults align with the user's swing/intraday timeframe.
ALPHA158_SHORT: tuple[AlphaSeed, ...] = (
    # --- momentum / return rate-of-change ---
    AlphaSeed(
        name="ROC5",
        expression="subtract(divide(close, ts_delay(close, 5)), 1.0)",
        lookback=5, category="momentum",
        description_zh="5 日收益率 (close / lag5_close − 1)",
        description_en="5-day rate of change (close / lag5_close − 1)",
    ),
    AlphaSeed(
        name="ROC10",
        expression="subtract(divide(close, ts_delay(close, 10)), 1.0)",
        lookback=10, category="momentum",
        description_zh="10 日收益率",
        description_en="10-day rate of change",
    ),
    AlphaSeed(
        name="ROC20",
        expression="subtract(divide(close, ts_delay(close, 20)), 1.0)",
        lookback=20, category="momentum",
        description_zh="20 日(约 1 个月)收益率",
        description_en="20-day (~1mo) rate of change",
    ),
    AlphaSeed(
        name="ROC5_RANK",
        expression="rank(subtract(divide(close, ts_delay(close, 5)), 1.0))",
        lookback=5, category="momentum",
        description_zh="5 日收益的截面 rank",
        description_en="Cross-sectional rank of 5d ROC",
    ),
    AlphaSeed(
        name="ROC20_RANK",
        expression="rank(subtract(divide(close, ts_delay(close, 20)), 1.0))",
        lookback=20, category="momentum",
        description_zh="20 日收益的截面 rank",
        description_en="Cross-sectional rank of 20d ROC",
    ),
    AlphaSeed(
        name="RANK_MEAN_RET_5",
        expression="rank(ts_mean(returns, 5))",
        lookback=5, category="momentum",
        description_zh="5 日日均收益 rank",
        description_en="Rank of 5d mean daily return",
    ),
    AlphaSeed(
        name="RANK_MEAN_RET_20",
        expression="rank(ts_mean(returns, 20))",
        lookback=20, category="momentum",
        description_zh="20 日日均收益 rank",
        description_en="Rank of 20d mean daily return",
    ),

    # --- trend / MA distance ---
    AlphaSeed(
        name="MA5_DIST",
        expression="subtract(divide(close, ts_mean(close, 5)), 1.0)",
        lookback=5, category="trend",
        description_zh="close 距离 5 日均线的相对位置",
        description_en="Close relative to 5d MA",
    ),
    AlphaSeed(
        name="MA10_DIST",
        expression="subtract(divide(close, ts_mean(close, 10)), 1.0)",
        lookback=10, category="trend",
        description_zh="close 距离 10 日均线的相对位置",
        description_en="Close relative to 10d MA",
    ),
    AlphaSeed(
        name="MA20_DIST",
        expression="subtract(divide(close, ts_mean(close, 20)), 1.0)",
        lookback=20, category="trend",
        description_zh="close 距离 20 日均线的相对位置",
        description_en="Close relative to 20d MA",
    ),
    AlphaSeed(
        name="MAX20_DIST",
        expression="subtract(divide(close, ts_max(close, 20)), 1.0)",
        lookback=20, category="trend",
        description_zh="close 距离 20 日最高的折扣 (breakout 指标)",
        description_en="Close relative to 20d high (breakout indicator)",
    ),
    AlphaSeed(
        name="MIN20_DIST",
        expression="subtract(divide(close, ts_min(close, 20)), 1.0)",
        lookback=20, category="trend",
        description_zh="close 距离 20 日最低的溢价",
        description_en="Close relative to 20d low",
    ),

    # --- volatility (raw) ---
    AlphaSeed(
        name="STD5",
        expression="ts_std(returns, 5)",
        lookback=5, category="volatility",
        description_zh="5 日日收益标准差",
        description_en="5d realized volatility",
    ),
    AlphaSeed(
        name="STD10",
        expression="ts_std(returns, 10)",
        lookback=10, category="volatility",
        description_zh="10 日日收益标准差",
        description_en="10d realized volatility",
    ),
    AlphaSeed(
        name="STD20",
        expression="ts_std(returns, 20)",
        lookback=20, category="volatility",
        description_zh="20 日日收益标准差",
        description_en="20d realized volatility",
    ),
    AlphaSeed(
        name="HL_RANGE_20",
        expression="divide(subtract(ts_max(high, 20), ts_min(low, 20)), close)",
        lookback=20, category="volatility",
        description_zh="20 日 high-low range / close (Parkinson-like)",
        description_en="20d high-low range / close (Parkinson-like)",
    ),

    # --- low-vol (negated for cross-section rank: low std wins) ---
    AlphaSeed(
        name="LOW_STD_20",
        expression="subtract(0.0, ts_std(returns, 20))",
        lookback=20, category="low_vol",
        description_zh="负 20 日波动 (低波动率因子, Frazzini-Pedersen BAB)",
        description_en="Negated 20d vol (low-vol factor; Frazzini-Pedersen BAB)",
    ),

    # --- liquidity ---
    AlphaSeed(
        name="VOL_RATIO_5",
        expression="divide(volume, ts_mean(volume, 5))",
        lookback=5, category="liquidity",
        description_zh="当日 volume / 5 日均量 (量比)",
        description_en="Volume / 5d mean volume",
    ),
    AlphaSeed(
        name="VOL_RATIO_20",
        expression="divide(volume, ts_mean(volume, 20))",
        lookback=20, category="liquidity",
        description_zh="当日 volume / 20 日均量",
        description_en="Volume / 20d mean volume",
    ),
    AlphaSeed(
        name="DOLLAR_VOL_RANK",
        expression="rank(multiply(close, volume))",
        lookback=1, category="liquidity",
        description_zh="美元成交额截面 rank (大盘股 = 1)",
        description_en="Cross-sectional rank of dollar volume",
    ),
    AlphaSeed(
        name="VOL_ZSCORE_20",
        expression="ts_zscore(volume, 20)",
        lookback=20, category="liquidity",
        description_zh="20 日成交量 z-score",
        description_en="20d volume z-score",
    ),

    # --- oscillator (RSV / Stochastic) ---
    AlphaSeed(
        name="STOCH_20",
        expression="divide(subtract(close, ts_min(close, 20)), subtract(ts_max(close, 20), ts_min(close, 20)))",
        lookback=20, category="oscillator",
        description_zh="20 日 Stochastic %K (close 在 20d 区间的位置)",
        description_en="20d Stochastic %K position",
    ),
    AlphaSeed(
        name="STOCH_5",
        expression="divide(subtract(close, ts_min(close, 5)), subtract(ts_max(close, 5), ts_min(close, 5)))",
        lookback=5, category="oscillator",
        description_zh="5 日 Stochastic %K",
        description_en="5d Stochastic %K",
    ),
    AlphaSeed(
        name="RET_ZSCORE_20",
        expression="ts_zscore(returns, 20)",
        lookback=20, category="oscillator",
        description_zh="20 日日收益 z-score",
        description_en="20d return z-score",
    ),

    # --- reversal ---
    AlphaSeed(
        name="REVERSAL_5",
        expression="subtract(0.0, subtract(divide(close, ts_delay(close, 5)), 1.0))",
        lookback=5, category="reversal",
        description_zh="负 5 日动量 (短期反转因子)",
        description_en="Negated 5d momentum (short-term reversal)",
    ),
    AlphaSeed(
        name="REVERSAL_1",
        expression="subtract(0.0, returns)",
        lookback=1, category="reversal",
        description_zh="负日收益 (Jegadeesh 1990 1日反转)",
        description_en="Negated daily return (Jegadeesh 1990 1d reversal)",
    ),

    # --- confirmation (volume confirms direction) ---
    AlphaSeed(
        name="VOL_RET_CORR_20",
        expression="ts_corr(volume, returns, 20)",
        lookback=20, category="confirmation",
        description_zh="20 日 volume 与 return 相关性 (>0 量价配合)",
        description_en="20d volume-return correlation",
    ),

    # --- decay-weighted (Alpha101-style) ---
    AlphaSeed(
        name="DECAY_RET_20",
        expression="ts_decay_linear(returns, 20)",
        lookback=20, category="momentum",
        description_zh="20 日 linear-decay 加权收益",
        description_en="20d linear-decay weighted return",
    ),
    AlphaSeed(
        name="DECAY_VOL_20",
        expression="ts_decay_linear(volume, 20)",
        lookback=20, category="liquidity",
        description_zh="20 日 linear-decay 加权成交量",
        description_en="20d linear-decay weighted volume",
    ),

    # --- composite (momentum minus vol; mirrors SHORT_TERM_FACTOR_EXPR) ---
    AlphaSeed(
        name="MOMVOL_10",
        expression="subtract(rank(ts_mean(returns, 10)), rank(ts_std(returns, 10)))",
        lookback=10, category="composite",
        description_zh="10 日动量 减 10 日波动 rank-composite",
        description_en="10d momentum rank − 10d vol rank composite",
    ),
    AlphaSeed(
        name="MOMVOL_20",
        expression="subtract(rank(ts_mean(returns, 20)), rank(ts_std(returns, 20)))",
        lookback=20, category="composite",
        description_zh="20 日动量 减 20 日波动 rank-composite",
        description_en="20d momentum rank − 20d vol rank composite",
    ),
)


def filter_library(
    horizon_max: int | None = 20,
    category: Category | None = None,
) -> list[AlphaSeed]:
    """Return the subset of ALPHA158_SHORT matching the filter.

    horizon_max=None disables the lookback filter; category=None
    disables the category filter. Both None = full library.
    """
    out = list(ALPHA158_SHORT)
    if horizon_max is not None:
        out = [s for s in out if s.lookback <= horizon_max]
    if category is not None:
        out = [s for s in out if s.category == category]
    return out
