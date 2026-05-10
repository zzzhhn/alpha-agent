"""Manually refresh fixture files from real APIs.

Usage:
    python scripts/refresh_fixtures.py --ticker AAPL --date 2024-12-15

This is a manual ops tool — never run in CI. It hits real APIs (yfinance)
and writes frozen JSON snapshots into tests/fixtures/ for use in unit tests.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).parent.parent / "tests" / "fixtures"


def refresh_yfinance(ticker: str, date: str) -> None:
    out = ROOT / "yfinance"
    out.mkdir(parents=True, exist_ok=True)

    t = yf.Ticker(ticker)
    info = t.info
    info_path = out / f"{ticker}_info_{date}.json"
    info_path.write_text(json.dumps(info, default=str, indent=2))
    print(f"  Wrote {info_path}")

    df = yf.download(ticker, start="2024-01-01", end=date, progress=False, auto_adjust=True)
    if hasattr(df.columns, "get_level_values"):
        df.columns = df.columns.get_level_values(0)
    ohlcv_path = out / f"{ticker}_ohlcv_2024-01-01_{date}.json"
    df.reset_index().to_json(ohlcv_path, orient="records", date_format="iso")
    print(f"  Wrote {ohlcv_path}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Capture real API responses as test fixtures."
    )
    ap.add_argument("--ticker", required=True, help="Ticker symbol, e.g. AAPL")
    ap.add_argument("--date", required=True, help="As-of date ISO string, e.g. 2024-12-15")
    args = ap.parse_args()

    print(f"Refreshing fixtures for {args.ticker} @ {args.date} ...")
    refresh_yfinance(args.ticker, args.date)
    print(f"Done. Fixtures refreshed: {args.ticker} @ {args.date}")


if __name__ == "__main__":
    main()
