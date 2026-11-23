"""Read-side bridge: an offline locate cannot become evidence before receipt."""

from datetime import UTC, datetime, timedelta

from alpha_agent.paper.event_shadow_policy import equity_ticker, number
from alpha_agent.paper.market_clock import as_utc


async def import_receipt(pool, record):
    ticker = record.get("ticker")
    if not equity_ticker(ticker):
        raise ValueError("Invalid stock symbol")
    for field in ("source", "evidence_id"):
        if not isinstance(record.get(field), str) or not 1 <= len(record[field].strip()) <= 160:
            raise ValueError("A source and unique broker receipt reference are required")
    loan_id = record.get("loan_id")
    if loan_id is not None and (not isinstance(loan_id, str) or not 1 <= len(loan_id.strip()) <= 160):
        raise ValueError("Invalid loan continuation reference")
    source_at, until = as_utc(record["source_at"]), as_utc(record["valid_until"])
    if source_at > datetime.now(UTC) or until < source_at:
        raise ValueError("Invalid source time or validity")
    status, qty, rate = (
        record["status"],
        record.get("available_shares"),
        number(record.get("annual_rate")),
    )
    if status not in {"easy_to_borrow", "hard_to_borrow_located", "recalled", "not_shortable"}:
        raise ValueError("Invalid borrow status")
    if status in {"easy_to_borrow", "hard_to_borrow_located"} and (
        type(qty) is not int or qty <= 0 or rate is None or not 0 <= rate <= 5
    ):
        raise ValueError(
            "A lendable receipt must include dated inventory and annualized borrow rate"
        )
    return await pool.fetchval(
        """INSERT INTO event_shadow_borrow
        (source,evidence_id,ticker,source_at,valid_until,status,available_shares,annual_rate,loan_id)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) ON CONFLICT DO NOTHING RETURNING true""",
        record["source"],
        record["evidence_id"],
        ticker,
        source_at,
        until,
        status,
        qty,
        rate,
        loan_id,
    )


async def known_receipts(pool, at=None):
    at = at or datetime.now(UTC)
    # Include an expired latest receipt so it cannot accidentally reveal an older
    # open locate. Never substitute a database insert date for a broker source time.
    rows = await pool.fetch(
        """SELECT DISTINCT ON (ticker) ticker,source,evidence_id,loan_id,
        GREATEST(source_at,received_at) AS observed_at,valid_until,status,available_shares,annual_rate,
        (status='recalled') AS recalled FROM event_shadow_borrow
        WHERE source_at<=$1 AND received_at<=$1 AND received_at >= $2
        ORDER BY ticker,source_at DESC,received_at DESC""",
        at,
        at - timedelta(days=7),
    )
    return [dict(row) for row in rows]
