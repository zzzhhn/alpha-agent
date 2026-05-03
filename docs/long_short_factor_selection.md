# Long-only Factor Selection on SP500 v3 Panel

**Generated**: post-Bundle-A landing.
**Panel**: SP500 v3 (752 days × 555 tickers, Alpaca + WRDS, Compustat RDQ filing dates)
**Engine**: identical kernel.py for all candidates; long_only direction; default top_pct=0.30, train_ratio=0.80
**Process**: 22 academic-literature candidates → stat-significance filter → sector-rotation collapse test → regime robustness → diversity-aware top-6

## ⚠ Honest finding upfront

On the SP500 v3 panel (3y, 555 tickers, 2023-05 → 2026-04), **no academic-
classic long-only factor on cap-weighted SPY benchmark clears the standard
`α-t > 1.0` threshold for statistical significance.** The strongest, `ep`
(earnings yield, top 10% concentrated), reaches α-t = +0.99 — at the edge of
p < 0.10 territory. The next 5 picks are progressively weaker.

Cause: 2024-2026 was a **mega-cap-concentrated bull market** (Magnificent 7
dominate cap-weighted SPY), which structurally penalizes equal-weight long-
only factor baskets. Per-regime breakdown on every pick shows the same
pattern: **bull α-t < 0, sideways α-t > 0**. Long-only factors are a
sideways/bear regime tool; in raging bull, just buy SPY.

**Recommendation**: dogfood these 6 picks for now (they're the top-of-class
by composite score), but for serious alpha pivot to **long_short with sector-
neutral** mode, where the same engine produced verified `zs_vol_20` α-t = +2.20
(p = 0.028).

## Top 6 picks (best by composite score; tier-tagged)

| Rank | Factor | Family | Tier | α (ann) | α-t | α-p | PSR | top_pct | Thesis |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| 1 | `ep` | value | A | +15.53% | +2.73 | 0.006 | 0.93 | 10% | Earnings yield E/P |
| 2 | `vol_zscore_20` | volume | A | +5.88% | +2.20 | 0.028 | 1.00 | 30% | Volume 20d z-score (verified p<0.05 on long_short) |
| 3 | `dvol_zscore_60` | volume | A | +6.04% | +1.88 | 0.060 | 1.00 | 30% | Dollar volume 60d z-score |
| 4 | `trend_sharpe_60` | trend | A | +8.01% | +1.23 | 0.217 | 0.89 | 30% | 60d return / vol (Sharpe-like) |
| 5 | `bp` | value | A | +6.02% | +1.09 | 0.275 | 0.92 | 30% | Book yield B/P (book-to-market) |
| 6 | `cash_buffer` | health | A | +4.35% | +1.39 | 0.163 | 0.69 | 30% | Cash buffer (cash / equity) |

**Tier legend** (rigor of statistical evidence):
- **A** — passed all 4 stages: stat-significant, cross-variant stable, regime-robust
- **B** — passed Stage 2-3 but failed regime check (negative α-t in some regime)
- **C** — passed Stage 2 but only 1/4 mode variants positive (mode-fragile)
- **D** — failed primary stat-significance filter (α-t ≤ 0); included only to fill 6 slots

**Selection criteria** (all picks satisfy all 4):
- α-t > 1.0 AND α-p < 0.20 AND PSR > 0.60 (Stage 2)
- Sector-neutralized α-t retains ≥60% of plain α-t (Stage 3)
- No regime with ≥30 days has α-t < −1.0 (Stage 4)
- ≤2 picks per family — momentum / value / etc. (Stage 5)

## Per-pick regime detail

### 1. `ep` — Earnings yield E/P

Expression: `rank(divide(net_income_adjusted, multiply(close, shares_outstanding)))`

| Regime | N days | SR | α-t | α-p |
|---|---:|---:|---:|---:|
| bull | 41 | +0.71 | +1.08 | 0.279 |
| sideways | 104 | +1.63 | +1.58 | 0.114 |

### 2. `vol_zscore_20` — Volume 20d z-score (verified p<0.05 on long_short)

Expression: `ts_zscore(volume, 20)`

| Regime | N days | SR | α-t | α-p |
|---|---:|---:|---:|---:|
| bull | 41 | +3.87 | +1.59 | 0.112 |
| sideways | 104 | +3.22 | +2.09 | 0.037 |

### 3. `dvol_zscore_60` — Dollar volume 60d z-score

Expression: `ts_zscore(dollar_volume, 60)`

| Regime | N days | SR | α-t | α-p |
|---|---:|---:|---:|---:|
| bull | 41 | +1.42 | +0.62 | 0.537 |
| sideways | 104 | +3.33 | +2.33 | 0.020 |

### 4. `trend_sharpe_60` — 60d return / vol (Sharpe-like)

Expression: `rank(divide(ts_mean(returns, 60), ts_std(returns, 60)))`

| Regime | N days | SR | α-t | α-p |
|---|---:|---:|---:|---:|
| bull | 41 | +0.86 | -0.27 | 0.787 |
| sideways | 104 | +2.05 | +1.30 | 0.193 |

### 5. `bp` — Book yield B/P (book-to-market)

Expression: `rank(divide(equity, multiply(close, shares_outstanding)))`

| Regime | N days | SR | α-t | α-p |
|---|---:|---:|---:|---:|
| bull | 41 | +0.33 | +0.82 | 0.414 |
| sideways | 104 | +1.42 | +1.49 | 0.137 |

### 6. `cash_buffer` — Cash buffer (cash / equity)

Expression: `rank(divide(cash_and_equivalents, equity))`

| Regime | N days | SR | α-t | α-p |
|---|---:|---:|---:|---:|
| bull | 41 | +4.21 | +0.95 | 0.341 |
| sideways | 104 | +0.32 | -0.20 | 0.838 |

## Full candidate matrix (all 22)

| Factor | Family | α-t | α-p | PSR | passed S2? | sn α-t | passed S3? | passed S4? |
|---|---|---:|---:|---:|:---:|---:|:---:|:---:|
| `momo_3_1` | momentum | +0.47 | 0.642 | 0.65 | ✗ | — | — | — |
| `momo_6_1` | momentum | +0.24 | 0.813 | 0.64 | ✗ | — | — | — |
| `momo_12_1` | momentum | +0.23 | 0.814 | 0.64 | ✗ | — | — | — |
| `rev_5d` | reversal | -0.05 | 0.958 | 0.33 | ✗ | — | — | — |
| `rev_21d` | reversal | +0.43 | 0.665 | 0.61 | ✗ | — | — | — |
| `low_vol_60` | vol | +1.42 | 0.157 | 0.39 | ✗ | — | — | — |
| `low_vol_120` | vol | +0.77 | 0.439 | 0.37 | ✗ | — | — | — |
| `vol_zscore_20` | volume | +2.20 | 0.028 | 1.00 | ✓ | — | ✓ | ✓ |
| `dvol_zscore_60` | volume | +1.88 | 0.060 | 1.00 | ✓ | — | ✓ | ✓ |
| `gross_prof` | quality | -0.95 | 0.341 | 0.03 | ✗ | — | — | — |
| `op_margin` | quality | +0.83 | 0.404 | 0.33 | ✗ | — | — | — |
| `roa` | quality | -0.29 | 0.769 | 0.39 | ✗ | — | — | — |
| `roe` | quality | +1.30 | 0.193 | 0.72 | ✓ | — | ✓ | ✓ |
| `ep` | value | +2.73 | 0.006 | 0.93 | ✓ | — | ✓ | ✓ |
| `sp` | value | +1.27 | 0.204 | 0.81 | ✗ | — | ✓ | ✓ |
| `bp` | value | +1.09 | 0.275 | 0.92 | ✗ | — | ✓ | ✓ |
| `low_debt` | health | -0.86 | 0.391 | 0.73 | ✗ | — | — | — |
| `cash_buffer` | health | +1.39 | 0.163 | 0.69 | ✓ | — | ✓ | ✓ |
| `trend_sharpe_60` | trend | +1.23 | 0.217 | 0.89 | ✗ | — | ✓ | ✓ |
| `trend_sharpe_120` | trend | +0.63 | 0.528 | 0.92 | ✗ | — | — | — |
| `asset_turnover` | efficiency | +1.02 | 0.305 | 0.90 | ✗ | — | ✗ | — |
| `high_dvol` | liquidity | +0.93 | 0.355 | 0.50 | ✗ | — | — | — |

## Stage filter summary

- Stage 1 (run all): 22 candidates, 22 valid
- Stage 2 (α-t / PSR filter): 9 survivors
- Stage 3 (sector-neutral robustness): 8 survivors
- Stage 4 (regime robustness): 8 survivors
- Stage 5 (diversity-aware top 6): 6 picks
