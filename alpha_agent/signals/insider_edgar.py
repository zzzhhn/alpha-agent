"""SEC EDGAR Form 4 fetch + parse for the insider signal.

Used by the offline ingestion job (scripts/ingest_insider_form4.py), NOT the
signal path: parsing Form 4 XML for the whole universe is thousands of
rate-limited SEC requests, which cannot run inside the Vercel 300s cron. The
job writes net values to insider_form4; the signal reads from there.

Net value = sum over open-market transactions (codes P / S) in the last
`window_days` of (+shares*price for acquired, -shares*price for disposed),
following Cohen-Malloy-Pomorski (2012): grants / option exercises / gifts
(codes A / M / G / F ...) are excluded as non-opportunistic.

SEC fair-access rules: <=10 req/s and a descriptive User-Agent. The fetch
helpers sleep between requests to stay well under the limit.
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import httpx

# SEC asks for a real contact in the UA. Identifies this research tool.
SEC_HEADERS = {"User-Agent": "AlphaAgent research contact@bobbyzhong.com"}
_SEC_THROTTLE_S = 0.13  # ~7.7 req/s, safely under SEC's 10/s ceiling
_OPEN_MARKET_CODES = {"P", "S"}


def _local(tag: str) -> str:
    """Strip the XML namespace from a tag, e.g. '{...}value' -> 'value'."""
    return tag.split("}")[-1]


def _first_text(elem: ET.Element, *path_local_names: str) -> str | None:
    """Walk child-by-child matching local tag names, return the leaf text."""
    cur = elem
    for name in path_local_names:
        nxt = None
        for child in cur:
            if _local(child.tag) == name:
                nxt = child
                break
        if nxt is None:
            return None
        cur = nxt
    return (cur.text or "").strip() or None


def load_cik_map(client: httpx.Client) -> dict[str, str]:
    """{TICKER: zero-padded 10-digit CIK} from SEC's public ticker map."""
    resp = client.get(
        "https://www.sec.gov/files/company_tickers.json",
        headers=SEC_HEADERS, timeout=30.0,
    )
    resp.raise_for_status()
    out: dict[str, str] = {}
    for row in resp.json().values():
        ticker = str(row.get("ticker", "")).upper()
        cik = row.get("cik_str")
        if ticker and cik is not None:
            out[ticker] = f"{int(cik):010d}"
    return out


def _recent_form4_docs(
    client: httpx.Client, cik10: str, as_of: datetime, window_days: int
) -> list[str]:
    """Document URLs of Form 4 filings filed within `window_days` of as_of."""
    resp = client.get(
        f"https://data.sec.gov/submissions/CIK{cik10}.json",
        headers=SEC_HEADERS, timeout=30.0,
    )
    resp.raise_for_status()
    recent = resp.json().get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accns = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])
    cutoff = (as_of - timedelta(days=window_days)).date()
    cik_int = int(cik10)
    urls: list[str] = []
    for form, date_s, accn, doc in zip(forms, dates, accns, docs):
        if form != "4":
            continue
        try:
            if datetime.strptime(date_s, "%Y-%m-%d").date() < cutoff:
                continue
        except (ValueError, TypeError):
            continue
        accn_nodash = accn.replace("-", "")
        # primaryDocument may be the XSL-rendered path (xslF345X06/form4.xml);
        # the raw XML sits beside it under the bare filename.
        bare = doc.split("/")[-1] if doc else "form4.xml"
        urls.append(
            f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_nodash}/{bare}"
        )
    return urls


def _parse_form4_net(xml_bytes: bytes) -> float:
    """Net signed dollar value of open-market (P/S) non-derivative transactions."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return 0.0
    net = 0.0
    for elem in root.iter():
        if _local(elem.tag) != "nonDerivativeTransaction":
            continue
        code = _first_text(elem, "transactionCoding", "transactionCode")
        if code not in _OPEN_MARKET_CODES:
            continue
        shares = _first_text(elem, "transactionAmounts", "transactionShares", "value")
        price = _first_text(
            elem, "transactionAmounts", "transactionPricePerShare", "value"
        )
        acq = _first_text(
            elem, "transactionAmounts", "transactionAcquiredDisposedCode", "value"
        )
        try:
            value = float(shares) * float(price)
        except (TypeError, ValueError):
            continue
        net += value if acq == "A" else -value
    return net


def fetch_form4_net(
    client: httpx.Client, cik10: str, as_of: datetime, window_days: int = 30
) -> tuple[float, int]:
    """(net_value, n_filings_with_open_market_txns) for one company."""
    time.sleep(_SEC_THROTTLE_S)
    doc_urls = _recent_form4_docs(client, cik10, as_of, window_days)
    net = 0.0
    n = 0
    for url in doc_urls:
        time.sleep(_SEC_THROTTLE_S)
        try:
            r = client.get(url, headers=SEC_HEADERS, timeout=30.0)
            r.raise_for_status()
        except httpx.HTTPError:
            continue
        delta = _parse_form4_net(r.content)
        if delta != 0.0:
            net += delta
            n += 1
    return net, n
