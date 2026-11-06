from urllib.parse import parse_qs, urlsplit

import pytest

from scripts.cron_recovery import recovery_path


def test_price_recovery_defaults_to_small_window():
    query = parse_qs(urlsplit(recovery_path("daily_prices", 5, 0, "test")).query)
    assert query == {"limit": ["5"], "offset": ["0"], "period": ["5d"]}
    assert "period=1mo" in recovery_path("daily_prices", 75, 75, "test", "1mo")


@pytest.mark.parametrize("limit,offset,period", [(76, 0, "5d"), (5, -1, "5d"), (5, 0, "3y")])
def test_price_recovery_keeps_bounded_scope(limit, offset, period):
    with pytest.raises(ValueError):
        recovery_path("daily_prices", limit, offset, "test", period)
