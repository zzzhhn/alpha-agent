"""Point-in-time fundamentals fetcher (T1.1 of v4).

The legacy fundamentals pull in `scripts/fetch_sp100_v2.py` joins each
quarterly statement onto the daily timeline using the *fiscal quarter end*
as the date key. That is a structural look-ahead bias: a fiscal quarter
ending 2024-09-30 isn't actually known until the 10-Q is filed (~30-45
days later, sometimes longer). Backtests using `eps`, `revenue`,
`free_cash_flow`, etc. saw earnings up to ~45 days before they were public.

This module fixes that. For every ticker we pull:
  * `quarterly_income_stmt` / `quarterly_balance_sheet` / `quarterly_cashflow`
    — values keyed by `report_period` (fiscal quarter end)
  * `earnings_dates` — actual announcement timestamps (when EPS becomes public)

We then match each `report_period` to its first announcement date strictly
after it. Falls back to `report_period + 45d` (the conservative US 10-Q
deadline) when earnings_dates is missing or doesn't cover that quarter.

The output is a long-format DataFrame with one row per (ticker, report_period)
carrying both `report_period` and `filing_date`. The downstream Step 2 will
consume this in `_load_panel()` and produce a (T, N) array per fundamental
field where the value at row `t` for a ticker is "the most recent statement
whose `filing_date` ≤ panel_dates[t]" — the canonical PIT join.

This module does not write parquet itself; see `scripts/build_pit_fundamentals.py`
for the orchestration that calls into here per ticker.
"""
from __future__ import annotations

import logging
import time
from typing import Iterable

import pandas as pd

logger = logging.getLogger(__name__)

# yfinance row-label dialects → our canonical operand names. First match wins.
# Mirrors `scripts/fetch_sp100_v2.py:FUNDAMENTAL_MAP` so a swap-in is trivial.
FUNDAMENTAL_MAP: list[tuple[str, list[str], str]] = [
    # ── income statement
    ("revenue",             ["Total Revenue", "Operating Revenue"],                                  "income"),
    ("net_income_adjusted", ["Net Income", "Net Income Common Stockholders",
                             "Net Income From Continuing Operation Net Minority Interest"],         "income"),
    ("ebitda",              ["EBITDA", "Normalized EBITDA"],                                         "income"),
    ("eps",                 ["Diluted EPS", "Basic EPS"],                                            "income"),
    ("gross_profit",        ["Gross Profit"],                                                        "income"),
    ("operating_income",    ["Operating Income", "Total Operating Income As Reported"],              "income"),
    ("cost_of_goods_sold",  ["Cost Of Revenue", "Reconciled Cost Of Revenue"],                       "income"),
    ("ebit",                ["EBIT"],                                                                "income"),
    # ── balance sheet
    ("equity",              ["Common Stock Equity", "Stockholders Equity",
                             "Total Equity Gross Minority Interest"],                                "balance"),
    ("assets",              ["Total Assets"],                                                        "balance"),
    ("current_assets",      ["Current Assets"],                                                      "balance"),
    ("current_liabilities", ["Current Liabilities"],                                                 "balance"),
    ("long_term_debt",      ["Long Term Debt"],                                                      "balance"),
    ("short_term_debt",     ["Current Debt", "Short Term Debt"],                                     "balance"),
    ("cash_and_equivalents",["Cash And Cash Equivalents",
                             "Cash Cash Equivalents And Short Term Investments"],                    "balance"),
    ("retained_earnings",   ["Retained Earnings"],                                                   "balance"),
    ("goodwill",            ["Goodwill", "Goodwill And Other Intangible Assets"],                    "balance"),
    # ── cash flow
    ("free_cash_flow",      ["Free Cash Flow"],                                                      "cashflow"),
    ("operating_cash_flow", ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"], "cashflow"),
    ("investing_cash_flow", ["Investing Cash Flow", "Cash Flow From Continuing Investing Activities"], "cashflow"),
]
FUNDAMENTAL_FIELDS: list[str] = [c for c, _, _ in FUNDAMENTAL_MAP]

# Conservative US filing deadline: 10-Q must be filed within 40-45 days
# of quarter end for large accelerated filers. We use 45 as fallback when
# `earnings_dates` is unavailable or doesn't cover the quarter — this is
# strictly more conservative than the SEC deadline (i.e. data becomes
# available no earlier than this in the worst case).
FALLBACK_LAG_DAYS: int = 45

# Maximum plausible gap between fiscal quarter end and actual announcement.
# 120 days covers extreme cases (smaller firms with extensions, missed
# filings) without admitting unrelated future quarters.
MAX_ANNOUNCEMENT_GAP_DAYS: int = 120


def _pick_row(stmt: pd.DataFrame, candidates: Iterable[str]) -> pd.Series | None:
    """Return the first row whose label matches one of `candidates`, or None.

    yfinance occasionally renames rows between API versions ("EBIT" vs
    "Earnings Before Interest And Taxes"); the candidate list is a manual
    union of historical names so we don't bind to one specific version.
    """
    for name in candidates:
        if name in stmt.index:
            return stmt.loc[name]
    return None


def _resolve_filing_date(
    report_period: pd.Timestamp,
    earnings_dates: pd.DataFrame | None,
) -> pd.Timestamp:
    """Map a fiscal quarter end to the actual public announcement date.

    Strategy: pick the earliest entry in `earnings_dates` whose date strictly
    follows `report_period` and lies within MAX_ANNOUNCEMENT_GAP_DAYS. Falls
    back to `report_period + FALLBACK_LAG_DAYS` if no match.

    `earnings_dates` from yfinance is indexed by tz-aware UTC timestamps and
    can include future scheduled announcements; we coerce to date-naive UTC
    and filter strictly after report_period to handle that.
    """
    fallback = report_period + pd.Timedelta(days=FALLBACK_LAG_DAYS)
    if earnings_dates is None or earnings_dates.empty:
        return fallback

    idx = earnings_dates.index
    # Strip timezone for comparison; yfinance returns tz-aware (Eastern usually)
    if hasattr(idx, "tz") and idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    # Window: strictly after report_period, within MAX_ANNOUNCEMENT_GAP_DAYS
    window_end = report_period + pd.Timedelta(days=MAX_ANNOUNCEMENT_GAP_DAYS)
    candidates = idx[(idx > report_period) & (idx <= window_end)]
    if len(candidates) == 0:
        return fallback
    return pd.Timestamp(min(candidates))


def fetch_pit_fundamentals(ticker: str) -> pd.DataFrame:
    """Pull quarterly statements + earnings dates for one ticker.

    Returns a DataFrame with columns:
        ticker | report_period | filing_date | <20 fundamental fields>

    One row per fiscal quarter, ordered by `report_period` ascending. Empty
    DataFrame returned on yfinance failure or empty statement results — caller
    should treat that as "skip this ticker".

    NaN preservation: missing values stay as NaN. `filing_date` is always
    populated (falling back to +45d when earnings_dates is unavailable).

    Network: this is a synchronous yfinance call. Caller should add jitter
    sleep between tickers to avoid rate-limit blocks.
    """
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance not installed — pip install yfinance") from exc

    t = yf.Ticker(ticker)

    try:
        qis = t.quarterly_income_stmt
        qbs = t.quarterly_balance_sheet
        qcf = t.quarterly_cashflow
    except Exception as exc:
        logger.warning("yfinance statement fetch failed for %s: %s", ticker, exc)
        return pd.DataFrame()

    if (qis is None or qis.empty) and (qbs is None or qbs.empty) and (qcf is None or qcf.empty):
        logger.debug("yfinance returned empty statements for %s", ticker)
        return pd.DataFrame()

    # earnings_dates can fail on illiquid names; treat as None and fall back.
    try:
        ed = t.earnings_dates
        if ed is not None and not ed.empty:
            ed = ed.sort_index()
    except Exception as exc:
        logger.debug("earnings_dates fetch failed for %s: %s — using +%dd fallback",
                     ticker, exc, FALLBACK_LAG_DAYS)
        ed = None

    # Union of report periods across statements
    all_periods: set[pd.Timestamp] = set()
    for stmt in (qis, qbs, qcf):
        if stmt is not None and not stmt.empty:
            all_periods.update(pd.Timestamp(c) for c in stmt.columns)

    if not all_periods:
        return pd.DataFrame()

    rows: list[dict] = []
    for period in sorted(all_periods):
        filing_date = _resolve_filing_date(period, ed)
        rec: dict = {
            "ticker": ticker,
            "report_period": period.strftime("%Y-%m-%d"),
            "filing_date": filing_date.strftime("%Y-%m-%d"),
        }
        for canonical, candidates, kind in FUNDAMENTAL_MAP:
            stmt = qis if kind == "income" else qbs if kind == "balance" else qcf
            if stmt is None or stmt.empty:
                rec[canonical] = None
                continue
            row = _pick_row(stmt, candidates)
            if row is None:
                rec[canonical] = None
                continue
            val = row.get(period)
            rec[canonical] = float(val) if pd.notna(val) else None
        rows.append(rec)

    return pd.DataFrame(rows)


def fetch_all_pit_fundamentals(
    tickers: list[str], throttle_seconds: float = 0.3,
) -> pd.DataFrame:
    """Iterate `fetch_pit_fundamentals` over a ticker list with progress logging.

    Throttles between calls to avoid yfinance rate limits. Continues on
    per-ticker errors (logs but doesn't raise) — final concat covers
    whatever subset succeeded.
    """
    frames: list[pd.DataFrame] = []
    for i, tk in enumerate(tickers, 1):
        try:
            df = fetch_pit_fundamentals(tk)
            if df.empty:
                logger.warning("[%d/%d] %s: empty fundamentals", i, len(tickers), tk)
            else:
                frames.append(df)
                # Sanity: filing_date should always be > report_period
                bad = df[pd.to_datetime(df["filing_date"]) <= pd.to_datetime(df["report_period"])]
                if len(bad) > 0:
                    logger.error(
                        "[%d/%d] %s: %d row(s) with filing_date <= report_period — possible data error",
                        i, len(tickers), tk, len(bad),
                    )
                logger.info(
                    "[%d/%d] %s: %d quarters, %d non-null cells",
                    i, len(tickers), tk, len(df),
                    df.drop(columns=["ticker", "report_period", "filing_date"]).notna().sum().sum(),
                )
        except Exception as exc:
            logger.error("[%d/%d] %s FAIL: %s: %s", i, len(tickers), tk, type(exc).__name__, exc)
        time.sleep(throttle_seconds)

    if not frames:
        return pd.DataFrame(columns=["ticker", "report_period", "filing_date", *FUNDAMENTAL_FIELDS])
    return pd.concat(frames, ignore_index=True).sort_values(
        ["ticker", "report_period"]
    ).reset_index(drop=True)
