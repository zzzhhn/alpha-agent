"""Identity evidence for manual market orders."""
from datetime import date
from typing import Any

from alpha_agent.data.security_identity import valid_research_symbol


async def read_market_instrument(conn: Any, ticker: str):
    return await conn.fetchrow(
        "SELECT id,identity_status FROM sim_instrument WHERE ticker=$1 FOR SHARE", ticker,
    )


def market_identity_verified(
    ticker: str, target: date, instrument: Any, instrument_id: int | None = None,
) -> bool:
    if not valid_research_symbol(ticker, target):
        return False
    if instrument is None:
        return instrument_id is None
    return instrument['identity_status'] == 'supported_universe' and (
        instrument_id is None or instrument_id == instrument['id']
    )
