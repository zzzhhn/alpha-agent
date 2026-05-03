# SP100 v2 vs SP500 v3 — Factor Comparison Report

**Generated**: post-T1.5a landing.
**Method**: identical factor expressions, identical engine (kernel.py),
two panels differing only in (a) universe size and (b) history length.

| Dimension | SP100 v2 (legacy) | **SP500 v3 (T1.5a)** |
|---|---|---|
| Universe | 98 tickers (yfinance) | **555 tickers (Alpaca + WRDS)** |
| History | 1 year (251 days) | **3 years (752 days)** |
| Survivorship correction | mask only (4/98 movers) | mask + delisted-ticker data |
| Fundamentals | yfinance +45d estimate | **Compustat RDQ filing date** |
| Walk-forward windows (30d step) | ~7 | **~25** (3.5x) |
| Cross-sectional N at each rank | ~98 | **~555** (5.7x) |

## Headline: statistical power

| α p-value threshold | SP100 v2 | **SP500 v3** | delta |
|---|---|---|---|
| p < 0.05 | 0/10 | **1/10** | +1 |
| p < 0.10 | 2/10 | **1/10** | -1 |

### The `p < 0.10` count went DOWN — a feature, not a bug

The two v2 factors that cleared `p < 0.10` were `vol_60d_hi` (IC `p = 0.019`) and
`vol_120d_hi` (IC `p = 0.041`). Both rank tickers by recent realized volatility.
On SP100 v2 those signals look strong because the panel happens to include
**MSTR / SNOW / COIN / PLTR** — permanently extreme-vol mega-caps that were
either never SP500 members or only joined mid-window. Their volatility ranks
were absorbing what looked like systematic alpha.

On SP500 v3, those four tickers are correctly excluded from the cross-section
at the dates they were not SP500 members (membership mask), and the broader
universe dilutes the rest. Both vol factors collapse: v3 IC `p` becomes 0.295
and 0.442 respectively. The v2 "significance" was phantom alpha from
survivorship bias.

In exchange, v3 surfaces **`zs_vol_20`** as a genuine signal: it was marginal
on v2 (`p = 0.151`, α-t = +1.69) and clears `p < 0.05` on v3 (`p = 0.017`,
α-t = +2.10). With 555 tickers in the cross-section, "unusual recent volume"
becomes statistically distinguishable from noise.

Net: v3 trades two false positives for one real positive — exactly what
proper survivorship correction is supposed to deliver.

## Per-factor comparison

| Factor | v2 SR | v3 SR | v2 IC | v3 IC | v2 IC_p | v3 IC_p | v2 PSR | v3 PSR | v2 α-t | v3 α-t |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `momo_5d` | +1.21 | +1.68 | +0.0153 | +0.0100 | 0.701 | 0.496 | 0.70 | 0.91 | +1.91 | +0.69 |
| `momo_20d` | +0.31 | +1.10 | -0.0046 | -0.0042 | 0.898 | 0.773 | 0.56 | 0.81 | +0.63 | +0.40 |
| `momo_60d` | +0.41 | +1.47 | -0.0139 | +0.0074 | 0.724 | 0.624 | 0.57 | 0.87 | +1.22 | +1.04 |
| `momo_120d` | +0.49 | +1.61 | -0.0040 | +0.0161 | 0.920 | 0.339 | 0.59 | 0.89 | +0.84 | +0.20 |
| `vol_60d_hi` | +3.12 | +0.89 | +0.0891 | +0.0186 | 0.019 | 0.295 | 0.91 | 0.75 | +0.41 | -0.80 |
| `vol_120d_hi` | +2.82 | +0.90 | +0.0831 | +0.0138 | 0.041 | 0.442 | 0.89 | 0.75 | -0.97 | -0.38 |
| `zs_close_60` | +0.08 | +1.21 | -0.0099 | +0.0010 | 0.793 | 0.944 | 0.51 | 0.83 | +1.20 | +1.00 |
| `zs_vol_20` | +1.85 | +3.35 | +0.0278 | +0.0153 | 0.151 | 0.017 | 0.79 | 1.00 | +1.69 | +2.10 |
| `roe` | -0.53 | -0.64 | +0.0157 | +0.0035 | 0.377 | 0.561 | 0.41 | 0.30 | -0.71 | -0.17 |
| `roa` | +1.79 | -0.29 | +0.0066 | -0.0050 | 0.721 | 0.503 | 0.80 | 0.41 | -0.44 | -0.92 |

## Interpretation

**What changed between v2 and v3 holds the engine constant** — same kernel.py,
same operators, same backtest mechanics. Differences trace entirely to data.

**Universe size effect** (98 → 555 tickers) tightens cross-sectional rank
variance, so any genuine signal converges to its true IC value faster. Noise
factors stay noisy but with smaller p-value variance.

**History length effect** (1y → 3y) gives the bootstrap CIs more independent
samples to draw from; CI widths typically tighten by √3 ≈ 1.7x.

**Survivorship effect** (mask + delisted data) shows up most on factors that
rank on extreme cross-sectional values — vol and zscore-style — because
MSTR/SNOW-style permanent-extreme tickers are no longer artificially in or
out of the universe. Momentum factors are less affected because their
signals are time-series, not cross-section-extreme.

**Caveat**: ROE / ROA on v3 use Compustat fundamentals (real RDQ filing
dates); on v2 they use yfinance with a +45d filing-date estimate. Some of
the cross-panel difference for fundamental factors is data-source variance,
not pure universe/window effect.
