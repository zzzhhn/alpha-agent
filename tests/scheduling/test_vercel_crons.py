"""Validate every deployed expression and its actual UTC firing minutes."""
import json
import re
from pathlib import Path

import pytest

CONFIG = json.loads((Path(__file__).resolve().parents[2] / "vercel.json").read_text())


def expand(field, low, high):
    values = set()
    for part in field.split(","):
        assert re.fullmatch(r"(?:\*|\d+(?:-\d+)?)(?:/\d+)?", part), part
        span, *step = part.split("/")
        stride = int(step[0]) if step else 1
        assert 1 <= stride <= high - low + 1
        if span == "*":
            start, end = low, high
        elif "-" in span:
            start, end = map(int, span.split("-"))
        else:
            start = end = int(span)
        assert low <= start <= end <= high
        values.update(range(start, end + 1, stride))
    return values


@pytest.mark.parametrize("cron", CONFIG["crons"])
def test_every_vercel_cron_is_valid_five_field_utc_syntax(cron):
    fields = cron["schedule"].split()
    assert len(fields) == 5
    for field, (low, high) in zip(fields, [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]):
        assert expand(field, low, high)


def times(path):
    return {(h, m) for c in CONFIG["crons"] if c["path"] == path
            for h in expand(c["schedule"].split()[1], 0, 23)
            for m in expand(c["schedule"].split()[0], 0, 59)}


def test_all_daily_close_and_slow_retry_minutes():
    assert times("/api/cron/tick/daily_close") == {
        divmod(t, 60) for t in range(20 * 60 + 10, 24 * 60, 5)}
    assert times("/api/cron/tick/slow_daily") == {
        divmod(t, 60) for t in range(13 * 60 + 30, 14 * 60 + 26, 5)}


def test_existing_crons_and_requested_single_shots_preserved():
    assert CONFIG["functions"]["api/index.py"]["maxDuration"] == 300
    pairs = {(c["path"], c["schedule"]) for c in CONFIG["crons"]}
    assert {
        ("/api/cron/paper_bot/valuation", "7,37 13-21 * * 1-5"),
        ("/api/cron/paper_fill", "0 1 * * *"),
        ("/api/cron/paper_bot/wake", "1,4 14,15 * * 1-5"),
        ("/api/cron/paper_bot/wake", "31,34 16,17,19,20 * * 1-5"),
        ("/api/cron/tick/fast_tech", "30 15,19 * * 1-5"),
        ("/api/cron/tick/news_per_ticker", "0 15,19 * * 1-5"),
        ("/api/cron/tick/news_macro", "0 12,16,20 * * 1-5"),
        ("/api/cron/tick/news_macro", "0 2 * * *"),
        ("/api/cron/tick/minute_bars", "15 18 * * 1-5"),
        ("/api/cron/tick/ic_backtest_monthly", "0 4 1 * *"),
    } <= pairs
    assert times("/api/cron/paper_bot/drive") == {
        (h, m) for hours, minutes in [((14, 15), range(1, 26)),
                                     ((16, 17, 19, 20), range(31, 56))]
        for h in hours for m in minutes}
