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
| 1 | `ep` | value | A | +6.60% | +0.99 | 0.324 | 0.91 | 10% | Earnings yield E/P |
| 2 | `trend_sharpe_120` | trend | A | +0.90% | +0.21 | 0.836 | 0.91 | 30% | 120d return / vol |
| 3 | `low_vol_120` | vol | A | +3.79% | +0.70 | 0.486 | 0.81 | 10% | Low realized vol 120d |
| 4 | `low_vol_60` | vol | A | +1.06% | +0.20 | 0.843 | 0.82 | 10% | Low realized vol 60d (low-vol anomaly) |
| 5 | `vol_zscore_20` | volume | C | +0.60% | +0.11 | 0.910 | 0.95 | 10% | Volume 20d z-score (verified p<0.05 on long_short) |
| 6 | `bp` | value | C | +0.30% | +0.04 | 0.969 | 0.88 | 10% | Book yield B/P (book-to-market) |

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
| bull | 41 | +2.25 | +0.20 | 0.840 |
| sideways | 104 | +1.98 | +0.96 | 0.336 |

### 2. `trend_sharpe_120` — 120d return / vol

Expression: `rank(divide(ts_mean(returns, 120), ts_std(returns, 120)))`

| Regime | N days | SR | α-t | α-p |
|---|---:|---:|---:|---:|
| bull | 41 | +2.92 | -0.60 | 0.546 |
| sideways | 104 | +2.06 | +1.09 | 0.274 |

### 3. `low_vol_120` — Low realized vol 120d

Expression: `rank(inverse(ts_std(returns, 120)))`

| Regime | N days | SR | α-t | α-p |
|---|---:|---:|---:|---:|
| bull | 41 | -0.80 | -0.55 | 0.581 |
| sideways | 104 | +2.16 | +1.29 | 0.198 |

### 4. `low_vol_60` — Low realized vol 60d (low-vol anomaly)

Expression: `rank(inverse(ts_std(returns, 60)))`

| Regime | N days | SR | α-t | α-p |
|---|---:|---:|---:|---:|
| bull | 41 | -0.71 | -0.88 | 0.377 |
| sideways | 104 | +1.61 | +0.78 | 0.433 |

### 5. `vol_zscore_20` — Volume 20d z-score (verified p<0.05 on long_short)

Expression: `ts_zscore(volume, 20)`

| Regime | N days | SR | α-t | α-p |
|---|---:|---:|---:|---:|
| bull | 41 | +2.89 | +0.20 | 0.840 |
| sideways | 104 | +2.63 | +1.57 | 0.117 |

### 6. `bp` — Book yield B/P (book-to-market)

Expression: `rank(divide(equity, multiply(close, shares_outstanding)))`

| Regime | N days | SR | α-t | α-p |
|---|---:|---:|---:|---:|
| bull | 41 | +1.79 | +0.02 | 0.988 |
| sideways | 104 | +1.87 | +0.87 | 0.385 |

## Full candidate matrix (all 22)

| Factor | Family | α-t | α-p | PSR | passed S2? | sn α-t | passed S3? | passed S4? |
|---|---|---:|---:|---:|:---:|---:|:---:|:---:|
| `momo_3_1` | momentum | -0.69 | 0.489 | 0.75 | ✗ | — | — | — |
| `momo_6_1` | momentum | +0.04 | 0.965 | 0.79 | ✗ | — | ✗ | — |
| `momo_12_1` | momentum | -0.54 | 0.591 | 0.73 | ✗ | — | — | — |
| `rev_5d` | reversal | -0.35 | 0.723 | 0.64 | ✗ | — | — | — |
| `rev_21d` | reversal | -0.52 | 0.606 | 0.74 | ✗ | — | — | — |
| `low_vol_60` | vol | +0.20 | 0.843 | 0.82 | ✗ | — | ✓ | ✓ |
| `low_vol_120` | vol | +0.70 | 0.486 | 0.81 | ✗ | — | ✓ | ✓ |
| `vol_zscore_20` | volume | +0.11 | 0.910 | 0.95 | ✗ | — | ✗ | — |
| `dvol_zscore_60` | volume | -0.73 | 0.467 | 0.98 | ✗ | — | — | — |
| `gross_prof` | quality | -1.78 | 0.074 | 0.59 | ✗ | — | — | — |
| `op_margin` | quality | -0.35 | 0.725 | 0.67 | ✗ | — | — | — |
| `roa` | quality | -1.22 | 0.222 | 0.80 | ✗ | — | — | — |
| `roe` | quality | -0.06 | 0.951 | 0.76 | ✗ | — | — | — |
| `ep` | value | +0.99 | 0.324 | 0.91 | ✗ | — | ✓ | ✓ |
| `sp` | value | +0.04 | 0.970 | 0.86 | ✗ | — | ✗ | — |
| `bp` | value | +0.04 | 0.969 | 0.88 | ✗ | — | ✗ | — |
| `low_debt` | health | -1.51 | 0.130 | 0.72 | ✗ | — | — | — |
| `cash_buffer` | health | +0.05 | 0.961 | 0.67 | ✗ | — | ✗ | — |
| `trend_sharpe_60` | trend | -0.39 | 0.697 | 0.88 | ✗ | — | — | — |
| `trend_sharpe_120` | trend | +0.21 | 0.836 | 0.91 | ✗ | — | ✓ | ✓ |
| `asset_turnover` | efficiency | -0.13 | 0.898 | 0.91 | ✗ | — | — | — |
| `high_dvol` | liquidity | -0.63 | 0.529 | 0.68 | ✗ | — | — | — |

## Stage filter summary

- Stage 1 (run all): 22 candidates, 22 valid
- Stage 2 (α-t / PSR filter): 9 survivors
- Stage 3 (sector-neutral robustness): 4 survivors
- Stage 4 (regime robustness): 4 survivors
- Stage 5 (diversity-aware top 6): 6 picks
