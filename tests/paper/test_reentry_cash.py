from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from scripts.research.reentry_cash import category, replay, verify_opening


def test_forward_opening_accepts_matching_receipt_not_revised_marks():
    cutoff = datetime(2026, 11, 24, 21, tzinfo=UTC)
    snapshot = dict(
        account=9,
        cohort=2,
        cutoff=cutoff.isoformat(),
        captured_at="2026-11-25T07:00:00Z",
        cash="60",
        positions={"A": 2},
        prices={"A": "20"},
        opening_nav="100",
        price_basis="sip:1Min:raw",
    )
    args = snapshot, {"id": 9, "reset_count": 2}, cutoff, Decimal(60), {"A": 2, "sold": 0}
    verify_opening(*args, {"A": {"price": 20}})
    with pytest.raises(ValueError, match="checkpoint differs"):
        verify_opening(*args, {"A": {"price": 21}})


def buy():
    at = datetime(2026, 11, 10, 16, tzinfo=UTC)
    return dict(
        ticker="A",
        side="buy",
        qty=2,
        fill_price=10,
        transaction_cost=0.02,
        fee_bps=10,
        instrument_id=1,
        action_id="abc",
        accepted_at=at,
        fill_date=at.date(),
        context={
            "created_at": at.isoformat(),
            "recommendations": [
                {
                    "ticker": "A",
                    "tier": "OW",
                    "previous_tier": "OW",
                    "rank": 2,
                    "previous_rank": 3,
                    "evidence_id": "rating:1",
                }
            ],
        },
        result={
            "decision": {
                "actions": [
                    {
                        "type": "set_target_weight",
                        "instrument_id": "1",
                        "action_id": "abc",
                        "evidence_ids": ["rating:1"],
                    }
                ]
            }
        },
    )


def test_unknown_is_not_a_rank_only_buy():
    row = buy()
    assert category(row) == "unchanged_rank_rise"
    row["context"]["recommendations"][0]["previous_tier"] = None
    assert category(row) == "unknown"
    row = buy()
    row["result"]["decision"]["actions"][0]["evidence_ids"].append("other:1")
    assert category(row) == "other_evidence"
    row = buy()
    row["accepted_at"] = datetime(2026, 11, 9, tzinfo=UTC)
    assert category(row) == "unknown"


def test_skipped_buy_cannot_be_sold_and_fees_are_not_charged_twice():
    row = buy()
    sell = {
        **row,
        "side": "sell",
        "qty": 3,
        "fill_price": 12,
        "transaction_cost": 0.036,
        "fill_date": date(2026, 11, 11),
    }
    args = (
        Decimal(100),
        {"A": 1},
        [row, sell],
        {},
        [{"date": sell["fill_date"], "ticker": "A", "rate": 0.5}],
    )
    actual = replay("actual", *args)
    cash = replay("skip_rank_rise", *args)
    assert actual["nav"] == 115.944 and cash["nav"] == 111.988
    assert cash["fees"] == 0.012 and cash["size_limited"] == 1
    assert cash["dividend_sensitivity"] == 0.5 and actual["dividend_sensitivity"] == 1.5
