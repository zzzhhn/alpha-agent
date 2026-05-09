"""Pull 3-year SP500 OHLCV panel from Alpaca + sector/cap/fundamentals from WRDS.

Survivorship-bias-corrected: the universe is the union of all SP500
constituents over the past 3 years (per fja05680 historical components),
including delisted tickers like SIVB (2023-03), FRC (2023-05), CTLT, etc.

Output: alpaca_agent/data/factor_universe_sp500_v3.parquet
        alpha_agent/data/fundamentals_pit_sp500_v3.parquet
        (schema-compatible with v2; backtest engine auto-selects v3 when present)

Usage:
    python3 scripts/fetch_sp500_alpaca.py                  # full 3y pull
    python3 scripts/fetch_sp500_alpaca.py --years 1        # 1y for smoke
    python3 scripts/fetch_sp500_alpaca.py --skip-fundamentals  # OHLCV only
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

# ── Project layout ──────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "alpha_agent" / "data"
MEMBERSHIP_CSV = DATA_DIR / "sp500_membership_2026-01-17.csv"
OUT_PARQUET = DATA_DIR / "factor_universe_sp500_v3.parquet"
OUT_FUND_PARQUET = DATA_DIR / "fundamentals_pit_sp500_v3.parquet"

BENCHMARK = "SPY"
ALPACA_BATCH_SIZE = 100  # Alpaca docs say up to 200 symbols; 100 is a safe round


# ── 1. Universe construction (fja05680 union over the panel window) ────────


def compute_universe(start: datetime, end: datetime) -> list[str]:
    """Return the union of every ticker that was an SP500 constituent at any
    point in [start, end]. This is what makes the panel survivorship-bias-free.
    """
    df = pd.read_csv(MEMBERSHIP_CSV)
    df["date"] = pd.to_datetime(df["date"])
    # Keep snapshots that "covered" any day in the window: snap_date <= end
    # AND the next snap_date > start (or there's no next snapshot).
    df = df.sort_values("date").reset_index(drop=True)
    union: set[str] = set()
    for i, row in df.iterrows():
        snap_date = row["date"]
        next_snap = df.loc[i + 1, "date"] if i + 1 < len(df) else pd.Timestamp.max
        # This snapshot is "active" between [snap_date, next_snap).
        if next_snap > start and snap_date <= end:
            for tk in str(row["tickers"]).split(","):
                tk = tk.strip().replace(".", "-")  # normalize BRK.B → BRK-B
                if tk:
                    union.add(tk)
    return sorted(union)


# ── 2. OHLCV pull via Alpaca multi-symbol bars ──────────────────────────────


def _to_alpaca_form(t: str) -> str:
    """Yahoo dash form (BRK-B) → Alpaca dot form (BRK.B). Idempotent."""
    return t.replace("-", ".")


def _to_panel_form(t: str) -> str:
    """Alpaca dot form (BRK.B) → panel dash form (BRK-B), matching v2 schema
    so downstream code (existing SP100 panel, mask CSV) doesn't need changes."""
    return t.replace(".", "-")


def fetch_ohlcv_alpaca(tickers: list[str], start: datetime, end: datetime) -> pd.DataFrame:
    """Bulk pull daily bars from Alpaca, in batches of ALPACA_BATCH_SIZE.

    Convention handling: tickers come in as Yahoo dash form (BRK-B). We
    convert to dot form (BRK.B) at the Alpaca boundary, store back as dash
    in the output DataFrame so v2-schema downstream code is untouched.

    Robustness: if Alpaca returns 400 "invalid symbol: X", the bad symbol is
    dropped from the batch and the batch is re-issued. This handles edge
    cases where fja05680 lists a ticker that Alpaca's roster doesn't carry
    (rare — usually only very-recently-delisted issues with no asset record).

    Returns:
        Long-format DataFrame with columns: date, ticker, open, high, low,
        close, volume. Tickers in panel-form (dash for class shares).
    """
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.common.exceptions import APIError

    client = StockHistoricalDataClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_API_SECRET"],
    )

    frames: list[pd.DataFrame] = []
    dropped: list[str] = []
    n_batches = (len(tickers) + ALPACA_BATCH_SIZE - 1) // ALPACA_BATCH_SIZE

    for i in range(0, len(tickers), ALPACA_BATCH_SIZE):
        batch_panel = tickers[i : i + ALPACA_BATCH_SIZE]
        batch_alpaca = [_to_alpaca_form(t) for t in batch_panel]
        t0 = time.time()

        # Retry loop: drop invalid symbols one by one until the batch succeeds
        # (or shrinks to empty). Each "invalid symbol" message names exactly
        # one bad ticker; we strip it and retry.
        bars = None
        attempts = 0
        while batch_alpaca and bars is None:
            try:
                req = StockBarsRequest(
                    symbol_or_symbols=batch_alpaca,
                    timeframe=TimeFrame.Day,
                    start=start,
                    end=end,
                )
                bars = client.get_stock_bars(req)
            except APIError as e:
                msg = str(e)
                if "invalid symbol" in msg:
                    bad = msg.split("invalid symbol:")[-1].strip().rstrip("'\"} ")
                    if bad in batch_alpaca:
                        batch_alpaca.remove(bad)
                        dropped.append(_to_panel_form(bad))
                        attempts += 1
                        continue
                # Non-recoverable: rethrow
                raise

        if bars is None or bars.df is None or bars.df.empty:
            print(f"  batch {i//ALPACA_BATCH_SIZE+1}/{n_batches}: empty after {attempts} drops", flush=True)
            continue

        df = bars.df.reset_index()
        df["date"] = df["timestamp"].dt.strftime("%Y-%m-%d")
        df["ticker"] = df["symbol"].map(_to_panel_form)
        cols = ["date", "ticker", "open", "high", "low", "close", "volume"]
        df = df[cols]
        frames.append(df)
        n_uniq = df["ticker"].nunique()
        suffix = f", dropped {attempts}" if attempts > 0 else ""
        print(
            f"  batch {i//ALPACA_BATCH_SIZE+1}/{n_batches}: "
            f"{len(df):>7} rows, {n_uniq}/{len(batch_panel)} tickers in {time.time()-t0:.1f}s{suffix}",
            flush=True,
        )

    if dropped:
        print(f"  total invalid symbols dropped: {len(dropped)} ({dropped[:10]}{'...' if len(dropped)>10 else ''})", flush=True)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ── 3. WRDS sector + cap + fundamentals (single bulk SQL each) ─────────────


def fetch_wrds_metadata(tickers: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pull from WRDS:
        (a) Compustat `co_industry` style metadata → ticker, gsector, gind, cap
        (b) Compustat fundq → 12-quarter PIT fundamentals with RDQ filing date

    Returns (meta_df, fund_df).

    Schema lag: Compustat has ~3-month lag for quarterly statements (vs CRSP
    DSF's 16-month lag). Acceptable because fundamentals are reported quarterly
    anyway — a panel ending today uses the most recent reported quarter.
    """
    import wrds

    # wrds-py prompts for `input()` confirmation even when wrds_username is
    # set; in non-interactive contexts (Claude Code subprocess, CI, cron)
    # this raises EOFError. Workaround: pre-load PGPASSWORD from ~/.pgpass
    # so __make_sa_engine_conn() succeeds on the first attempt and the
    # interactive prompt path is never hit.
    # CRITICAL: read WRDS password from ~/.pgpass FIRST, before checking
    # env. dotenv loads Neon's PGPASSWORD into os.environ via .env (since
    # `vercel env pull`), which would otherwise shadow the WRDS password
    # we actually need here. We always prefer pgpass for WRDS.
    wrds_user = os.environ.get("WRDS_USERNAME", "zzzhhn")
    pw = None
    pgpass_path = Path.home() / ".pgpass"
    if pgpass_path.exists():
        for line in pgpass_path.read_text().splitlines():
            # pgpass format: host:port:db:user:password. Passwords can contain
            # colons (WRDS auto-generates them), so split with maxsplit=4 to
            # keep trailing colons inside the password field.
            parts = line.strip().split(":", 4)
            if len(parts) == 5 and "wharton" in parts[0] and parts[3] == wrds_user:
                pw = parts[4]
                break
    if not pw:
        raise RuntimeError(
            f"WRDS password not found in ~/.pgpass for user {wrds_user!r}. "
            f"Add a line: wrds-pgdata.wharton.upenn.edu:9737:wrds:{wrds_user}:<PASSWORD>"
        )
    print(f"[wrds] auth: user={wrds_user} pw_len={len(pw)} PGHOST={os.environ.get('PGHOST', '<unset>')}", flush=True)
    # The Neon-related env vars from `vercel env pull` shadow the WRDS
    # connection: wrds.Connection's __init__ reads PGHOST from os.environ,
    # which points to Neon (ep-broad-waterfall-...neon.tech) when .env is
    # loaded. Strip them locally for the WRDS connection only — restore
    # afterwards in case other code paths rely on them.
    saved_pg = {k: os.environ.pop(k, None) for k in
                ("PGHOST", "PGHOST_UNPOOLED", "PGUSER", "PGPASSWORD",
                 "PGDATABASE", "DATABASE_URL", "DATABASE_URL_UNPOOLED")}
    os.environ["PGPASSWORD"] = pw  # restore the WRDS password we just looked up
    try:
        db = wrds.Connection(
            wrds_username=wrds_user,
            wrds_password=pw,
            wrds_hostname="wrds-pgdata.wharton.upenn.edu",
            wrds_port=9737,
            wrds_dbname="wrds",
        )
    finally:
        for k, v in saved_pg.items():
            if v is not None:
                os.environ[k] = v

    # (a) Sector + industry + cap snapshot, one row per ticker.
    print("[wrds] fetching sector + cap snapshot...", flush=True)
    ticker_list = ",".join(f"'{t}'" for t in tickers)
    # Bundle C.1 (Phase A) fix — two SQL bugs corrected for SP500 ticker
    # coverage (was 82.7% → 96.6%):
    #
    # 1. `latest_link`: changed `ORDER BY ... linkenddt DESC` to
    #    `... DESC NULLS FIRST`. PostgreSQL's default is NULLS LAST for
    #    DESC, which sorted active links (linkenddt IS NULL) AFTER
    #    historical ones — DISTINCT ON then picked the wrong (historical)
    #    gvkey. Active links MUST come first.
    # 2. `latest_name`: now `DISTINCT ON (ticker)` (one PERMNO per ticker)
    #    plus `nameenddt > '2024-01-01'` to drop reused ticker codes from
    #    defunct historical companies (e.g. AAL was reused 3× since 1971;
    #    we want the active American Airlines PERMNO 21020, not the 1997
    #    All American Life Corp PERMNO 63845).
    # 3. CRSP `stocknames.ticker` collapses class shares into the root
    #    code (BRK-B → "BRK", BF-B → "BF"). Strip the class suffix at
    #    the SQL boundary so panel tickers map cleanly.
    crsp_form_tickers = [t.split("-")[0] if "-" in t else t for t in tickers]
    ticker_list = ",".join(f"'{t}'" for t in set(crsp_form_tickers))
    meta_sql = f"""
        WITH latest_link AS (
            SELECT DISTINCT ON (lpermno) gvkey, lpermno, linkdt, linkenddt
            FROM crsp.ccmxpf_linktable
            WHERE linktype IN ('LU', 'LC')
              AND linkprim IN ('P', 'C')
            ORDER BY lpermno, linkenddt DESC NULLS FIRST
        ),
        active_name AS (
            SELECT DISTINCT ON (ticker) permno, ticker
            FROM crsp.stocknames
            WHERE ticker IN ({ticker_list})
              AND nameenddt > '2024-01-01'
            ORDER BY ticker, nameenddt DESC NULLS FIRST
        )
        SELECT
            n.ticker,
            c.gvkey,
            c.gsector,
            c.gind,
            c.gsubind
        FROM active_name n
        JOIN latest_link l ON n.permno = l.lpermno
        JOIN comp.company c ON l.gvkey = c.gvkey
    """
    meta_df = db.raw_sql(meta_sql)
    print(f"  → {len(meta_df)} ticker→sector rows", flush=True)

    # (b) Quarterly fundamentals with RDQ filing date.
    print("[wrds] fetching 12-quarter Compustat fundq...", flush=True)
    if len(meta_df) == 0:
        return meta_df, pd.DataFrame()

    gvkey_list = ",".join(f"'{g}'" for g in meta_df["gvkey"].unique())
    # NB: Compustat fundq has only YTD ("y" suffix) versions for cash flow
    # statement items (oancfy, ivncfy, fincfy) — there are no native quarterly
    # cash flow fields. We omit those for v3 and let any factor that needs
    # them either (a) compute via YTD differencing in a follow-up, or (b)
    # fall back to the legacy v2 yfinance-derived fcf which IS quarterly.
    fund_sql = f"""
        SELECT
            f.gvkey, f.datadate, f.rdq,
            f.revtq    AS revenue,
            f.niq      AS net_income_adjusted,
            f.epspxq   AS eps,
            f.atq      AS assets,
            f.ceqq     AS equity,
            f.ltq      AS total_liabilities,
            f.cheq     AS cash_and_equivalents,
            f.dlttq    AS long_term_debt,
            f.dlcq     AS short_term_debt,
            f.cogsq                     AS cost_of_goods_sold,
            (f.revtq - f.cogsq)         AS gross_profit,
            f.oibdpq   AS ebitda,
            f.oiadpq   AS operating_income,
            f.req      AS retained_earnings,
            f.gdwlq    AS goodwill,
            f.actq     AS current_assets,
            f.lctq     AS current_liabilities,
            f.cshoq    AS shares_outstanding
        FROM comp.fundq f
        WHERE f.gvkey IN ({gvkey_list})
          AND f.datadate >= '2022-01-01'
          AND f.indfmt = 'INDL' AND f.datafmt = 'STD' AND f.consol = 'C'
          AND f.popsrc = 'D'
        ORDER BY f.gvkey, f.datadate
    """
    fund_df = db.raw_sql(fund_sql)
    print(f"  → {len(fund_df)} quarterly records across {fund_df['gvkey'].nunique()} firms", flush=True)
    db.close()
    return meta_df, fund_df


# ── 4. Assembly: long-form parquet matching v2 schema ──────────────────────

# GICS sector code → human-readable name. Used to populate the existing
# `panel.sector` string field (kernel.group_neutralize and screener filter
# both expect human-readable strings, not numeric codes).
GICS_SECTOR_MAP = {
    10: "Energy", 15: "Materials", 20: "Industrials",
    25: "Consumer Discretionary", 30: "Consumer Staples",
    35: "Health Care", 40: "Financials", 45: "Information Technology",
    50: "Communication Services", 55: "Utilities", 60: "Real Estate",
}


def assemble_panel(
    ohlcv: pd.DataFrame, meta: pd.DataFrame, fund: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stitch OHLCV + meta into long-form panel; reformat fund into PIT parquet."""
    if meta.empty:
        ohlcv["sector"] = "Unknown"
        ohlcv["industry"] = "Unknown"
        ohlcv["cap"] = pd.NA
        ohlcv["exchange"] = "Unknown"
        ohlcv["currency"] = "USD"
        return ohlcv, pd.DataFrame()

    # Bundle C.1 class-share rehydration: meta_df was queried with CRSP-form
    # tickers (BRK not BRK-B because CRSP collapses class shares). Panel
    # uses Yahoo dash form (BRK-B). For each CRSP-form row in meta, find
    # any panel ticker whose root matches and add a duplicate row with the
    # panel-form ticker, so the maps below resolve cleanly.
    panel_tickers = ohlcv["ticker"].unique()
    crsp_to_panel: dict[str, list[str]] = {}
    for pt in panel_tickers:
        root = pt.split("-")[0] if "-" in pt else pt
        crsp_to_panel.setdefault(root, []).append(pt)
    rows_to_add = []
    for _, row in meta.iterrows():
        for panel_form in crsp_to_panel.get(row["ticker"], []):
            if panel_form != row["ticker"]:
                rows_to_add.append({**row.to_dict(), "ticker": panel_form})
    if rows_to_add:
        meta = pd.concat([meta, pd.DataFrame(rows_to_add)], ignore_index=True)

    sector_map = meta.set_index("ticker")["gsector"].astype("Int64").to_dict()
    industry_map = meta.set_index("ticker")["gind"].astype("Int64").to_dict()
    gvkey_map = meta.set_index("ticker")["gvkey"].to_dict()

    ohlcv["sector"] = ohlcv["ticker"].map(
        lambda t: GICS_SECTOR_MAP.get(int(sector_map[t]), "Unknown")
        if t in sector_map and pd.notna(sector_map.get(t)) else "Unknown"
    )
    ohlcv["industry"] = ohlcv["ticker"].map(
        lambda t: str(int(industry_map[t]))
        if t in industry_map and pd.notna(industry_map.get(t)) else "Unknown"
    )
    ohlcv["exchange"] = "Unknown"
    ohlcv["currency"] = "USD"

    # Cap = close × shares_outstanding via PIT (RDQ-based) as-of join. The
    # fundq query at line ~309 already pulls f.cshoq AS shares_outstanding;
    # we PIT-join it backward by filing date so each (t, ticker) sees the
    # latest pre-filed quarter's shrout (no lookahead). CSHOQ is reported
    # in millions of shares per Compustat docs, so × 1e6 to get raw share
    # count, then × close = market cap in USD. Skip when fundq is empty
    # or shrout column missing — preserves prior all-NaN behavior so the
    # screener's "no cap data" empty state still triggers gracefully.
    if (
        not fund.empty
        and "shares_outstanding" in fund.columns
        and "rdq" in fund.columns
    ):
        rev_gvkey = {v: k for k, v in gvkey_map.items()}
        shares_pit = fund[["gvkey", "rdq", "shares_outstanding"]].copy()
        shares_pit["ticker"] = shares_pit["gvkey"].map(rev_gvkey)
        shares_pit = shares_pit[
            shares_pit["ticker"].notna()
            & shares_pit["rdq"].notna()
            & shares_pit["shares_outstanding"].notna()
        ].copy()
        shares_pit["filing_date"] = pd.to_datetime(shares_pit["rdq"])
        shares_pit = shares_pit[
            ["ticker", "filing_date", "shares_outstanding"]
        ].sort_values(["ticker", "filing_date"])

        # merge_asof requires both frames sorted by the on-key (date /
        # filing_date) — sort ohlcv by (ticker, date) before joining.
        ohlcv = ohlcv.sort_values(["ticker", "date"]).reset_index(drop=True)
        ohlcv["_date_dt"] = pd.to_datetime(ohlcv["date"])
        merged = pd.merge_asof(
            ohlcv,
            shares_pit,
            left_on="_date_dt",
            right_on="filing_date",
            by="ticker",
            direction="backward",
            allow_exact_matches=True,
        )
        # Convert millions → raw shares; cap in USD.
        cap_series = (
            merged["close"] * merged["shares_outstanding"] * 1_000_000
        ).astype("float64")
        ohlcv["cap"] = cap_series
        ohlcv = ohlcv.drop(columns=["_date_dt"])

        n_total = len(ohlcv)
        n_filled = int(ohlcv["cap"].notna().sum())
        n_uniq_tickers = int(
            ohlcv.loc[ohlcv["cap"].notna(), "ticker"].nunique()
        )
        print(
            f"  cap filled: {n_filled}/{n_total} cells ({n_filled / max(n_total, 1) * 100:.1f}%) "
            f"across {n_uniq_tickers}/{ohlcv['ticker'].nunique()} tickers",
            flush=True,
        )
    else:
        ohlcv["cap"] = pd.NA
        print(
            "  cap left NaN (fundq empty or shares_outstanding missing)",
            flush=True,
        )

    # PIT fundamentals: long-form on (gvkey, datadate). Rename gvkey→ticker
    # by reverse lookup; drop rows with no rdq (un-filed quarters).
    if fund.empty:
        return ohlcv, pd.DataFrame()
    rev_gvkey = {v: k for k, v in gvkey_map.items()}
    fund = fund.copy()
    fund["ticker"] = fund["gvkey"].map(rev_gvkey)
    fund = fund[fund["ticker"].notna() & fund["rdq"].notna()].copy()
    fund["report_period"] = pd.to_datetime(fund["datadate"]).dt.strftime("%Y-%m-%d")
    fund["filing_date"] = pd.to_datetime(fund["rdq"]).dt.strftime("%Y-%m-%d")
    fund = fund.drop(columns=["gvkey", "datadate", "rdq"])
    return ohlcv, fund


# ── 5. Main ─────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=float, default=3.0,
                    help="Panel length in years (default: 3.0)")
    ap.add_argument("--end", type=str, default=None,
                    help="Panel end date YYYY-MM-DD (default: today - 2 days)")
    ap.add_argument("--skip-fundamentals", action="store_true")
    ap.add_argument("--skip-ohlcv", action="store_true",
                    help="Re-use existing OHLCV parquet; only re-pull WRDS "
                         "metadata + fundamentals. Useful when fixing the "
                         "Compustat link-table join without re-hitting Alpaca.")
    ap.add_argument("--out", type=str, default=str(OUT_PARQUET))
    args = ap.parse_args()

    end = pd.Timestamp(args.end) if args.end else (
        pd.Timestamp.today().normalize() - pd.Timedelta(days=2)
    )
    start = end - pd.Timedelta(days=int(args.years * 365.25))
    print(f"=== panel window: {start.date()} → {end.date()} ===", flush=True)

    # Step 1: universe
    print("\n[1/4] computing SP500 union from fja05680...", flush=True)
    universe = compute_universe(start.to_pydatetime(), end.to_pydatetime())
    print(f"  union size: {len(universe)} tickers (incl. delisted)", flush=True)

    # Step 2: OHLCV
    if args.skip_ohlcv and Path(args.out).exists():
        print(f"\n[2/4] --skip-ohlcv: reading {Path(args.out).name} (no Alpaca call)", flush=True)
        existing = pd.read_parquet(args.out)
        # Strip prior meta columns; we'll re-assemble with fresh WRDS data.
        ohlcv = existing[["date", "ticker", "open", "high", "low", "close", "volume"]].copy()
        print(f"  loaded: {len(ohlcv)} rows, {ohlcv['ticker'].nunique()} tickers", flush=True)
    else:
        print(f"\n[2/4] pulling OHLCV from Alpaca for {len(universe)+1} tickers...", flush=True)
        all_tickers = universe + [BENCHMARK]
        t0 = time.time()
        ohlcv = fetch_ohlcv_alpaca(all_tickers, start.to_pydatetime(), end.to_pydatetime())
        print(f"  total: {len(ohlcv)} rows, {ohlcv['ticker'].nunique()} tickers in {time.time()-t0:.1f}s", flush=True)

    # Step 3: WRDS sector + fundamentals
    if args.skip_fundamentals:
        print("\n[3/4] SKIPPING WRDS metadata + fundamentals", flush=True)
        meta, fund = pd.DataFrame(), pd.DataFrame()
    else:
        print("\n[3/4] pulling WRDS metadata + fundamentals...", flush=True)
        meta, fund = fetch_wrds_metadata(universe)

    # Step 4: assemble
    print("\n[4/4] assembling long-form panel...", flush=True)
    panel, fund_pit = assemble_panel(ohlcv, meta, fund)

    out_path = Path(args.out)
    panel.to_parquet(out_path, index=False, compression="snappy")
    if not fund_pit.empty:
        fund_pit.to_parquet(OUT_FUND_PARQUET, index=False, compression="snappy")

    print(f"\n=== DONE ===")
    print(f"  panel:       {out_path} ({out_path.stat().st_size/1024/1024:.1f} MB)")
    print(f"  shape:       {panel.shape}")
    print(f"  date range:  {panel['date'].min()} → {panel['date'].max()}")
    print(f"  tickers:     {panel['ticker'].nunique()}")
    if not fund_pit.empty:
        print(f"  fundamentals:{OUT_FUND_PARQUET} ({OUT_FUND_PARQUET.stat().st_size/1024:.1f} KB)")
        print(f"  fund records:{len(fund_pit)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
