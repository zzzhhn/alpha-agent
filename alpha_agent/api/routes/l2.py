"""Read-only L2 forward-book evidence for the decision workspace."""
from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter

from alpha_agent.api.dependencies import get_db_pool

router = APIRouter(prefix="/api/l2", tags=["l2"])


async def _continuous_account(pool, *, strategy_name: str) -> dict[str, Any] | None:
    row = await pool.fetchrow(
        """
        SELECT s.id AS strategy_id, s.version, a.initial_cash, a.cash, a.nav,
               a.start_after_run_id, a.last_fill_date,
               (SELECT count(*) FROM l2_position p
                WHERE p.strategy_id=s.id AND p.qty>0) AS positions,
               (SELECT count(*) FROM l2_order o
                WHERE o.strategy_id=s.id AND o.status='pending') AS pending,
               (SELECT COALESCE(sum(o.transaction_cost),0) FROM l2_order o
                WHERE o.strategy_id=s.id) AS costs,
               (SELECT turnover FROM l2_equity_daily e
                WHERE e.strategy_id=s.id ORDER BY as_of_date DESC LIMIT 1) AS latest_turnover
        FROM l2_strategy s
        JOIN l2_account a ON a.strategy_id=s.id
        WHERE s.name=$1
        ORDER BY s.version DESC LIMIT 1
        """,
        strategy_name,
    )
    if row is None:
        return None
    nav = float(row["nav"])
    initial = float(row["initial_cash"])
    return {
        "status": "active" if row["last_fill_date"] else "awaiting_forward_run",
        "strategy_id": int(row["strategy_id"]),
        "strategy_version": int(row["version"]),
        "accounting": "continuous_share_delta",
        "initial_cash": initial,
        "nav": nav,
        "cash": float(row["cash"]),
        "cumulative_return": nav / initial - 1.0 if initial else None,
        "positions": int(row["positions"] or 0),
        "pending_orders": int(row["pending"] or 0),
        "transaction_costs": float(row["costs"] or 0.0),
        "latest_turnover": (
            float(row["latest_turnover"]) if row["latest_turnover"] is not None else None
        ),
        "last_fill_date": row["last_fill_date"].isoformat() if row["last_fill_date"] else None,
        "start_after_run_id": int(row["start_after_run_id"]),
    }


def _compound(returns: list[float | None]) -> float:
    value = 1.0
    for ret in returns:
        if ret is not None and math.isfinite(float(ret)):
            value *= 1.0 + float(ret)
    return value - 1.0


def _max_drawdown(returns: list[float | None]) -> float:
    nav = peak = 1.0
    worst = 0.0
    for ret in returns:
        if ret is None or not math.isfinite(float(ret)):
            continue
        nav *= 1.0 + float(ret)
        peak = max(peak, nav)
        worst = min(worst, nav / peak - 1.0)
    return worst


def _beta(strategy: list[float], benchmark: list[float]) -> float | None:
    pairs = [
        (s, b) for s, b in zip(strategy, benchmark)
        if math.isfinite(s) and math.isfinite(b)
    ]
    if len(pairs) < 3:
        return None
    s_mean = sum(s for s, _ in pairs) / len(pairs)
    b_mean = sum(b for _, b in pairs) / len(pairs)
    variance = sum((b - b_mean) ** 2 for _, b in pairs)
    if variance <= 1e-12:
        return None
    return sum((s - s_mean) * (b - b_mean) for s, b in pairs) / variance


@router.get("/summary")
async def l2_summary() -> dict[str, Any]:
    """Cost, benchmark, risk and exception evidence from the frozen L2 book."""
    pool = await get_db_pool()
    continuous = await _continuous_account(
        pool, strategy_name="canonical_top50_continuous"
    )
    strategic_continuous = await _continuous_account(
        pool, strategy_name="canonical_top50_continuous_strategic"
    )
    strategy = await pool.fetchrow(
        "SELECT id, name, version, params_json FROM l2_strategy "
        "WHERE name='canonical_top50' ORDER BY version DESC LIMIT 1"
    )
    if strategy is None:
        return {
            "status": "empty",
            "series": [],
            "sector_exposure": [],
            "continuous_account": continuous,
            "strategic_continuous_account": strategic_continuous,
        }

    strategy_id = int(strategy["id"])
    equity = await pool.fetch(
        "SELECT as_of_date, gross_return, net_return, benchmark_return, "
        "rsp_return, turnover, n_positions, stale_count, missing_count, cost_bps "
        "FROM l2_equity_daily WHERE strategy_id=$1 ORDER BY as_of_date",
        strategy_id,
    )
    latest_signal_date = await pool.fetchval(
        "SELECT MAX(signal_date) FROM l2_order WHERE strategy_id=$1",
        strategy_id,
    )
    sectors = []
    if latest_signal_date is not None:
        sectors = await pool.fetch(
            """
            SELECT COALESCE(cp.sector, 'Unknown') AS sector,
                   SUM(o.target_weight) AS weight, COUNT(*) AS positions
            FROM l2_order o
            LEFT JOIN company_profiles cp ON cp.ticker=o.ticker
            WHERE o.strategy_id=$1 AND o.signal_date=$2
              AND o.status IN ('pending', 'filled', 'exited')
            GROUP BY COALESCE(cp.sector, 'Unknown')
            ORDER BY weight DESC
            """,
            strategy_id,
            latest_signal_date,
        )
    order_exceptions = await pool.fetchrow(
        "SELECT COUNT(*) FILTER (WHERE status='unfilled') AS unfilled, "
        "COUNT(*) FILTER (WHERE status='exited') AS exited "
        "FROM l2_order WHERE strategy_id=$1",
        strategy_id,
    )

    net = [float(row["net_return"]) for row in equity if row["net_return"] is not None]
    spy = [
        float(row["benchmark_return"])
        for row in equity if row["benchmark_return"] is not None
    ]
    beta_pairs = [
        (float(row["net_return"]), float(row["benchmark_return"]))
        for row in equity
        if row["net_return"] is not None and row["benchmark_return"] is not None
    ]
    series: list[dict[str, Any]] = []
    nav = spy_nav = rsp_nav = 100.0
    rsp_started = False
    for row in equity:
        nav *= 1.0 + float(row["net_return"] or 0.0)
        spy_nav *= 1.0 + float(row["benchmark_return"] or 0.0)
        if row["rsp_return"] is not None:
            rsp_nav *= 1.0 + float(row["rsp_return"])
            rsp_started = True
        series.append({
            "date": row["as_of_date"].isoformat(),
            "nav": nav,
            "spy": spy_nav,
            "rsp": rsp_nav if rsp_started else None,
        })

    cost_sensitivity = {}
    for bps in (5, 10, 20):
        adjusted = [
            float(row["gross_return"] or 0.0)
            - 2.0 * bps / 10000.0 * float(row["turnover"] or 0.0)
            for row in equity
        ]
        cost_sensitivity[str(bps)] = _compound(adjusted)

    return {
        "status": "ready" if equity else "accumulating",
        "strategy_id": strategy_id,
        "strategy_name": strategy["name"],
        "strategy_version": int(strategy["version"]),
        "periods": len(equity),
        "net_return": _compound(net),
        "spy_return": _compound(spy),
        "rsp_return": (
            _compound([
                float(row["rsp_return"])
                for row in equity if row["rsp_return"] is not None
            ])
            if any(row["rsp_return"] is not None for row in equity)
            else None
        ),
        "beta_spy": _beta(
            [pair[0] for pair in beta_pairs],
            [pair[1] for pair in beta_pairs],
        ),
        "max_drawdown": _max_drawdown(net),
        "mean_turnover": (
            sum(float(row["turnover"] or 0.0) for row in equity) / len(equity)
            if equity else None
        ),
        "cost_sensitivity": cost_sensitivity,
        "exceptions": {
            "unfilled": int(order_exceptions["unfilled"] or 0),
            "exited": int(order_exceptions["exited"] or 0),
            "stale_marks": sum(int(row["stale_count"] or 0) for row in equity),
            "missing_marks": sum(int(row["missing_count"] or 0) for row in equity),
        },
        "latest_signal_date": (
            latest_signal_date.isoformat() if latest_signal_date else None
        ),
        "latest_positions": int(equity[-1]["n_positions"] or 0) if equity else 0,
        "series": series,
        "sector_exposure": [
            {
                "sector": row["sector"],
                "weight": float(row["weight"] or 0.0),
                "positions": int(row["positions"] or 0),
            }
            for row in sectors
        ],
        "continuous_account": continuous,
        "strategic_continuous_account": strategic_continuous,
    }
