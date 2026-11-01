"""Bounded, offline research refresh. No database writes or invented filings.

Alpaca SIP adjusted daily bars; SEC companyfacts for newly public statements.
Keep the existing historical fundamentals and preserve missing fields. Run on
the maintenance machine, not inside a 300-second web request.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
import pandas as pd
from dotenv import load_dotenv

from scripts.fetch_insider_form4 import USER_AGENT

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "alpha_agent/data"
PANEL = DATA / "factor_universe_sp500_v3.parquet"
PIT = DATA / "fundamentals_pit_sp500_v3.parquet"
MEMBERS = DATA / "sp500_membership_2026-01-17.csv"  # legacy filename, not content as-of
MANIFEST = DATA / "research_dataset.json"
MEMBERS_URL = ("https://raw.githubusercontent.com/fja05680/sp500/master/"
               "S%26P%20500%20Historical%20Components%20%26%20Changes%20(Updated).csv")

# Existing Compustat fields use USD millions / millions of shares; EPS is USD.
# SEC NetIncomeLoss is GAAP net income, not a vendor-adjusted earnings series.
TAGS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
    "net_income_adjusted": ["NetIncomeLoss", "ProfitLoss"],
    "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
    "assets": ["Assets"], "equity": ["StockholdersEquity"],
    "total_liabilities": ["Liabilities"],
    "cash_and_equivalents": ["CashAndCashEquivalentsAtCarryingValue"],
    "long_term_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "short_term_debt": ["LongTermDebtCurrent", "ShortTermBorrowings"],
    "cost_of_goods_sold": ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
    "gross_profit": ["GrossProfit"], "operating_income": ["OperatingIncomeLoss"],
    "retained_earnings": ["RetainedEarningsAccumulatedDeficit"],
    "goodwill": ["Goodwill"], "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "shares_outstanding": ["CommonStockSharesOutstanding"],
}
FLOWS = {"revenue", "net_income_adjusted", "eps", "cost_of_goods_sold",
         "gross_profit", "operating_income"}


def sec_snapshots(payload: dict, ticker: str, *, after: str, through: str) -> list[dict]:
    """Use actual filing dates and directly reported quarters, never +45d guesses.

    A filing becomes usable the next calendar day (conservative for after-close
    announcements). Restated facts only become visible at their later filing.
    Annual/YTD income cannot masquerade as a quarter; leave it missing.
    """
    facts = payload.get("facts", {}).get("us-gaap", {})
    candidates = []
    for field, tags in TAGS.items():
        unit = "USD/shares" if field == "eps" else "shares" if field == "shares_outstanding" else "USD"
        for priority, tag in enumerate(tags):
            for row in facts.get(tag, {}).get("units", {}).get(unit, []):
                filed, end = row.get("filed", ""), row.get("end", "")
                if not after < filed <= through or row.get("form") not in ("10-Q", "10-K"):
                    continue
                if not end or end > filed or (date.fromisoformat(filed) - date.fromisoformat(end)).days > 135:
                    continue
                if field in FLOWS:
                    start = row.get("start")
                    if not start or not 60 <= (date.fromisoformat(end) - date.fromisoformat(start)).days <= 110:
                        continue
                candidates.append((filed, end, field, priority, float(row["val"])))
    output = []
    for filed in sorted({r[0] for r in candidates}):
        records = [r for r in candidates if r[0] == filed]
        period = max(r[1] for r in records)
        row = {"ticker": ticker, "report_period": period,
               "filing_date": (date.fromisoformat(filed) + timedelta(days=1)).isoformat()}
        for field in TAGS:
            values = sorted([r for r in records if r[1] == period and r[2] == field], key=lambda r: r[3])
            if values:
                row[field] = values[0][4] / (1 if field == "eps" else 1_000_000)
        if "assets" in row or "revenue" in row:
            output.append(row)
    return output


def supplement_membership(members, through: str):
    updates = json.loads((DATA / "membership_updates.json").read_text())
    for update in sorted(updates, key=lambda r: r["date"]):
        if members.iloc[-1].date < update["date"] <= through:
            current = set(members.iloc[-1].tickers.split(","))
            current = (current - set(update["remove"])) | set(update["add"])
            members = pd.concat([members, pd.DataFrame([{
                "date": update["date"], "tickers": ",".join(sorted(current)),
            }])], ignore_index=True)
    return members, [u for u in updates if u["date"] <= through]


def refresh_caps(frame, fundamentals):
    shares = fundamentals[["ticker", "filing_date", "shares_outstanding"]].dropna().copy()
    shares["filing_date"] = pd.to_datetime(shares.filing_date)
    frame = frame.copy()
    frame["day"] = pd.to_datetime(frame.date)
    joined = pd.merge_asof(frame.sort_values("day"), shares.sort_values("filing_date"),
                          left_on="day", right_on="filing_date", by="ticker", direction="backward")
    fresh = (joined.day - joined.filing_date).dt.days <= 200
    joined["cap"] = (joined.close * joined.shares_outstanding * 1e6).where(fresh)
    return joined.drop(columns=["day", "filing_date", "shares_outstanding"])


def refresh_prices(client, through: str) -> dict:
    history = client.get(MEMBERS_URL).raise_for_status().text
    members = pd.read_csv(io.StringIO(history)).sort_values("date")
    members = members[members.date <= through]
    members, supplements = supplement_membership(members, through)
    start = (date.fromisoformat(through) - timedelta(days=3 * 366)).isoformat()
    relevant = members[members.date >= start]
    prior = members[members.date < start].tail(1)
    universe = sorted({t.strip().replace(".", "-") for s in pd.concat([prior, relevant]).tickers
                       for t in s.split(",")} | {"SPY", "RSP"})
    headers = {"APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"],
               "APCA-API-SECRET-KEY": os.environ["ALPACA_API_SECRET"]}
    rows = []
    for offset in range(0, len(universe), 75):
        params = {"symbols": ",".join(t.replace("-", ".") for t in universe[offset:offset + 75]),
                  "timeframe": "1Day", "start": start,
                  "end": (date.fromisoformat(through) + timedelta(days=1)).isoformat(),
                  "feed": "sip", "adjustment": "all", "asof": "-", "limit": 10000}
        for _page in range(20):
            payload = client.get("https://data.alpaca.markets/v2/stocks/bars",
                                 headers=headers, params=params).raise_for_status().json()
            for tk, bars in payload.get("bars", {}).items():
                for bar in bars:
                    day = bar["t"][:10]
                    # PARA was recycled by another issuer. Never join the two.
                    if day > through or (tk == "PARA" and day > "2025-08-06"):
                        continue
                    rows.append({"ticker": tk.replace(".", "-"), "date": day,
                                 **{k: bar[v] for k, v in {"open": "o", "high": "h", "low": "l", "close": "c", "volume": "v"}.items()}})
            if not payload.get("next_page_token"):
                break
            params["page_token"] = payload["next_page_token"]
        else:
            raise RuntimeError("Alpaca pagination bound exceeded; dataset unchanged")
        print(f"OHLCV {min(offset + 75, len(universe))}/{len(universe)} symbols; {len(rows)} rows", flush=True)
    frame = pd.DataFrame(rows).drop_duplicates(["date", "ticker"]).sort_values(["date", "ticker"])
    if frame[frame.ticker == "SPY"].date.max() != through:
        raise RuntimeError("Benchmark not current; dataset unchanged")
    current = set(members.iloc[-1].tickers.replace(".", "-").split(","))
    latest = set(frame[frame.date == through].ticker)
    coverage = len(current & latest) / len(current)
    if coverage < .9:
        raise RuntimeError(f"Current membership quote coverage only {coverage:.1%}; dataset unchanged")
    old = pd.read_parquet(PANEL).sort_values("date").drop_duplicates("ticker", keep="last")
    metadata = old.set_index("ticker")
    for field in ("sector", "industry", "exchange", "currency"):
        frame[field] = frame.ticker.map(metadata[field]).fillna("USD" if field == "currency" else "Unknown")
    # Never extend a stale capitalization snapshot; rebuild from dated shares below.
    frame = refresh_caps(frame, pd.read_parquet(PIT))
    frame.to_parquet(PANEL.with_suffix(".tmp"), index=False)
    PANEL.with_suffix(".tmp").replace(PANEL)
    members.to_csv(MEMBERS, index=False)
    return {"market_data_through": through, "market_source": "Alpaca SIP", "adjustment": "all",
            "symbol_mapping": "disabled; PARA history capped 2025-08-06", "rows": len(frame),
            "tickers": frame.ticker.nunique(), "membership_as_of": str(members.iloc[-1].date),
            "membership_source": MEMBERS_URL, "current_membership_coverage": coverage,
            "membership_supplements": supplements,
            "missing_current_symbols": sorted(current - latest)}


def refresh_fundamentals(client, through: str) -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}
    mapping = client.get("https://www.sec.gov/files/company_tickers.json", headers=headers).raise_for_status().json()
    ciks = {r["ticker"].replace(".", "-"): r["cik_str"] for r in mapping.values()}
    old = pd.read_parquet(PIT)
    frame = pd.read_parquet(PANEL)
    tickers = sorted(set(frame.ticker) - {"SPY", "RSP", "PARA"})
    new, errors = [], []
    for i, ticker in enumerate(tickers):
        if ticker not in ciks:
            continue
        try:
            payload = client.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{ciks[ticker]:010d}.json", headers=headers).raise_for_status().json()
            new.extend(sec_snapshots(payload, ticker, after="2026-04-30", through=through))
        except (httpx.HTTPError, ValueError) as exc:
            errors.append({"ticker": ticker, "error": type(exc).__name__})
        time.sleep(.15)  # sequential, comfortably below SEC's 10 requests/second
        if (i + 1) % 40 == 0:
            print(f"SEC {i + 1}/{len(tickers)}; {len(new)} dated snapshots; {len(errors)} failed", flush=True)
    if len({r["ticker"] for r in new}) < 300:
        raise RuntimeError(f"Too few fresh SEC issuers ({len({r['ticker'] for r in new})}); PIT unchanged")
    combined = pd.concat([old, pd.DataFrame(new)], ignore_index=True).drop_duplicates(["ticker", "filing_date"], keep="last")
    combined = combined.sort_values(["ticker", "filing_date"])
    combined.to_parquet(PIT.with_suffix(".tmp"), index=False)
    PIT.with_suffix(".tmp").replace(PIT)
    refresh_caps(frame, combined).to_parquet(PANEL, index=False)
    return {"fundamentals_checked_through": through, "fundamentals_source": "SEC companyfacts after existing Compustat history",
            "new_fundamental_snapshots": len(new), "fresh_issuers": len({r["ticker"] for r in new}),
            "fundamentals_failures": errors, "publication_rule": "actual filing date plus one calendar day",
            "fundamental_limitations": ["SEC GAAP net income, not adjusted earnings", "annual/YTD flows not substituted for quarters", "sector metadata remains a snapshot"]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--through", required=True)
    p.add_argument("--env-file", required=True)
    p.add_argument("--fundamentals-only", action="store_true")
    p.add_argument("--prices-only", action="store_true")
    args = p.parse_args()
    load_dotenv(args.env_file)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    with httpx.Client(timeout=httpx.Timeout(30, connect=10), follow_redirects=True) as client:
        if not args.fundamentals_only:
            manifest.update(refresh_prices(client, args.through))
            MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
        if not args.prices_only:
            manifest.update(refresh_fundamentals(client, args.through))
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
