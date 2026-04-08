"""US stock universe definitions for backtesting."""

from __future__ import annotations

# fmt: off
# Top-50 S&P 500 constituents by market cap (snapshot 2026-Q1).
_SP500_TOP50: dict[str, str] = {
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "AMZN": "Amazon",
    "GOOGL": "Alphabet A", "META": "Meta", "BRK-B": "Berkshire B", "AVGO": "Broadcom",
    "LLY": "Eli Lilly", "JPM": "JPMorgan", "TSLA": "Tesla", "V": "Visa",
    "UNH": "UnitedHealth", "XOM": "Exxon", "MA": "Mastercard", "COST": "Costco",
    "PG": "Procter&Gamble", "JNJ": "J&J", "HD": "Home Depot", "ABBV": "AbbVie",
    "WMT": "Walmart", "NFLX": "Netflix", "BAC": "Bank of America", "CRM": "Salesforce",
    "CVX": "Chevron", "KO": "Coca-Cola", "MRK": "Merck", "ORCL": "Oracle",
    "AMD": "AMD", "PEP": "PepsiCo", "ACN": "Accenture", "TMO": "Thermo Fisher",
    "LIN": "Linde", "MCD": "McDonald's", "CSCO": "Cisco", "ADBE": "Adobe",
    "ABT": "Abbott", "WFC": "Wells Fargo", "PM": "Philip Morris", "IBM": "IBM",
    "GE": "GE Aerospace", "ISRG": "Intuitive Surgical", "NOW": "ServiceNow",
    "INTU": "Intuit", "CAT": "Caterpillar", "QCOM": "Qualcomm",
    "GS": "Goldman Sachs", "VZ": "Verizon", "AMAT": "Applied Materials", "TXN": "Texas Instruments",
}

# A broader set — top 100 spanning S&P 500 mega + large caps
_SP500_TOP100: dict[str, str] = {
    **_SP500_TOP50,
    "BKNG": "Booking", "BLK": "BlackRock", "UBER": "Uber", "AXP": "AmEx",
    "SPGI": "S&P Global", "T": "AT&T", "DHR": "Danaher", "RTX": "RTX Corp",
    "LOW": "Lowe's", "NEE": "NextEra", "PLD": "Prologis", "SYK": "Stryker",
    "HON": "Honeywell", "DE": "Deere", "UNP": "Union Pacific", "ETN": "Eaton",
    "ELV": "Elevance", "ADP": "ADP", "BMY": "Bristol-Myers", "PANW": "Palo Alto",
    "LRCX": "Lam Research", "CI": "Cigna", "FI": "Fiserv", "MDLZ": "Mondelez",
    "KLAC": "KLA Corp", "CB": "Chubb", "DUK": "Duke Energy", "SO": "Southern Co",
    "CME": "CME Group", "MCO": "Moody's", "ICE": "ICE", "BSX": "Boston Sci",
    "MU": "Micron", "PH": "Parker Hannifin", "SNPS": "Synopsys", "CDNS": "Cadence",
    "SHW": "Sherwin-Williams", "MMC": "Marsh McLennan", "GD": "General Dynamics",
    "ZTS": "Zoetis", "TT": "Trane Technologies", "ITW": "Illinois Tool", "EMR": "Emerson",
    "PNC": "PNC Financial", "REGN": "Regeneron", "MSI": "Motorola Solutions",
    "USB": "US Bancorp", "CL": "Colgate", "APD": "Air Products", "AON": "Aon",
    "WELL": "Welltower", "TDG": "TransDigm",
}
# fmt: on


class SP500Universe:
    """S&P 500 top-50 investable universe for US equity backtesting."""

    def __init__(self, top_n: int = 50) -> None:
        self._top_n = min(top_n, len(_SP500_TOP100))
        self._data = dict(list(_SP500_TOP100.items())[:self._top_n])

    @property
    def stock_codes(self) -> list[str]:
        """Return a list of US ticker symbols."""
        return list(self._data.keys())

    def name_map(self) -> dict[str, str]:
        """Return an immutable copy of ticker -> company name mapping."""
        return dict(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"SP500Universe(n={len(self)})"
