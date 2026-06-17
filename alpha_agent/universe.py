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

# Tickers scored beyond the factor-panel parquet. These names are NOT in the
# factor model panel, so factor.py drops them gracefully ("not in panel
# universe") and their composite is built from the remaining signals
# (technicals / analyst / earnings / news / supply_chain / ...). Added when a
# serenity bottleneck study scores a name the panel does not cover.
#   VRT (Vertiv) — 2026-06-17, power+cooling bottleneck (data-center power +
#   liquid-cooling pure-play); supply_chain author-grade scorecard upserted.
_EXTRA_TICKERS: list[str] = ["VRT"]


def _load_sp500() -> list[str]:
    if not _PANEL_PATH.exists():
        # Fallback for environments without the parquet (CI / fresh installs)
        base = [
            "AAPL", "MSFT", "GOOG", "AMZN", "META", "NVDA", "TSLA",
            "BRK.B", "JPM", "JNJ", "V", "WMT", "PG", "MA", "UNH",
            "HD", "DIS", "BAC", "XOM", "PFE",
        ] + [f"T{i:03d}" for i in range(80)]
    else:
        df = pd.read_parquet(_PANEL_PATH, columns=["ticker"])
        base = sorted(df["ticker"].unique().tolist())
    seen = set(base)
    return base + [t for t in _EXTRA_TICKERS if t not in seen]


SP500_UNIVERSE: list[str] = _load_sp500()


def get_watchlist(top_n: int = 100, offset: int = 0) -> list[str]:
    """Stub: returns SP500[offset:offset+top_n]. M3+ reads user-specific list from Postgres.

    `offset` enables multi-shot coverage from external schedulers (GH Actions cron
    workflow) under Hobby 300s function timeout: one shot covers `top_n` slots,
    successive offsets walk the universe.
    """
    return SP500_UNIVERSE[offset : offset + top_n]
