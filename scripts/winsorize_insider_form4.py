"""Winsorize the aggregated Form 4 insider parquet to neutralize outliers.

Run after `fetch_insider_form4.py` whenever the raw aggregated parquet is
rebuilt. Apply global symmetric winsorize at [0.5%, 99.5%] on the
`net_dollars` column. Necessary because some Form 4 XML filings have
shares×price parsing errors (LLY 2025-11-14: -75.9B sell which is 12% of
market cap in one day, physically impossible — diagnosed as parser bug
pending root-cause).

Per-day cross-sectional winsorize is the textbook CMP 2012 approach but
our active-day fill rate is ~7 obs/day; the per-day quantile is too noisy.
Global winsorize at the same percentile is more stable for our sample
size.

Idempotent: running twice has no further effect since the second pass
finds nothing outside the already-clipped bounds.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PARQUET = (
    Path(__file__).resolve().parent.parent
    / "alpha_agent"
    / "data"
    / "insider_form4_sp500_v3.parquet"
)


def main() -> int:
    if not PARQUET.exists():
        print(f"missing {PARQUET}; run fetch_insider_form4.py first", file=sys.stderr)
        return 1

    df = pd.read_parquet(PARQUET)
    print(f"before: {len(df)} rows")

    # 1. drop rows with un-parseable transaction_date (Form 4 occasionally
    #    has 2-digit year typos that pandas reads as year 0025 etc.)
    parsed = pd.to_datetime(df["transaction_date"], errors="coerce")
    bad_dates = int(parsed.isna().sum())
    if bad_dates:
        df = df.loc[parsed.notna()].copy()
        print(f"  dropped {bad_dates} rows with unparseable date")

    # 2. global symmetric winsorize at [0.5%, 99.5%]
    lo, hi = df["net_dollars"].quantile([0.005, 0.995])
    n_lo = int((df["net_dollars"] < lo).sum())
    n_hi = int((df["net_dollars"] > hi).sum())
    print(f"  clip lo={lo:,.0f} (n={n_lo})  hi={hi:,.0f} (n={n_hi})")
    df["net_dollars"] = df["net_dollars"].clip(lower=lo, upper=hi)

    print(f"after clip: min={df['net_dollars'].min():,.0f}  "
          f"max={df['net_dollars'].max():,.0f}")

    df.to_parquet(PARQUET, index=False)
    print(f"saved → {PARQUET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
