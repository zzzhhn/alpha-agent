"""Statistical significance + multiple-testing correction (T2.1 of v4).

When a user iterates on M factor variants and picks the one with highest
in-sample Sharpe, the picked variant's realized Sharpe is the maximum of M
noisy estimates — even if every variant truly has SR=0, the sample max grows
~ sqrt(2 ln M) by extreme-value theory. The user's "winner" is therefore
biased upward, sometimes by 0.5-1.5 Sharpe units, before any out-of-sample
data is touched.

Bailey & López de Prado (2014, "The Deflated Sharpe Ratio") give a closed
form for the probability that the realized SR exceeds the null benchmark
once the multiple-comparison and non-normality corrections are applied:

    PSR(SR0) = Φ((SR̂ - SR0) * sqrt((T-1) / (1 - γ3·SR̂ + (γ4-1)/4·SR̂²)))

where:
    SR̂  : realized (sample) Sharpe (annualized)
    SR0 : benchmark / null Sharpe to test against
    T   : sample length (trading days)
    γ3  : skewness of returns
    γ4  : kurtosis of returns (NOT excess; γ4-1 in the formula = excess)
    Φ   : standard normal CDF

For DSR specifically, SR0 is set to E[max SR_M] under N independent null
trials, approximated by:

    E[max SR_M] ≈ sqrt(V) * ((1-γ_em)·Φ⁻¹(1 - 1/M) + γ_em·Φ⁻¹(1 - 1/(M·e)))

where V is the variance of SR estimates and γ_em ≈ 0.5772 is the
Euler-Mascheroni constant. We use V = 1/T as a conservative estimate
when only one factor's data is available.

The output is a probability in [0, 1]. Values:
    PSR > 0.95  →  factor's SR is convincingly above the multiple-testing-
                   corrected null; treat as real
    0.5-0.95    →  marginal; needs more data or fewer trials
    < 0.5       →  factor's realized SR is below the lucky-max under the
                   stated number of trials; do not deploy
"""
from __future__ import annotations

import math

import numpy as np


_EULER_MASCHERONI = 0.5772156649015329


def _normal_inv_cdf(p: float) -> float:
    """Φ⁻¹(p) — Beasley-Springer-Moro approximation, accurate to ~1e-7.

    NumPy provides this via `scipy.stats.norm.ppf`, but we avoid SciPy as a
    runtime dep (Vercel function size). For our use (p in [1-1/M, 1-1/(M·e)]
    with M in [2, 100]), p is always in (0.5, 1) and accuracy of 1e-7 is
    overkill — this implementation is faster and dep-free.
    """
    if not 0.0 < p < 1.0:
        raise ValueError(f"p must be in (0, 1), got {p}")
    # Beasley-Springer-Moro
    a = (-3.969683028665376e+01, 2.209460984245205e+02,
         -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02,
         -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01,
         -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01,
         2.445134137142996e+00, 3.754408661907416e+00)
    p_low = 0.02425
    p_high = 1.0 - p_low
    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        num = (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])
        den = ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1.0)
        return num / den
    if p > p_high:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        num = (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])
        den = ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1.0)
        return -num / den
    q = p - 0.5
    r = q * q
    num = (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5]) * q
    den = (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1.0)
    return num / den


def _normal_cdf(x: float) -> float:
    """Φ(x) via erf; the 1/2 factor + erf is the cleanest expression."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def lucky_max_multiplier(n_trials: int) -> float:
    """The unitless extreme-value multiplier from Bailey-LdP 2014 §A:

        ((1 - γ_em) · Φ⁻¹(1 - 1/N) + γ_em · Φ⁻¹(1 - 1/(N·e)))

    Multiply this by σ(SR̂) to get E[max SR_N] in matching units.
    Returns 0 for N ≤ 1 (no multiple-comparison penalty).
    """
    if n_trials <= 1:
        return 0.0
    z1 = _normal_inv_cdf(1.0 - 1.0 / n_trials)
    z2 = _normal_inv_cdf(1.0 - 1.0 / (n_trials * math.e))
    return (1.0 - _EULER_MASCHERONI) * z1 + _EULER_MASCHERONI * z2


def expected_max_sharpe_annual(n_trials: int, n_samples: int) -> float:
    """E[max SR_annual] under N independent null trials with T daily samples each.

    Under the null (true SR = 0) and IID returns, σ(SR̂_daily) ≈ 1/√(T-1),
    so σ(SR̂_annual) ≈ √(252/(T-1)). Multiply by the extreme-value
    multiplier to get the lucky-max benchmark used in DSR.
    """
    if n_trials <= 1 or n_samples < 2:
        return 0.0
    sigma_annual = math.sqrt(252.0 / max(n_samples - 1, 1))
    return sigma_annual * lucky_max_multiplier(n_trials)


def deflated_sharpe(
    daily_returns: np.ndarray,
    n_trials: int,
    benchmark_sr_annual: float = 0.0,
) -> tuple[float, float]:
    """Probabilistic Sharpe Ratio (deflated) per Bailey & López de Prado 2014.

    Args:
        daily_returns: 1D array of daily strategy returns (NaN-tolerant; NaNs
                       dropped before computation).
        n_trials: number of variants the user explored picking this factor.
                  Roughly: how many different expressions / parameter sets
                  did they backtest before saving this one?
        benchmark_sr_annual: SR threshold to test against, in annual units.
                             Default 0 = "is this factor's SR > 0?"
                             Use `expected_max_sharpe_null(n_trials)` to test
                             against the multiple-testing-corrected null.

    Returns:
        (psr, sr_hat_annual): probability in [0, 1] that the true SR exceeds
        the benchmark, plus the realized annualized Sharpe for reference.

    PSR > 0.95 = factor's SR convincingly clears the bar.
    PSR < 0.5 = realized SR below what one would expect from luck across
                n_trials independent null factors.
    """
    r = np.asarray(daily_returns, dtype=np.float64)
    r = r[~np.isnan(r)]
    n = r.size
    if n < 30:  # Bailey-LdP rely on CLT; short samples not meaningful
        return (0.5, 0.0)

    mean = float(r.mean())
    std = float(r.std(ddof=1))
    if std <= 1e-12:
        return (0.5, 0.0)

    # Daily Sharpe → annualized (× sqrt(252))
    sr_daily = mean / std
    sr_hat = sr_daily * math.sqrt(252.0)

    # Skew + kurtosis on the daily series (these are scale-invariant)
    centered = r - mean
    m2 = float((centered**2).mean())
    m3 = float((centered**3).mean())
    m4 = float((centered**4).mean())
    if m2 <= 0:
        return (0.5, sr_hat)
    skew = m3 / (m2**1.5)
    kurt = m4 / (m2**2)  # NOT excess; raw kurtosis
    excess_kurt = kurt - 3.0

    # Variance of the sample Sharpe estimate (Bailey-LdP eq. 5)
    sr_var_daily = (1.0 - skew * sr_daily + (excess_kurt / 4.0) * sr_daily**2) / (n - 1)
    if sr_var_daily <= 0:
        # Pathological; fall back to raw normal-approximation t-test
        sr_var_daily = max(1.0 / (n - 1), 1e-12)

    # Convert benchmark SR_annual → SR_daily for like-for-like comparison
    sr0_daily = benchmark_sr_annual / math.sqrt(252.0)

    z = (sr_daily - sr0_daily) / math.sqrt(sr_var_daily)
    psr = _normal_cdf(z)
    return (float(psr), float(sr_hat))


def stationary_block_bootstrap_ci(
    values: np.ndarray,
    metric_fn,
    block_len: int = 20,
    n_resamples: int = 1000,
    ci: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """Stationary block bootstrap 95% CI for a scalar metric on a daily series.

    Politis-Romano 1994: each resample is built by concatenating blocks whose
    lengths follow a geometric distribution with mean `block_len`. Block
    starting positions are uniform over the original series (with wrap-around).
    This preserves serial correlation structure that IID bootstrap destroys —
    important for Sharpe / IC where daily returns aren't independent.

    Args:
        values: 1D float array, e.g. daily strategy returns or daily IC.
                NaNs filtered out before bootstrapping.
        metric_fn: callable taking a 1D array → scalar (e.g. annualized Sharpe).
        block_len: mean block length in samples (~ 20 trading days = 1 month).
        n_resamples: number of bootstrap iterations (default 1000).
        ci: confidence level in (0, 1). 0.95 → return (2.5th, 97.5th) percentiles.
        seed: deterministic RNG seed for reproducibility.

    Returns:
        (low, high) — both NaN if input has fewer than 5 valid samples.

    Wall-clock: ~50ms for n_resamples=1000 on 200-day series.
    """
    arr = np.asarray(values, dtype=np.float64)
    arr = arr[~np.isnan(arr)]
    n = arr.size
    if n < 5:
        return (float("nan"), float("nan"))

    rng = np.random.default_rng(seed)
    p = 1.0 / max(block_len, 1)

    # Pre-roll all randomness in vectorized chunks; the inner index assembly
    # is sequential (carry "current pointer" from new_block decisions).
    starts = rng.integers(0, n, size=(n_resamples, n))
    new_block = rng.random(size=(n_resamples, n)) < p
    new_block[:, 0] = True  # always start a new block at j=0

    metrics = np.empty(n_resamples, dtype=np.float64)
    for r in range(n_resamples):
        idx = np.empty(n, dtype=np.int64)
        cur = 0
        for j in range(n):
            if new_block[r, j]:
                cur = int(starts[r, j])
            idx[j] = cur % n
            cur += 1
        try:
            metrics[r] = float(metric_fn(arr[idx]))
        except Exception:
            metrics[r] = float("nan")

    metrics = metrics[~np.isnan(metrics)]
    if metrics.size < 5:
        return (float("nan"), float("nan"))
    alpha = (1.0 - ci) / 2.0
    low = float(np.percentile(metrics, alpha * 100.0))
    high = float(np.percentile(metrics, (1.0 - alpha) * 100.0))
    return (low, high)


def cross_correlation_matrix(
    returns_by_factor: dict[str, np.ndarray],
) -> tuple[list[str], np.ndarray, list[tuple[str, str, float]]]:
    """Pearson correlation of daily strategy returns across factors.

    Args:
        returns_by_factor: {factor_name: 1D daily-return array}. Arrays must
                           share length; NaNs are pairwise-dropped.

    Returns:
        (names, corr_matrix, warnings) where:
          names         — factor names in column order
          corr_matrix   — (M, M) symmetric, diagonal = 1.0
          warnings      — list of (name_a, name_b, corr) for pairs |corr| > 0.8,
                          excluding self-pairs; sorted by |corr| descending.

    Empty input returns ([], 0×0 matrix, []).
    """
    if not returns_by_factor:
        return ([], np.zeros((0, 0)), [])

    names = list(returns_by_factor.keys())
    arrays = [np.asarray(returns_by_factor[n], dtype=np.float64) for n in names]
    m = len(names)
    corr = np.eye(m, dtype=np.float64)

    for i in range(m):
        for j in range(i + 1, m):
            a = arrays[i]
            b = arrays[j]
            length = min(a.size, b.size)
            if length < 2:
                continue
            a_slice = a[-length:]
            b_slice = b[-length:]
            mask = ~(np.isnan(a_slice) | np.isnan(b_slice))
            if int(mask.sum()) < 2:
                continue
            x = a_slice[mask]
            y = b_slice[mask]
            sx = float(x.std(ddof=1))
            sy = float(y.std(ddof=1))
            if sx <= 1e-12 or sy <= 1e-12:
                continue
            c = float(((x - x.mean()) * (y - y.mean())).mean() / (sx * sy))
            corr[i, j] = c
            corr[j, i] = c

    warnings: list[tuple[str, str, float]] = []
    for i in range(m):
        for j in range(i + 1, m):
            if abs(corr[i, j]) > 0.8:
                warnings.append((names[i], names[j], float(corr[i, j])))
    warnings.sort(key=lambda t: -abs(t[2]))
    return (names, corr, warnings)
