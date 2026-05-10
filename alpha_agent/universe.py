"""Universe definitions for cron orchestration.

SP500_UNIVERSE: source of truth for "which tickers does the slow cron iterate".
Bootstrapped from the v3 panel parquet manifest; can be replaced by a Postgres
table later (M3+).

get_watchlist: returns the user's tracked tickers (Phase 1 reads from a static
file; M3+ reads from Postgres user table).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

_PANEL_PATH = Path(__file__).parent / "data" / "factor_universe_sp500_v3.parquet"


def _load_sp500() -> list[str]:
    if not _PANEL_PATH.exists():
        # Fallback for environments without the parquet (CI / fresh installs)
        return [
            "AAPL", "MSFT", "GOOG", "AMZN", "META", "NVDA", "TSLA",
            "BRK.B", "JPM", "JNJ", "V", "WMT", "PG", "MA", "UNH",
            "HD", "DIS", "BAC", "XOM", "PFE",
        ] + [f"T{i:03d}" for i in range(80)]
    df = pd.read_parquet(_PANEL_PATH, columns=["ticker"])
    return sorted(df["ticker"].unique().tolist())


SP500_UNIVERSE: list[str] = _load_sp500()


def get_watchlist(top_n: int = 100) -> list[str]:
    """Stub: returns first top_n from SP500. M3+ reads user-specific list from Postgres."""
    return SP500_UNIVERSE[:top_n]
