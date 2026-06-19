"""RSRS factor validation (research, pre-integration).

RSRS (Resistance Support Relative Strength, 光大证券 2017): for each day, run an
OLS regression of the trailing-N daily HIGHs on the trailing-N daily LOWs; the
slope beta is the raw RSRS. Standardize to a z-score over a trailing M-day
window. A high z-score => resistance rising faster than support => bullish.

This script measures whether RSRS_zscore has CROSS-SECTIONAL predictive power on
US equities (apples-to-apples with how alpha_agent grades its other factors:
walk-forward Spearman rank IC of the factor vs forward returns), BEFORE wiring it
into the live pipeline. Note 4's A-share params are N=18, M=600, threshold 0.8;
daily IC there is only 0.01-0.05 (it is a weak-alone timing factor). We test
N=18 with M in {126, 252} (our OHLC history is shorter than 600 trading days) at
forward horizons 5 and 20.

Run (proxies unset so yfinance/httpx work under ClashX):
    unset ALL_PROXY HTTP_PROXY HTTPS_PROXY all_proxy
    python scripts/rsrs_validation.py
"""
from __future__ import annotations

import json
import time
import urllib.request

import numpy as np
import pandas as pd

# Local-IP yfinance is hard rate-limited, so pull OHLC from our deployed backend
# (Vercel IP), which serves the same get_ticker().history() at period=2y.
_BACKEND = "https://alpha-api.bobbyzhong.com/api/stock/{tk}/ohlcv?period=2y"

# ~35 liquid large/mid caps across sectors (cross-section big enough for a
# meaningful rank IC; kept modest to avoid rate-limiting yfinance on the backend).
SAMPLE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AVGO", "ORCL",
    "JPM", "BAC", "WFC", "GS", "V", "MA", "AXP",
    "UNH", "JNJ", "LLY", "PFE", "MRK", "ABBV", "TMO",
    "XOM", "CVX", "COP", "CAT", "DE", "HON", "GE",
    "WMT", "COST", "PG", "KO", "MCD", "HD",
]

N_REG = 18          # regression window (RSRS slope)
FWD_HORIZONS = (5, 20)
M_WINDOWS = (126, 252)
_MIN_XSEC = 8       # min tickers on a day for a meaningful cross-sectional IC


def _rolling_slope(high: pd.Series, low: pd.Series, n: int) -> pd.Series:
    """Trailing-n OLS slope of high on low: beta = cov(low,high)/var(low)."""
    cov = low.rolling(n).cov(high)
    var = low.rolling(n).var()
    return cov / var.replace(0.0, np.nan)


def _fetch_ohlc(ticker: str) -> pd.DataFrame | None:
    try:
        req = urllib.request.Request(
            _BACKEND.format(tk=ticker), headers={"User-Agent": "rsrs-validation"}
        )
        with urllib.request.urlopen(req, timeout=40) as r:  # noqa: S310 - fixed https host
            bars = json.loads(r.read()).get("bars", [])
        if not bars:
            print(f"  empty: {ticker}")
            return None
        df = pd.DataFrame(bars)
        if not {"high", "low", "close"}.issubset(df.columns):
            return None
        df = df.dropna(subset=["high", "low", "close"])
        out = df[["high", "low", "close"]].rename(
            columns={"high": "High", "low": "Low", "close": "Close"}
        )
        out.index = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
        return out
    except Exception as e:  # noqa: BLE001 - research script, just report + skip
        print(f"  fetch fail {ticker}: {type(e).__name__}: {e}")
        return None


def _spearman(a: pd.Series, b: pd.Series) -> float:
    """Spearman rank correlation of two aligned series (manual: rank then Pearson)."""
    m = a.notna() & b.notna()
    if m.sum() < _MIN_XSEC:
        return np.nan
    return a[m].rank().corr(b[m].rank())


def main() -> int:
    print(f"fetching 2y OHLC for {len(SAMPLE)} tickers ...")
    z_by_m: dict[int, dict[str, pd.Series]] = {m: {} for m in M_WINDOWS}
    fwd_by_h: dict[int, dict[str, pd.Series]] = {h: {} for h in FWD_HORIZONS}
    ok = 0
    for tk in SAMPLE:
        df = _fetch_ohlc(tk)
        if df is None or len(df) < max(M_WINDOWS) + N_REG + max(FWD_HORIZONS):
            continue
        ok += 1
        beta = _rolling_slope(df["High"], df["Low"], N_REG)
        for m in M_WINDOWS:
            mu = beta.rolling(m).mean()
            sd = beta.rolling(m).std()
            z_by_m[m][tk] = (beta - mu) / sd.replace(0.0, np.nan)
        for h in FWD_HORIZONS:
            fwd_by_h[h][tk] = df["Close"].shift(-h) / df["Close"] - 1.0
        time.sleep(1.5)
    print(f"usable tickers: {ok}/{len(SAMPLE)}\n")
    if ok < _MIN_XSEC:
        print("too few tickers fetched; aborting")
        return 1

    print(f"{'M':>4} {'horizon':>7} {'mean_IC':>8} {'IC_IR':>7} {'%pos':>6} {'days':>5}")
    results = []
    for m in M_WINDOWS:
        zpanel = pd.DataFrame(z_by_m[m])  # dates x tickers
        for h in FWD_HORIZONS:
            fpanel = pd.DataFrame(fwd_by_h[h]).reindex(zpanel.index)
            ics = [
                _spearman(zpanel.loc[d], fpanel.loc[d])
                for d in zpanel.index
            ]
            ics = pd.Series(ics).dropna()
            if ics.empty:
                continue
            mean_ic = ics.mean()
            ic_ir = mean_ic / ics.std() if ics.std() else np.nan
            pct_pos = (ics > 0).mean()
            results.append((m, h, mean_ic, ic_ir, pct_pos, len(ics)))
            print(f"{m:>4} {h:>7} {mean_ic:>8.4f} {ic_ir:>7.3f} {pct_pos:>6.1%} {len(ics):>5}")

    print("\nreference: alpha_agent 'factor' signal ~0.087 IC @20d (council #4).")
    print("RSRS read: |mean_IC|>=~0.02 with %pos clearly off 50% => has cross-sectional")
    print("signal worth fusing (weak-alone is expected per Note 4); near-zero => skip.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
