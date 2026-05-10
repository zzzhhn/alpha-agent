from alpha_agent.universe import SP500_UNIVERSE, get_watchlist


def test_sp500_universe_is_nonempty_string_list():
    assert isinstance(SP500_UNIVERSE, list)
    assert len(SP500_UNIVERSE) >= 100  # Phase 1 panel has ~99 tickers
    assert all(isinstance(t, str) for t in SP500_UNIVERSE)
    assert all(t.isupper() for t in SP500_UNIVERSE)


def test_get_watchlist_default_returns_top_n():
    wl = get_watchlist(top_n=20)
    assert isinstance(wl, list)
    assert len(wl) <= 20
    assert all(isinstance(t, str) for t in wl)
