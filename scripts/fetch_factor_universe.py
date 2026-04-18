"""
Fetch 1y OHLCV for the factor-backtest universe and write parquet.

Usage:
    python3 scripts/fetch_factor_universe.py
    # writes alpha_agent/data/factor_universe_1y.parquet

Universe: 36 US large/mid caps spanning megacap, tech-adjacent, and
stablecoin-ecosystem names; plus SPY as benchmark.

Design notes:
- yfinance is used at build time only (not in serverless). Committed
  parquet is the source of truth at runtime — see
  `alpha_agent/factor_engine/universe_parquet.py` for the lazy loader.
- Long format ("date", "ticker", "open", "high", "low", "close",
  "volume") keeps the file compact (~150 KB) and groups cleanly by
  ticker for vectorized ops.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

UNIVERSE: tuple[str, ...] = (
    # Base 20 megacaps
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
    "META", "TSLA", "AVGO", "BRK-B", "JPM",
    "V", "XOM", "UNH", "WMT", "MA",
    "HD", "LLY", "JNJ", "PG", "KO",
    # Tech 10
    "AMD", "INTC", "CRM", "ORCL", "ADBE",
    "NFLX", "CSCO", "QCOM", "SNOW", "PLTR",
    # Stablecoin / crypto-adjacent 6 (XYZ = Block Inc, formerly SQ)
    "COIN", "MSTR", "HOOD", "PYPL", "BLK", "XYZ",
)
BENCHMARK: str = "SPY"
PERIOD: str = "1y"
INTERVAL: str = "1d"

OUT_PATH = Path(__file__).resolve().parent.parent / "alpha_agent" / "data" / "factor_universe_1y.parquet"


def fetch_one(ticker: str) -> pd.DataFrame:
    df = yf.Ticker(ticker).history(period=PERIOD, interval=INTERVAL, auto_adjust=True)
    if df.empty:
        raise RuntimeError(f"yfinance returned empty frame for {ticker!r}")
    df = df.rename(columns=str.lower).reset_index()
    df["date"] = pd.to_datetime(df["Date" if "Date" in df.columns else "date"]).dt.strftime("%Y-%m-%d")
    df["ticker"] = ticker
    return df[["date", "ticker", "open", "high", "low", "close", "volume"]]


def main() -> int:
    all_tickers = list(UNIVERSE) + [BENCHMARK]
    frames: list[pd.DataFrame] = []
    for i, tkr in enumerate(all_tickers, 1):
        print(f"[{i}/{len(all_tickers)}] fetching {tkr} ...", flush=True)
        try:
            frames.append(fetch_one(tkr))
        except Exception as e:
            print(f"  WARN: {tkr} failed: {type(e).__name__}: {e}", file=sys.stderr)

    if not frames:
        print("ERROR: no frames fetched — aborting", file=sys.stderr)
        return 1

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["ticker", "date"]).reset_index(drop=True)
    print(f"Combined shape: {combined.shape}; tickers: {combined['ticker'].nunique()}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(OUT_PATH, index=False, compression="snappy")
    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"Wrote {OUT_PATH} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
