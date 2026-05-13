# tests/signals/test_yf_helpers.py
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pandas as pd

from alpha_agent.signals.yf_helpers import (
    extract_fundamentals,
    extract_news_items,
    extract_next_earnings,
    extract_ohlcv,
    get_ticker,
)


def test_get_ticker_caches_within_ttl():
    """Two calls within TTL should return the same Ticker instance."""
    from alpha_agent.signals import yf_helpers
    yf_helpers._cache.clear()
    with patch("yfinance.Ticker") as mock_yf:
        mock_yf.return_value = MagicMock(name="aapl_ticker")
        a = get_ticker("AAPL")
        b = get_ticker("AAPL")
    assert a is b
    assert mock_yf.call_count == 1


def test_get_ticker_refreshes_after_ttl():
    """Calls beyond _TTL_SECONDS create a fresh Ticker instance."""
    from alpha_agent.signals import yf_helpers
    yf_helpers._cache.clear()
    with patch("alpha_agent.signals.yf_helpers.time") as mock_time, \
         patch("yfinance.Ticker") as mock_yf:
        mock_time.time.side_effect = [1000.0, 1601.0]
        mock_yf.side_effect = [MagicMock(name="t1"), MagicMock(name="t2")]
        a = get_ticker("MSFT")
        b = get_ticker("MSFT")
    assert a is not b
    assert mock_yf.call_count == 2


def test_extract_fundamentals_full_payload():
    info = {
        "trailingPE": 28.5, "forwardPE": 26.0, "trailingEps": 6.42,
        "marketCap": 3_200_000_000_000, "dividendYield": 0.0043,
        "profitMargins": 0.246, "debtToEquity": 145.3, "beta": 1.21,
    }
    out = extract_fundamentals(info)
    assert out["pe_trailing"] == 28.5
    assert out["pe_forward"] == 26.0
    assert out["eps_ttm"] == 6.42
    assert out["market_cap"] == 3_200_000_000_000
    assert out["dividend_yield"] == 0.0043
    assert out["profit_margin"] == 0.246
    assert out["debt_to_equity"] == 145.3
    assert out["beta"] == 1.21


def test_extract_fundamentals_missing_fields_returns_none():
    """yfinance returns sparse `info` dicts for thinly-traded names; missing
    keys must surface as None (frontend uses ?? '—'), not 0 or NaN."""
    out = extract_fundamentals({"trailingPE": 12.0})
    assert out["pe_trailing"] == 12.0
    assert out["pe_forward"] is None
    assert out["market_cap"] is None


def test_extract_fundamentals_nan_normalised_to_none():
    """Pandas/yfinance occasionally surfaces NaN floats; Postgres JSONB
    rejects literal NaN tokens, so we coerce at the extraction boundary."""
    out = extract_fundamentals({"trailingPE": float("nan"), "beta": 1.1})
    assert out["pe_trailing"] is None
    assert out["beta"] == 1.1


def test_extract_news_items_max_5():
    raw = [
        {"title": f"Headline {i}", "publisher": "Reuters",
         "providerPublishTime": 1700000000 + i * 60, "link": f"https://x/{i}"}
        for i in range(10)
    ]
    out = extract_news_items(raw, limit=5)
    assert len(out) == 5
    assert out[0]["title"] == "Headline 0"
    assert out[0]["publisher"] == "Reuters"
    assert out[0]["published_at"].startswith("2023")
    assert out[0]["sentiment"] in ("pos", "neg", "neu")


def test_extract_news_items_new_nested_shape():
    """Current yfinance Ticker.news returns items as
    {id, content: {title, pubDate, provider: {displayName}, canonicalUrl: {url}}}.
    Regression for M4a F1 follow-up: the old flat-shape lookups returned
    empty strings, so all UI headlines rendered blank in production."""
    raw = [
        {
            "id": "abc",
            "content": {
                "id": "abc",
                "title": "Apple stock soars on record close",
                "pubDate": "2026-05-13T17:51:12Z",
                "provider": {"displayName": "Yahoo Finance"},
                "canonicalUrl": {"url": "https://finance.yahoo.com/news/abc"},
                "summary": "Apple stock was on pace for a record close...",
            },
        }
    ]
    out = extract_news_items(raw, limit=5)
    assert len(out) == 1
    assert out[0]["title"] == "Apple stock soars on record close"
    assert out[0]["publisher"] == "Yahoo Finance"
    assert out[0]["link"] == "https://finance.yahoo.com/news/abc"
    assert out[0]["published_at"] == "2026-05-13T17:51:12Z"
    assert out[0]["sentiment"] == "pos"  # "soars" + "record"


def test_extract_news_items_sentiment_keyword_classifier():
    out = extract_news_items(
        [
            {"title": "Apple beats Q3 earnings, raises guidance",
             "publisher": "WSJ", "providerPublishTime": 1700000000, "link": "x"},
            {"title": "Stock plunges on weak iPhone sales",
             "publisher": "Bloomberg", "providerPublishTime": 1700000000, "link": "y"},
            {"title": "Apple announces new product launch",
             "publisher": "Reuters", "providerPublishTime": 1700000000, "link": "z"},
        ],
        limit=5,
    )
    assert out[0]["sentiment"] == "pos"  # "beats" + "raises"
    assert out[1]["sentiment"] == "neg"  # "plunges" + "weak"
    assert out[2]["sentiment"] == "neu"


def test_extract_next_earnings_when_calendar_has_entry():
    cal = pd.DataFrame(
        {"Earnings Date": [pd.Timestamp("2026-07-31", tz="UTC")],
         "EPS Estimate": [1.45], "Revenue Estimate": [120_000_000_000]}
    )
    out = extract_next_earnings(cal, as_of=datetime(2026, 5, 13, tzinfo=UTC))
    assert out["next_date"] == "2026-07-31"
    assert out["days_until"] == 79
    assert out["eps_estimate"] == 1.45
    assert out["revenue_estimate"] == 120_000_000_000


def test_extract_next_earnings_when_no_entry_returns_none_fields():
    out = extract_next_earnings(None, as_of=datetime(2026, 5, 13, tzinfo=UTC))
    assert out == {"next_date": None, "days_until": None,
                   "eps_estimate": None, "revenue_estimate": None}


def test_extract_next_earnings_dict_shape():
    """Newer yfinance versions return Ticker.calendar as a plain dict with
    list values. Regression for M4a F1 follow-up: previously crashed with
    AttributeError 'list' object has no attribute 'iloc'."""
    cal = {
        "Earnings Date": [pd.Timestamp("2026-07-31", tz="UTC")],
        "EPS Estimate": 1.45,
        "Revenue Estimate": 120_000_000_000,
    }
    out = extract_next_earnings(cal, as_of=datetime(2026, 5, 13, tzinfo=UTC))
    assert out["next_date"] == "2026-07-31"
    assert out["days_until"] == 79
    assert out["eps_estimate"] == 1.45
    assert out["revenue_estimate"] == 120_000_000_000


def test_extract_next_earnings_empty_dict_returns_none_fields():
    out = extract_next_earnings({}, as_of=datetime(2026, 5, 13, tzinfo=UTC))
    assert out["next_date"] is None


def test_extract_ohlcv_shapes_pandas_to_records():
    df = pd.DataFrame(
        {"Open": [100.0, 101.0], "High": [102.0, 103.0],
         "Low": [99.0, 100.5], "Close": [101.5, 102.5],
         "Volume": [1_000_000, 1_100_000]},
        index=pd.DatetimeIndex(["2026-05-12", "2026-05-13"]),
    )
    out = extract_ohlcv(df)
    assert len(out) == 2
    assert out[0] == {"date": "2026-05-12", "open": 100.0, "high": 102.0,
                      "low": 99.0, "close": 101.5, "volume": 1_000_000}


def test_extract_ohlcv_empty_df_returns_empty_list():
    out = extract_ohlcv(pd.DataFrame())
    assert out == []


def test_extract_ohlcv_propagates_none_for_missing_prices():
    """Price fields with NaN/missing must surface as None so the chart
    consumer can choose drop vs gap-fill, not get a misleading 0.0 bar."""
    df = pd.DataFrame(
        {"Open": [100.0, float("nan")], "High": [102.0, 103.0],
         "Low": [99.0, 100.5], "Close": [101.5, 102.5],
         "Volume": [1_000_000, 1_100_000]},
        index=pd.DatetimeIndex(["2026-05-12", "2026-05-13"]),
    )
    out = extract_ohlcv(df)
    assert out[1]["open"] is None
    assert out[1]["high"] == 103.0  # other fields untouched
