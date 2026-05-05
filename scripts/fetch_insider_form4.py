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
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
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
RATE_LIMIT_SLEEP = 0.12  # 8.3 req/s — under SEC's 10/s fair-use bar (serial mode)
PARALLEL_PER_WORKER_SLEEP = 0.65  # 6 workers × 1/0.65 = 9.2 req/s aggregate — at SEC ceiling


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
    """Locate + download the Form 4 XML for a filing.

    Filing agents use INCONSISTENT XML filenames:
      - Older / standard:  form4.xml         (~50% of SP500)
      - XSL-rendered:      xslF345X06/form4.xml
      - Workiva / agents:  wk-form4_<timestamp>.xml
      - Other custom names

    Strategy (cheap → expensive):
      1. Try /form4.xml directly (1 req, hits ~50% of filings)
      2. Try /xslF345X06/form4.xml (1 req, hits ~20%)
      3. Fetch index.json, find any *form4*.xml in directory listing,
         try each (3+ reqs but only for the remaining ~30% of filings)

    Average cost: 1.3-1.5 reqs per filing — much better than always
    fetching index.json (which was 2 reqs per filing).
    """
    base = f"{SEC_HOST}/Archives/edgar/data/{int(cik)}/{accession_no_dashes}"
    # Step 1+2: cheap hardcoded paths that cover most of the historic
    # filer base. curl returns rc=22 immediately on 404 (no retry), so
    # the cost of each miss is ~0.5s + the per-worker sleep.
    for path in ("/form4.xml", "/xslF345X06/form4.xml"):
        try:
            return _request(base + path)
        except Exception:
            continue
    # Step 3: fall back to directory discovery for novel filename patterns.
    try:
        idx_bytes = _request(base + "/index.json")
        idx = json.loads(idx_bytes)
    except Exception:
        return None
    items = idx.get("directory", {}).get("item", [])
    candidates = [
        it["name"] for it in items
        if isinstance(it.get("name"), str)
        and it["name"].lower().endswith(".xml")
        and ("form4" in it["name"].lower() or "form-4" in it["name"].lower()
             or "ownership" in it["name"].lower())
    ]
    # Prefer files at the root over xslF345X06/ (the latter is XSLT-rendered).
    candidates.sort(key=lambda n: ("xsl" in n.lower(), len(n)))
    for name in candidates:
        try:
            return _request(f"{base}/{name}")
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
    ap.add_argument("--workers", type=int, default=6,
                    help="Parallel ticker fetchers. SEC fair-use is 10 req/s "
                         "aggregate; default 6 × 0.65s sleep = 9.2 req/s.")
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
    # Parallel mode: each worker holds an entire ticker (its 50-200 filings)
    # serially, but multiple tickers process concurrently. With 4 workers
    # × 0.55s gap, aggregate is 7.3 req/s — well under SEC's 10/s fair-use.
    # Each worker has its own per-request sleep; no global lock needed.
    rows_lock = threading.Lock()
    progress_lock = threading.Lock()
    completed = [0]  # mutable counter, accessed under progress_lock

    def process_ticker(ticker: str, cik: str) -> tuple[str, int, int, float]:
        """Worker fn: fetch + parse all Form 4 filings for one ticker.

        Returns (ticker, n_filings, n_txs, elapsed_s) for the progress
        printer. Appends raw transactions to the global `all_rows` list
        under `rows_lock` so the checkpoint logic can read it.
        """
        time.sleep(PARALLEL_PER_WORKER_SLEEP)
        filings = list_form4_for_ticker(cik, args.start, args.end)
        local_rows: list[dict] = []
        t_start = time.time()
        for filing_date, acc_clean in filings:
            time.sleep(PARALLEL_PER_WORKER_SLEEP)
            xml_bytes = fetch_form4_xml(cik, acc_clean)
            if xml_bytes is None:
                continue
            txs = parse_form4(xml_bytes)
            for t in txs:
                t["ticker"] = ticker
                t["filing_date"] = filing_date
                t["accession"] = acc_clean
            local_rows.extend(txs)
        with rows_lock:
            all_rows.extend(local_rows)
        return ticker, len(filings), len(local_rows), time.time() - t_start

    workers = max(1, min(args.workers, 6))  # SEC fair-use ceiling
    print(f"\n[step 2-5] fetching {len(todo)} tickers with {workers} parallel workers...", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_ticker, t, c): t for t, c in todo}
        for fut in as_completed(futures):
            ticker = futures[fut]
            try:
                ticker_done, n_filings, n_txs, elapsed = fut.result()
            except Exception as exc:
                with progress_lock:
                    completed[0] += 1
                    print(f"  [{completed[0]}/{len(todo)}] {ticker}: FAIL "
                          f"{type(exc).__name__}: {str(exc)[:80]}", file=sys.stderr)
                continue
            with progress_lock:
                completed[0] += 1
                i = completed[0]
                print(f"  [{i}/{len(todo)}] {ticker_done}: "
                      f"{n_filings} filings → {n_txs} txs ({elapsed:.0f}s)", flush=True)
                # Per-ticker checkpoint — never lose more than one ticker's
                # work to a crash. Held under progress_lock to keep parquet
                # writes serialized (pandas isn't thread-safe).
                if i % 10 == 0 or i == len(todo):
                    with rows_lock:
                        pd.DataFrame(all_rows).to_parquet(
                            CHECKPOINT_PATH, index=False, compression="snappy",
                        )
                        n_rows = len(all_rows)
                    print(f"  [checkpoint] {i}/{len(todo)} tickers; "
                          f"{n_rows} txs persisted", flush=True)

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
