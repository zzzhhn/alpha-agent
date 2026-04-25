"""Fetch SP100 OHLCV + fundamentals + sector/industry, write extended parquet.

Output: alpha_agent/data/factor_universe_sp100_v2.parquet

Schema (long format, date+ticker as composite key):
    date, ticker
    open, high, low, close, volume          [yfinance daily, 250d]
    cap, sector, industry                    [yfinance info, snapshot, broadcast]
    revenue, net_income, ebitda, eps,        [financialdatasets quarterly, fwd-filled]
    equity, total_assets, free_cash_flow, gross_profit

Rate-limit hygiene:
  * yfinance: batched download, 1 request for OHLCV
  * yfinance info: sequential with 0.2s sleep
  * financialdatasets: sequential with 0.5s sleep, 3 endpoints per ticker

Usage:
    # smoke first (10 tickers, ~30s)
    python3 scripts/fetch_sp100_v2.py --subset sp10
    # full run (100 tickers + SPY, ~25min)
    python3 scripts/fetch_sp100_v2.py --subset sp100
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

# ── Universe ─────────────────────────────────────────────────────────────────
SP100_TICKERS: tuple[str, ...] = (
    # Megacap tech (15)
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "AVGO",
    "ORCL", "CRM", "ADBE", "NFLX", "CSCO", "AMD",
    # Megacap fin (10)
    "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "BLK", "AXP", "C",
    # Healthcare (10)
    "UNH", "LLY", "JNJ", "ABBV", "MRK", "PFE", "TMO", "ABT", "DHR", "BMY",
    # Consumer (10)
    "WMT", "HD", "PG", "KO", "PEP", "COST", "MCD", "NKE", "SBUX", "TGT",
    # Energy/Industrial (10)
    "XOM", "CVX", "COP", "GE", "CAT", "BA", "HON", "UPS", "RTX", "LMT",
    # Tech-2 (10)
    "INTC", "QCOM", "TXN", "IBM", "INTU", "AMAT", "MU", "LRCX", "KLAC", "ADI",
    # Other (15)
    "DIS", "VZ", "T", "CMCSA", "TMUS", "NEE", "DUK", "SO", "PLD", "AMT",
    "SPGI", "MCO", "MMC", "AON", "PGR",
    # Stablecoin/crypto-adjacent (5) — reuse from old universe
    "COIN", "MSTR", "PYPL", "HOOD", "PLTR",
    # Others to reach 100 (15)
    "PM", "MO", "BRK-B", "BX", "SCHW", "NOW", "SNOW", "PANW",
    "REGN", "VRTX", "ISRG", "GILD", "MDT", "SYK", "BSX",
)
SP10_TICKERS = SP100_TICKERS[:10]
SP30_TICKERS = SP100_TICKERS[:30]
BENCHMARK = "SPY"
PERIOD = "1y"

OUT_PATH = (
    Path(__file__).resolve().parent.parent
    / "alpha_agent"
    / "data"
    / "factor_universe_sp100_v2.parquet"
)

# 8 fundamental fields. yfinance row labels → our canonical names.
# Each tuple is (canonical, list of acceptable yfinance row names — first hit wins).
# Canonical names match the WorldQuant fundamentals catalog.
# Each entry: (canonical, [yfinance row name candidates], statement_kind)
# statement_kind: "income" / "balance" / "cashflow"
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
    ("cash_and_equivalents",["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"], "balance"),
    ("retained_earnings",   ["Retained Earnings"],                                                   "balance"),
    ("goodwill",            ["Goodwill", "Goodwill And Other Intangible Assets"],                    "balance"),
    # ── cash flow
    ("free_cash_flow",      ["Free Cash Flow"],                                                      "cashflow"),
    ("operating_cash_flow", ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"], "cashflow"),
    ("investing_cash_flow", ["Investing Cash Flow", "Cash Flow From Continuing Investing Activities"], "cashflow"),
]
FUNDAMENTAL_FIELDS = [c for c, _, _ in FUNDAMENTAL_MAP]


# ── OHLCV fetch (yfinance) ──────────────────────────────────────────────────


def _fetch_one_ohlcv(tk: str) -> pd.DataFrame | None:
    """Per-ticker fallback when batch download drops a name."""
    try:
        df = yf.Ticker(tk).history(period=PERIOD, interval="1d", auto_adjust=True)
        if df is None or df.empty:
            return None
        df = df.rename(columns=str.lower).reset_index()
        df["date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
        df["ticker"] = tk
        return df[["date", "ticker", "open", "high", "low", "close", "volume"]].dropna(subset=["close"])
    except Exception:
        return None


def fetch_ohlcv(tickers: list[str]) -> pd.DataFrame:
    """Bulk yfinance download → long-format DataFrame, with per-ticker retry."""
    print(f"[ohlcv] batch downloading {len(tickers)} tickers...", flush=True)
    df = yf.download(
        tickers, period=PERIOD, interval="1d", auto_adjust=True,
        group_by="ticker", progress=False, threads=True,
    )
    frames: list[pd.DataFrame] = []
    missing: list[str] = []
    for tk in tickers:
        try:
            if tk in df.columns.get_level_values(0):
                sub = df[tk].rename(columns=str.lower).reset_index()
                sub["date"] = pd.to_datetime(sub["Date"]).dt.strftime("%Y-%m-%d")
                sub["ticker"] = tk
                sub = sub[["date", "ticker", "open", "high", "low", "close", "volume"]].dropna(subset=["close"])
                if not sub.empty:
                    frames.append(sub)
                    continue
        except Exception:
            pass
        missing.append(tk)
    if missing:
        print(f"[ohlcv] retrying {len(missing)} missing per-ticker: {missing[:5]}...", flush=True)
        for tk in missing:
            sub = _fetch_one_ohlcv(tk)
            if sub is not None and not sub.empty:
                frames.append(sub)
                print(f"  recovered {tk}: {len(sub)}d", flush=True)
            else:
                print(f"  STILL FAILED {tk}", file=sys.stderr)
            time.sleep(0.2)
    out = pd.concat(frames, ignore_index=True)
    n_tk = out["ticker"].nunique()
    print(f"[ohlcv] {n_tk}/{len(tickers)} tickers, {len(out)} rows", flush=True)
    return out


# ── Sector / cap snapshot (yfinance info) ──────────────────────────────────


def fetch_meta(tickers: list[str]) -> dict[str, dict]:
    """Per-ticker {sector, industry, market_cap} snapshot from yfinance info."""
    out: dict[str, dict] = {}
    for i, tk in enumerate(tickers, 1):
        try:
            info = yf.Ticker(tk).info
            out[tk] = {
                "sector":   info.get("sector", "Unknown"),
                "industry": info.get("industry", "Unknown"),
                "cap":      info.get("marketCap"),
                "exchange": info.get("exchange", "Unknown"),
                "currency": info.get("currency", "Unknown"),
            }
            print(f"[meta {i}/{len(tickers)}] {tk}: {out[tk]['sector']:20s} {out[tk]['exchange']:8s} cap={out[tk]['cap']}", flush=True)
        except Exception as e:
            print(f"[meta {i}/{len(tickers)}] {tk}: FAIL {type(e).__name__}: {e}", file=sys.stderr)
            out[tk] = {"sector": "Unknown", "industry": "Unknown", "cap": None, "exchange": "Unknown", "currency": "Unknown"}
        time.sleep(0.2)
    return out


# ── Fundamentals (yfinance, free) ───────────────────────────────────────────


def _pick_row(stmt: pd.DataFrame, candidates: list[str]) -> pd.Series | None:
    """Return the first matching row from `candidates` in `stmt` (or None)."""
    for name in candidates:
        if name in stmt.index:
            return stmt.loc[name]
    return None


def fetch_fundamentals(ticker: str) -> pd.DataFrame:
    """Pull 4-5 quarterly statements and merge into a (date × fields) DataFrame."""
    t = yf.Ticker(ticker)
    qis = t.quarterly_income_stmt   # rows = field names, cols = quarter-end dates
    qbs = t.quarterly_balance_sheet
    qcf = t.quarterly_cashflow

    if qis is None or qis.empty:
        return pd.DataFrame()

    # Union of all quarter-end dates across the three statements
    all_dates = sorted(
        set(list(qis.columns) + list(qbs.columns) + list(qcf.columns)),
        reverse=True,
    )
    rows = []
    for d in all_dates:
        rec = {"date": pd.Timestamp(d).strftime("%Y-%m-%d")}
        for canonical, candidates, kind in FUNDAMENTAL_MAP:
            stmt = qis if kind == "income" else qbs if kind == "balance" else qcf
            row = _pick_row(stmt, candidates)
            val = row.get(d) if row is not None else None
            rec[canonical] = float(val) if pd.notna(val) else None
        rows.append(rec)
    out = pd.DataFrame(rows)
    out["ticker"] = ticker
    return out


def fetch_all_fundamentals(tickers: list[str]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for i, tk in enumerate(tickers, 1):
        try:
            df = fetch_fundamentals(tk)
            if df.empty:
                print(f"[fund {i}/{len(tickers)}] {tk}: empty (yfinance returned nothing)", file=sys.stderr)
                continue
            frames.append(df)
            non_null = df.drop(columns=["date", "ticker"]).notna().sum().sum()
            print(f"[fund {i}/{len(tickers)}] {tk}: {len(df)}q × {non_null} non-null cells", flush=True)
        except Exception as e:
            print(f"[fund {i}/{len(tickers)}] {tk}: FAIL {type(e).__name__}: {e}", file=sys.stderr)
        time.sleep(0.3)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ── Assembly ────────────────────────────────────────────────────────────────


def assemble(
    ohlcv: pd.DataFrame, meta: dict[str, dict], fund: pd.DataFrame,
) -> pd.DataFrame:
    """Merge OHLCV + meta + forward-filled fundamentals into one long-form panel."""
    # 1. Attach sector/industry/cap/exchange/currency from meta (broadcast)
    ohlcv["sector"]   = ohlcv["ticker"].map(lambda t: meta.get(t, {}).get("sector", "Unknown"))
    ohlcv["industry"] = ohlcv["ticker"].map(lambda t: meta.get(t, {}).get("industry", "Unknown"))
    ohlcv["cap"]      = ohlcv["ticker"].map(lambda t: meta.get(t, {}).get("cap"))
    ohlcv["exchange"] = ohlcv["ticker"].map(lambda t: meta.get(t, {}).get("exchange", "Unknown"))
    ohlcv["currency"] = ohlcv["ticker"].map(lambda t: meta.get(t, {}).get("currency", "USD"))

    # 2. Forward-fill fundamentals into daily timeline per ticker
    if fund.empty:
        for f in FUNDAMENTAL_FIELDS:
            ohlcv[f] = pd.NA
        return ohlcv

    fund = fund.sort_values(["ticker", "date"]).reset_index(drop=True)
    fund["date"] = pd.to_datetime(fund["date"]).dt.strftime("%Y-%m-%d")

    merged_chunks = []
    for tk, sub in ohlcv.groupby("ticker"):
        f = fund[fund["ticker"] == tk].drop(columns=["ticker"])
        if f.empty:
            for col in FUNDAMENTAL_FIELDS:
                sub[col] = pd.NA
            merged_chunks.append(sub)
            continue
        sub = sub.sort_values("date").reset_index(drop=True)
        f = f.sort_values("date").reset_index(drop=True)
        # merge_asof joins each daily row with the latest fundamental at-or-before
        sub_d = pd.to_datetime(sub["date"])
        f_d = pd.to_datetime(f["date"])
        sub2 = sub.assign(_date=sub_d)
        f2 = f.assign(_date=f_d).drop(columns=["date"])
        m = pd.merge_asof(
            sub2.sort_values("_date"),
            f2.sort_values("_date"),
            on="_date",
            direction="backward",
        ).drop(columns=["_date"])
        merged_chunks.append(m)
    return pd.concat(merged_chunks, ignore_index=True)


# ── Main ────────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subset", choices=("sp10", "sp30", "sp100"), default="sp10")
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--skip-fundamentals", action="store_true",
                    help="OHLCV+meta only, no FDS calls (faster smoke)")
    args = ap.parse_args()

    if args.subset == "sp10":
        universe = list(SP10_TICKERS)
    elif args.subset == "sp30":
        universe = list(SP30_TICKERS)
    else:
        universe = list(SP100_TICKERS)
    all_tickers = universe + [BENCHMARK]

    t0 = time.time()
    ohlcv = fetch_ohlcv(all_tickers)
    meta = fetch_meta(all_tickers)

    fund = pd.DataFrame()
    if not args.skip_fundamentals:
        # Skip benchmark for fundamentals (SPY is an ETF, no statements)
        fund = fetch_all_fundamentals(universe)

    panel = assemble(ohlcv, meta, fund)
    panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(out_path, index=False, compression="snappy")

    size_kb = out_path.stat().st_size / 1024
    elapsed = time.time() - t0
    print(f"\n=== SUMMARY ===")
    print(f"  panel shape: {panel.shape}")
    print(f"  tickers:     {panel['ticker'].nunique()}")
    print(f"  date range:  {panel['date'].min()} → {panel['date'].max()}")
    print(f"  fund non-null per field:")
    for f in FUNDAMENTAL_FIELDS:
        if f in panel.columns:
            non_null = panel[f].notna().sum()
            print(f"    {f:20s}: {non_null}/{len(panel)} ({100*non_null/len(panel):.1f}%)")
    print(f"  output:      {out_path} ({size_kb:.1f} KB)")
    print(f"  elapsed:     {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
