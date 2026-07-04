"""Parse a BRAIN PnL recordset into chart-ready cumulative points.

BRAIN's /alphas/{id}/recordsets/pnl returns {schema, records}, where each record
is a row like [date, ...numeric columns...]. We take the date (first cell) and
the last numeric cell as the cumulative PnL, producing [{date, pnl}] for a
line chart. Defensive: skips malformed rows rather than raising."""
from __future__ import annotations

from typing import Any


def pnl_to_points(recordset: Any) -> list[dict]:
    """[{'date': str, 'pnl': float}] from a BRAIN PnL recordset. Empty on any
    unexpected shape (the UI just shows 'no PnL')."""
    if not isinstance(recordset, dict):
        return []
    records = recordset.get("records")
    if not isinstance(records, list):
        return []
    points: list[dict] = []
    for rec in records:
        if not isinstance(rec, (list, tuple)) or len(rec) < 2:
            continue
        date = rec[0]
        pnl: float | None = None
        for cell in reversed(rec[1:]):  # last numeric column = cumulative PnL
            if isinstance(cell, (int, float)):
                pnl = float(cell)
                break
        if isinstance(date, str) and pnl is not None:
            points.append({"date": date, "pnl": pnl})
    return points


def yearly_to_rows(recordset: Any) -> list[dict]:
    """[{col: value}] from a BRAIN yearly-stats recordset — the per-year IS
    Summary table. Maps each record onto the schema's column names so the UI can
    render year/sharpe/turnover/fitness/returns/drawdown/margin/long/short."""
    if not isinstance(recordset, dict):
        return []
    records = recordset.get("records")
    schema = recordset.get("schema") or {}
    props = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(records, list):
        return []
    # Column names from the schema; fall back to positional keys.
    cols = (
        [p.get("name") for p in props if isinstance(p, dict)]
        if isinstance(props, list)
        else None
    )
    out: list[dict] = []
    for rec in records:
        if not isinstance(rec, (list, tuple)):
            continue
        if cols and len(cols) == len(rec):
            out.append({c: v for c, v in zip(cols, rec) if c})
        else:
            out.append({str(i): v for i, v in enumerate(rec)})
    return out
