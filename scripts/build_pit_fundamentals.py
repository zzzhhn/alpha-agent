"""Build the point-in-time fundamentals parquet (T1.1 Step 1 of v4).

Two execution modes:

  1. **Live yfinance** (preferred): pulls quarterly_income_stmt /
     quarterly_balance_sheet / quarterly_cashflow + earnings_dates per
     ticker. Real `filing_date` from the announcement timestamp.
     `python -m scripts.build_pit_fundamentals --mode live`

  2. **Recover from legacy panel** (fallback when yfinance is rate-limited):
     reads `factor_universe_sp100_v2.parquet`, identifies per-ticker fiscal
     quarter transition dates (when fundamental values change), treats those
     as `report_period`, and assigns `filing_date = report_period + 45d`
     (the conservative US 10-Q deadline). This recovers ~30 days of
     lookahead-bias correction without new network calls.
     `python -m scripts.build_pit_fundamentals --mode recover`

Output: `alpha_agent/data/fundamentals_pit.parquet`. Columns:
    ticker | report_period | filing_date | <20 fundamental fields>

Step 2 (next session) will consume this in `_load_panel()` and produce
PIT-aligned (T, N) arrays per fundamental field — replacing the broadcast
snapshot that currently leaks future earnings into past rows.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import pandas as pd

from alpha_agent.data.fundamentals_fetcher import (
    FALLBACK_LAG_DAYS,
    FUNDAMENTAL_FIELDS,
    fetch_all_pit_fundamentals,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_PARQUET = REPO_ROOT / "alpha_agent" / "data" / "factor_universe_sp100_v2.parquet"
OUTPUT_PARQUET = REPO_ROOT / "alpha_agent" / "data" / "fundamentals_pit.parquet"

logger = logging.getLogger(__name__)


# ── Live yfinance mode ─────────────────────────────────────────────────────

def build_live(tickers: list[str], throttle_seconds: float) -> pd.DataFrame:
    """Pull fresh PIT fundamentals via yfinance with real earnings_dates."""
    logger.info("Live mode: pulling %d tickers (throttle %.1fs)...", len(tickers), throttle_seconds)
    return fetch_all_pit_fundamentals(tickers, throttle_seconds=throttle_seconds)


# ── Recovery mode (legacy panel → PIT) ─────────────────────────────────────

def _ticker_quarterly_periods(sub: pd.DataFrame) -> list[pd.Timestamp]:
    """Identify fiscal quarter transitions in a ticker's daily fundamentals.

    Strategy: take any non-null fundamental field that has at least 2
    distinct values; each row where the value differs from the prior row
    marks a new quarter (the legacy panel's join was forward-fill on
    `report_period` so transitions land exactly on quarter ends).

    Falls back to scanning each field if the first one is constant.
    Returns sorted ascending list of transition dates.
    """
    sub = sub.sort_values("date").reset_index(drop=True)
    candidate_fields = [f for f in FUNDAMENTAL_FIELDS if f in sub.columns]

    for f in candidate_fields:
        series = sub[f]
        if series.notna().sum() < 2:
            continue
        # Mark rows where value strictly differs from the previous row
        # (NaN → value, value → other value, value → NaN all counted)
        prev = series.shift(1)
        changed = (series != prev) & ~(series.isna() & prev.isna())
        # The very first row's "change" flag is True by construction but
        # represents "data starts here", which we treat as the latest
        # known quarter at panel start.
        transition_dates = pd.to_datetime(sub.loc[changed, "date"])
        if len(transition_dates) > 0:
            return sorted(set(transition_dates))

    return []


def _ticker_pit_rows(sub: pd.DataFrame, periods: list[pd.Timestamp]) -> list[dict]:
    """Build one row per quarter for this ticker: report_period, filing_date,
    and the fundamental values that were live just AFTER each transition."""
    sub = sub.sort_values("date").reset_index(drop=True)
    rows: list[dict] = []
    for period in periods:
        # Find the first row at or after this period to capture the value
        # that the legacy panel attached to this period.
        match = sub[pd.to_datetime(sub["date"]) >= period]
        if match.empty:
            continue
        snapshot = match.iloc[0]
        rec: dict = {
            "ticker": sub["ticker"].iloc[0],
            "report_period": period.strftime("%Y-%m-%d"),
            "filing_date": (period + pd.Timedelta(days=FALLBACK_LAG_DAYS)).strftime("%Y-%m-%d"),
        }
        for f in FUNDAMENTAL_FIELDS:
            if f in sub.columns:
                v = snapshot.get(f)
                rec[f] = float(v) if pd.notna(v) else None
            else:
                rec[f] = None
        rows.append(rec)
    return rows


def build_recover(legacy_parquet: Path) -> pd.DataFrame:
    """Reconstruct PIT fundamentals from the legacy panel's transition dates."""
    if not legacy_parquet.exists():
        raise FileNotFoundError(f"Legacy panel not found: {legacy_parquet}")
    logger.info("Recovery mode: reading %s", legacy_parquet)
    df = pd.read_parquet(legacy_parquet)
    n_tickers = df["ticker"].nunique()
    logger.info("  %d rows, %d tickers, date range %s → %s",
                len(df), n_tickers, df["date"].min(), df["date"].max())

    out_rows: list[dict] = []
    for tk, sub in df.groupby("ticker"):
        periods = _ticker_quarterly_periods(sub)
        if not periods:
            logger.warning("  %s: no fundamental transitions detected", tk)
            continue
        ticker_rows = _ticker_pit_rows(sub, periods)
        out_rows.extend(ticker_rows)
        logger.info("  %s: %d periods", tk, len(periods))

    if not out_rows:
        return pd.DataFrame(
            columns=["ticker", "report_period", "filing_date", *FUNDAMENTAL_FIELDS]
        )
    return pd.DataFrame(out_rows).sort_values(["ticker", "report_period"]).reset_index(drop=True)


# ── Validation ─────────────────────────────────────────────────────────────

def validate_output(df: pd.DataFrame) -> None:
    """Self-check before write: schema, non-empty, lag-day sanity."""
    assert "ticker" in df.columns, "missing ticker column"
    assert "report_period" in df.columns, "missing report_period column"
    assert "filing_date" in df.columns, "missing filing_date column"
    assert len(df) > 0, "empty output — fetch must have failed"

    # All filing_dates must be strictly later than their report_periods
    rp = pd.to_datetime(df["report_period"])
    fd = pd.to_datetime(df["filing_date"])
    bad = (fd <= rp).sum()
    assert bad == 0, f"{bad} row(s) have filing_date <= report_period — bug"

    # Lag distribution sanity
    lag = (fd - rp).dt.days
    assert lag.min() > 0
    assert lag.max() < 200, f"max lag {lag.max()}d is suspiciously large"

    n_tickers = df["ticker"].nunique()
    n_quarters = len(df)
    field_count = sum(1 for c in df.columns if c in FUNDAMENTAL_FIELDS)
    nonnull_pct = (
        df[[c for c in FUNDAMENTAL_FIELDS if c in df.columns]].notna().sum().sum()
        / (n_quarters * field_count)
    ) if field_count > 0 else 0.0
    logger.info(
        "Validation pass: %d tickers, %d quarters, %d fields, "
        "lag avg %.1fd (min %dd, max %dd), %.1f%% non-null",
        n_tickers, n_quarters, field_count,
        float(lag.mean()), int(lag.min()), int(lag.max()), 100.0 * nonnull_pct,
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=("live", "recover"), default="recover",
                    help="live = yfinance fresh pull (real filing_date); "
                         "recover = reconstruct from legacy panel + 45d fallback")
    ap.add_argument("--tickers", nargs="+", default=None,
                    help="Override ticker list (live mode only). "
                         "Defaults to legacy panel's ticker set.")
    ap.add_argument("--throttle", type=float, default=0.3,
                    help="yfinance per-ticker sleep seconds (live mode only)")
    ap.add_argument("--out", type=Path, default=OUTPUT_PARQUET,
                    help=f"Output parquet path (default: {OUTPUT_PARQUET})")
    args = ap.parse_args()

    if args.mode == "live":
        if args.tickers:
            tickers = args.tickers
        else:
            legacy = pd.read_parquet(LEGACY_PARQUET)
            tickers = sorted(legacy["ticker"].unique().tolist())
            tickers = [t for t in tickers if t != "SPY"]  # benchmark, no statements
        df = build_live(tickers, throttle_seconds=args.throttle)
    else:
        df = build_recover(LEGACY_PARQUET)

    validate_output(df)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)
    logger.info("Wrote %s (%d rows × %d cols, %.1f KB)",
                args.out, len(df), len(df.columns),
                args.out.stat().st_size / 1024.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
