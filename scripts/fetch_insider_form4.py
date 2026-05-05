"""Pull insider Form 4 filings from SEC EDGAR + parse + aggregate.

Bundle C.3 of the v4 audit. Builds the `insider_net_buying` factor
operand from openly-licensed SEC EDGAR data — bypassing the
financial-datasets API's free-tier sample limits (only ~10 most-recent
filings per ticker on free).

Pipeline:
  1. Resolve panel tickers → CIKs via SEC's company_tickers.json
  2. Pull each ticker's submissions JSON (1 req per ticker, ~600 total)
  3. Filter Form 4 filings to the panel window (2023-05 → 2026-05)
  4. Download each Form 4 XML (~40-50k requests)
  5. Parse: extract per-transaction (insider, code, shares, price, A/D)
  6. Aggregate to per-ticker-day signed dollar net buying
  7. Save as alpha_agent/data/insider_form4_sp500_v3.parquet

Rate-limit: SEC EDGAR fair-use is 10 req/s with proper User-Agent.
We sleep 0.12s between requests for safety margin.

Checkpointing: per-ticker progress is saved every 10 tickers so a
network blip doesn't lose hours of pulling. Resume on re-run by
inspecting which tickers already have parsed transactions in the
checkpoint file.

Usage:
    python3 scripts/fetch_insider_form4.py --sample 10   # smoke (~30s)
    python3 scripts/fetch_insider_form4.py               # full (~70 min)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "alpha_agent" / "data"
V3_PANEL = DATA_DIR / "factor_universe_sp500_v3.parquet"
OUT_PATH = DATA_DIR / "insider_form4_sp500_v3.parquet"
CHECKPOINT_PATH = DATA_DIR / "_form4_checkpoint.parquet"

# SEC EDGAR fair-use requires a contact User-Agent. Edit if forking.
USER_AGENT = "alpha-agent research zzzhhn123-9472 (a22309@cuhk.edu.cn)"
SEC_HOST = "https://www.sec.gov"
SEC_DATA_HOST = "https://data.sec.gov"
TICKERS_URL = f"{SEC_HOST}/files/company_tickers.json"
RATE_LIMIT_SLEEP = 0.12  # 8.3 req/s — under SEC's 10/s fair-use bar


def _request(url: str, timeout: int = 15, retries: int = 3) -> bytes:
    """GET via curl subprocess. SEC's www.sec.gov has periodic SSL EOF
    handshake issues with Python `requests`/urllib3; curl handles cleanly.

    Retry policy: only retry on TRANSIENT failures (timeout, connection
    reset, SSL handshake). 4xx HTTP errors (curl rc=22) fail immediately
    so the caller can fall back to an alternate URL path quickly —
    Form 4 archives have ~50/50 split between `/form4.xml` and
    `/xslF345X06/form4.xml`, so retrying on 404 wastes 9s per filing.
    """
    TRANSIENT_RC = {6, 7, 28, 35, 52, 56}  # DNS, conn, timeout, SSL, response
    for attempt in range(retries):
        try:
            r = subprocess.run(
                ["curl", "-sf", "-A", USER_AGENT,
                 "--compressed", "--max-time", str(timeout), url],
                capture_output=True, check=False,
            )
            if r.returncode == 0 and r.stdout:
                return r.stdout
            # rc=22 = HTTP error from -f flag (404, 5xx etc) → don't retry,
            # caller decides whether the URL is wrong or to back off.
            if r.returncode == 22:
                raise RuntimeError(f"HTTP error: {url}")
            if r.returncode in TRANSIENT_RC and attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise RuntimeError(f"curl rc={r.returncode}: {r.stderr.decode()[:120]}")
        except subprocess.SubprocessError as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"curl subprocess failed: {exc}")
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"all retries failed: {url}")


# ── Step 1: ticker → CIK mapping ──────────────────────────────────────────


def load_cik_map() -> dict[str, str]:
    """Fetch SEC's master ticker→CIK map. ~10k entries; freshness ~daily."""
    print("[step 1] loading SEC ticker → CIK map...", flush=True)
    body = _request(TICKERS_URL)
    data = json.loads(body)
    # Format: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "..."}, ...}
    mapping = {v["ticker"]: f"{v['cik_str']:010d}" for v in data.values()}
    print(f"  → {len(mapping)} mappings", flush=True)
    return mapping


# ── Step 2-3: pull + filter Form 4 filings per ticker ─────────────────────


def list_form4_for_ticker(
    cik: str, start_date: str, end_date: str,
) -> list[tuple[str, str]]:
    """Returns list of (filing_date, accession_number_clean) for Form 4
    filings within the window."""
    url = f"{SEC_DATA_HOST}/submissions/CIK{cik}.json"
    body = _request(url)
    j = json.loads(body)
    recent = j.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accs = recent.get("accessionNumber", [])
    out = []
    for f, d, a in zip(forms, dates, accs):
        if f == "4" and start_date <= d <= end_date:
            # accession 0001140361-26-017175 → no-dash for URL: 000114036126017175
            out.append((d, a.replace("-", "")))
    return out


# ── Step 4-5: download + parse each Form 4 XML ────────────────────────────


def fetch_form4_xml(cik: str, accession_no_dashes: str) -> bytes | None:
    """Try the canonical xslF345X06/form4.xml path first (legible XML);
    fall back to the bare form4.xml path. Returns bytes or None on
    miss (rare but happens for very old filings with non-standard layout).
    """
    base = f"{SEC_HOST}/Archives/edgar/data/{int(cik)}/{accession_no_dashes}"
    for path in ("/form4.xml", "/xslF345X06/form4.xml"):
        try:
            return _request(base + path)
        except Exception:
            continue
    return None


def _xml_text(elem: ET.Element | None, path: str) -> str | None:
    """Fetch a `value`-tagged child's text or a direct text. Form 4 uses
    nested `<value>X</value>` for many fields — handle both shapes."""
    if elem is None:
        return None
    sub = elem.find(path)
    if sub is None:
        return None
    val = sub.find("value")
    if val is not None and val.text is not None:
        return val.text.strip()
    return sub.text.strip() if sub.text else None


def parse_form4(xml_bytes: bytes) -> list[dict]:
    """Parse a Form 4 XML into a list of per-transaction dicts.

    We only keep nonDerivativeTransaction rows — these are direct stock
    buys/sales by the insider. Derivative transactions (option grants,
    exercises) live in derivativeTable and have a different signal
    profile that we leave for a later iteration.

    Each output row has:
      transaction_date, transaction_code, acquired_disposed,
      shares, price_per_share, dollars_signed, insider_name,
      is_officer, is_director, is_ten_percent_owner, officer_title
    """
    out = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return out

    # Reporter info (insider).
    rpt_owner = root.find("reportingOwner")
    insider = _xml_text(rpt_owner, "reportingOwnerId/rptOwnerName") or ""
    rel = rpt_owner.find("reportingOwnerRelationship") if rpt_owner is not None else None
    is_officer = (_xml_text(rel, "isOfficer") or "").strip().lower() in ("true", "1")
    is_director = (_xml_text(rel, "isDirector") or "").strip().lower() in ("true", "1")
    is_10pct = (_xml_text(rel, "isTenPercentOwner") or "").strip().lower() in ("true", "1")
    title = _xml_text(rel, "officerTitle") or ""

    nd_table = root.find("nonDerivativeTable")
    if nd_table is None:
        return out
    for tx in nd_table.findall("nonDerivativeTransaction"):
        date = _xml_text(tx, "transactionDate")
        code = _xml_text(tx, "transactionCoding/transactionCode")
        ad = _xml_text(tx, "transactionAmounts/transactionAcquiredDisposedCode")
        shares_s = _xml_text(tx, "transactionAmounts/transactionShares")
        price_s = _xml_text(tx, "transactionAmounts/transactionPricePerShare")
        if not (date and code and shares_s):
            continue
        try:
            shares = float(shares_s)
            price = float(price_s) if price_s else 0.0
        except ValueError:
            continue
        # Sign: A=acquired (buy direction), D=disposed (sell direction).
        sign = 1.0 if ad == "A" else -1.0 if ad == "D" else 0.0
        dollars = sign * shares * price
        out.append({
            "transaction_date": date,
            "transaction_code": code,
            "acquired_disposed": ad,
            "shares": shares,
            "price": price,
            "dollars_signed": dollars,
            "insider": insider,
            "is_officer": is_officer,
            "is_director": is_director,
            "is_ten_percent_owner": is_10pct,
            "officer_title": title,
        })
    return out


# ── Step 6: aggregate per ticker-day ──────────────────────────────────────


def aggregate(rows: list[dict]) -> pd.DataFrame:
    """Per-ticker-day net dollar signed buying.

    `transaction_code` filter: keep P (open-market purchase) and S (open-
    market sale). Drop A (award/grant), M (option exercise), F (tax
    withholding) — these are non-discretionary and confound the signal.
    Cohen-Malloy-Pomorski 2012 ("Decoding Inside Information") is the
    canonical reference for filtering to discretionary trades.
    """
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df[df["transaction_code"].isin(["P", "S"])].copy()
    if df.empty:
        return df
    # Group: (ticker, transaction_date) → sum signed dollars + counts
    g = df.groupby(["ticker", "transaction_date"], as_index=False).agg(
        net_dollars=("dollars_signed", "sum"),
        n_buys=("transaction_code", lambda s: (s == "P").sum()),
        n_sells=("transaction_code", lambda s: (s == "S").sum()),
    )
    return g


# ── Main ──────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=None,
                    help="If set, only fetch first N tickers (smoke test).")
    ap.add_argument("--start", type=str, default="2023-05-01")
    ap.add_argument("--end", type=str, default="2026-05-31")
    ap.add_argument("--out", type=str, default=str(OUT_PATH))
    ap.add_argument("--resume", action="store_true",
                    help="Skip tickers already in the checkpoint parquet.")
    args = ap.parse_args()

    panel = pd.read_parquet(V3_PANEL)
    panel_tickers = sorted(set(panel["ticker"].unique()) - {"SPY", "RSP"})
    if args.sample:
        panel_tickers = panel_tickers[: args.sample]
    print(f"=== Form 4 pipeline: {len(panel_tickers)} tickers, "
          f"{args.start} → {args.end} ===", flush=True)

    cik_map = load_cik_map()
    matched = [(t, cik_map.get(t)) for t in panel_tickers]
    matched = [(t, c) for t, c in matched if c]
    skipped = len(panel_tickers) - len(matched)
    print(f"[step 1.5] {len(matched)}/{len(panel_tickers)} tickers in SEC map ({skipped} not found)", flush=True)

    # Resume support: drop tickers already in checkpoint.
    done_tickers: set[str] = set()
    all_rows: list[dict] = []
    if args.resume and CHECKPOINT_PATH.exists():
        ckpt = pd.read_parquet(CHECKPOINT_PATH)
        all_rows = ckpt.to_dict(orient="records")
        done_tickers = set(ckpt["ticker"].unique())
        print(f"[resume] {len(done_tickers)} tickers already in checkpoint", flush=True)

    todo = [(t, c) for t, c in matched if t not in done_tickers]

    # Step 2-5: pull + parse per ticker.
    for i, (ticker, cik) in enumerate(todo, 1):
        try:
            time.sleep(RATE_LIMIT_SLEEP)
            filings = list_form4_for_ticker(cik, args.start, args.end)
            print(f"  [{i}/{len(todo)}] {ticker}: {len(filings)} filings to fetch", flush=True)
            n_tx = 0
            n_404 = 0
            t_start = time.time()
            for j, (filing_date, acc_clean) in enumerate(filings, 1):
                time.sleep(RATE_LIMIT_SLEEP)
                xml_bytes = fetch_form4_xml(cik, acc_clean)
                if xml_bytes is None:
                    n_404 += 1
                    continue
                txs = parse_form4(xml_bytes)
                for t in txs:
                    t["ticker"] = ticker
                    t["filing_date"] = filing_date
                    t["accession"] = acc_clean
                all_rows.extend(txs)
                n_tx += len(txs)
                if j % 20 == 0:
                    print(f"    {j}/{len(filings)} filings ({n_tx} txs, {n_404} 404s, {time.time()-t_start:.0f}s)", flush=True)
            print(f"  → {ticker} done: {n_tx} txs, {n_404} 404s in {time.time()-t_start:.0f}s", flush=True)
        except Exception as exc:
            print(f"  [{i}/{len(todo)}] {ticker}: FAIL {type(exc).__name__}: {str(exc)[:80]}", file=sys.stderr)

        # Per-ticker checkpoint — Form 4 fetches can take 1-30 minutes per
        # ticker depending on insider activity volume; never lose more
        # than one ticker's worth of work to a crash / network drop.
        pd.DataFrame(all_rows).to_parquet(CHECKPOINT_PATH, index=False, compression="snappy")
        if i % 10 == 0:
            print(f"  [checkpoint] {i}/{len(todo)} tickers done; {len(all_rows)} rows", flush=True)

    # Step 6: aggregate + save final.
    print(f"\n[step 6] aggregating {len(all_rows)} raw transaction rows...", flush=True)
    raw_df = pd.DataFrame(all_rows)
    agg = aggregate(all_rows)
    print(f"  → {len(agg)} ticker-day aggregated rows", flush=True)

    out_path = Path(args.out)
    agg.to_parquet(out_path, index=False, compression="snappy")
    raw_df.to_parquet(CHECKPOINT_PATH, index=False, compression="snappy")  # final raw

    print(f"\n=== DONE ===")
    print(f"  aggregated: {out_path} ({out_path.stat().st_size/1024:.1f} KB)")
    print(f"  raw txs:    {CHECKPOINT_PATH} ({CHECKPOINT_PATH.stat().st_size/1024:.1f} KB)")
    if not agg.empty:
        print(f"  tickers:    {agg['ticker'].nunique()}")
        print(f"  date range: {agg['transaction_date'].min()} → {agg['transaction_date'].max()}")
        print(f"  net buyers (median): {agg['net_dollars'].describe()[['min','25%','50%','75%','max']].to_dict()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
