from alpha_agent.news.types import dedup_hash


def test_same_url_and_headline_same_ticker_collide():
    a = dedup_hash("AAPL", "https://example.com/a", "Apple beats earnings")
    b = dedup_hash("AAPL", "https://example.com/a", "Apple beats earnings")
    assert a == b


def test_same_story_different_tickers_distinct():
    # Multi-ticker story returned by per-symbol fetches must produce
    # one row per ticker. Without ticker in the hash, FMP and Finnhub
    # competing on AAPL would dedup, but AAPL and GOOG fetches of the
    # SAME story would also dedup (losing GOOG). Spec self-review fix.
    a = dedup_hash("AAPL", "https://example.com/x", "Cloud earnings broad beat")
    b = dedup_hash("GOOG", "https://example.com/x", "Cloud earnings broad beat")
    assert a != b


def test_url_query_params_stripped():
    a = dedup_hash("AAPL", "https://example.com/a?utm_source=x", "headline")
    b = dedup_hash("AAPL", "https://example.com/a", "headline")
    assert a == b


def test_headline_case_and_punctuation_normalized():
    a = dedup_hash("AAPL", "https://example.com/a", "Apple Beats Earnings!")
    b = dedup_hash("AAPL", "https://example.com/a", "apple beats earnings")
    assert a == b


def test_macro_event_uses_none_ticker():
    # macro events have no ticker scope; passing None must work.
    h = dedup_hash(None, "https://example.com/m", "Trump on Apple")
    assert isinstance(h, str) and len(h) == 64  # sha256 hex
