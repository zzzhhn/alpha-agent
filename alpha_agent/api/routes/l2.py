"""Read-only L2 forward-book evidence for the decision workspace."""
from __future__ import annotations

import json
import math
from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.api.cache import TTLCache
from alpha_agent.backtest.investment_shadow import replay_targets
from alpha_agent.market_session import latest_completed_xnys_session, next_xnys_session, xnys_close, xnys_sessions

router = APIRouter(prefix="/api/l2", tags=["l2"])
_study_cache = TTLCache(default_ttl=600)


@router.get("/turnover-study")
async def turnover_study(sleeve: Literal["tactical", "strategic"] = "strategic") -> dict:
    """Bounded on-demand replay, no writes, new market downloads or LLM calls."""
    cached = _study_cache.get(sleeve)
    if cached is not None:
        return cached
    pool = await get_db_pool()
    name = "canonical_top50_continuous" + ("_strategic" if sleeve == "strategic" else "")
    strategy = await pool.fetchrow("SELECT id,params_json FROM l2_strategy WHERE name=$1 ORDER BY version DESC LIMIT 1", name)
    if strategy is None:
        return {"status": "insufficient_history", "sleeve": sleeve}
    params = json.loads(strategy["params_json"])
    end = latest_completed_xnys_session()
    orders = await pool.fetch(
        "SELECT signal_date,ticker,target_weight,generated_at,source_policy_id FROM l2_order "
        "WHERE strategy_id=$1 AND signal_date >= $2 AND signal_date <= $3 ORDER BY signal_date,ticker LIMIT 10001",
        strategy["id"], end - timedelta(days=120), end,
    )
    if len(orders) > 10000:
        return {"status": "history_limit", "sleeve": sleeve}
    groups = {}
    for order in orders:
        groups.setdefault(order["signal_date"], []).append(order)
    targets = {}
    excluded = 0
    for signal_day, batch in groups.items():
        execution_day = next_xnys_session(signal_day)
        if execution_day > end:
            continue
        if any(o["generated_at"] >= xnys_close(execution_day) or o["source_policy_id"] != params.get("policy_id") for o in batch):
            excluded += 1
            continue
        targets[execution_day] = {o["ticker"]: float(o["target_weight"]) for o in batch}
    if len(targets) < 2:
        return {"status": "insufficient_history", "sleeve": sleeve, "causal_targets": len(targets), "excluded_batches": excluded}
    start = min(targets)
    tickers = sorted({"SPY", "RSP"} | {t for batch in targets.values() for t in batch})
    rows = await pool.fetch("SELECT date,ticker,close FROM daily_prices WHERE ticker=ANY($1::text[]) AND date BETWEEN $2 AND $3", tickers, start, end)
    prices = {(r["date"], r["ticker"]): float(r["close"]) for r in rows if r["close"] is not None}
    sessions = xnys_sessions(start, end)
    modes = ("recorded", "monthly", "band", "spy", "rsp", "cash")
    result = {
        "status": "retrospective_only", "sleeve": sleeve, "policy_id": params.get("policy_id"),
        "from": start.isoformat(), "to": end.isoformat(), "causal_targets": len(targets),
        "excluded_batches": excluded, "live_policy_changed": False,
        "cost_bps_per_side": float(params.get("cost_bps", 10)),
        "results": [{"mode": mode, **replay_targets(sessions, targets, prices, mode=mode, cost_bps=float(params.get("cost_bps", 10)))} for mode in modes],
        "limitations": ["retrospective_not_forward", "monthly_uses_first_available_recorded_target",
                        "fractional_shares", "no_dividends_taxes_or_cash_interest", "no_claim_of_statistical_significance"],
    }
    _study_cache.set(sleeve, result)
    return result


@router.get("/evidence")
async def l2_evidence(sleeve: Literal["tactical", "strategic"] = "strategic") -> dict[str, Any]:
    """One policy, one continuous book. Never substitute legacy research P&L."""
    pool = await get_db_pool()
    name = "canonical_top50_continuous" + ("_strategic" if sleeve == "strategic" else "")
    account = await _continuous_account(pool, strategy_name=name)
    if account is None:
        return {"status": "not_initialized", "sleeve": sleeve, "series": []}
    sid = account["strategy_id"]
    params_raw = await pool.fetchval("SELECT params_json FROM l2_strategy WHERE id=$1", sid)
    params = json.loads(params_raw) if isinstance(params_raw, str) else (params_raw or {})
    rows = await pool.fetch(
        "SELECT as_of_date,nav,net_return,benchmark_return,rsp_return,missing_count "
        ",turnover FROM l2_equity_daily WHERE strategy_id=$1 ORDER BY as_of_date", sid,
    )
    exceptions = await pool.fetch(
        "SELECT exit_reason,count(*) AS n FROM l2_order "
        "WHERE strategy_id=$1 AND status='unfilled' GROUP BY exit_reason", sid,
    )
    latest_market = latest_completed_xnys_session()
    overdue = account["overdue_orders"]
    missing = sum(int(r["missing_count"] or 0) for r in rows)
    status = ("execution_delayed" if overdue else "history_gaps" if exceptions or missing
              else "forward_validation" if rows else "accumulating")
    # Compare all alternatives from the first executed close, with identical
    # endpoints. Missing benchmark intervals invalidate that comparison.
    comparison_rows = rows[1:]
    base_nav = float(rows[0]["nav"]) if rows and rows[0]["nav"] else None
    comparison = None
    if base_nav and len(rows) > 1 and rows[-1]["nav"] is not None:
        comparison = {
            "from": rows[0]["as_of_date"].isoformat(),
            "to": rows[-1]["as_of_date"].isoformat(),
            "strategy": float(rows[-1]["nav"]) / base_nav - 1,
            "spy": (_compound([r["benchmark_return"] for r in comparison_rows])
                    if all(r["benchmark_return"] is not None for r in comparison_rows) else None),
            "rsp": (_compound([r["rsp_return"] for r in comparison_rows])
                    if all(r["rsp_return"] is not None for r in comparison_rows) else None),
            "cash_no_interest": 0.0,
        }
    return {
        "status": status, "sleeve": sleeve, "account": account,
        "policy_id": params.get("policy_id"), "execution": params.get("execution"),
        "top_n": params.get("top_n"), "cost_bps_per_side": params.get("cost_bps"),
        "rebalance": params.get("rebalance"),
        "as_of": account["last_fill_date"], "expected_market_date": latest_market.isoformat(),
        "valuation_current": account["last_fill_date"] == latest_market.isoformat(),
        "overdue_orders": overdue,
        "exceptions": [{"reason": r["exit_reason"], "count": int(r["n"])} for r in exceptions],
        "missing_marks": missing,
        "observations": len(rows),
        "sample_unit": "rebalance_valuation_not_independent_trials",
        "observed_max_drawdown": _max_drawdown([r["net_return"] for r in rows]),
        "mean_rebalance_turnover": (sum(float(r["turnover"] or 0) for r in rows) / len(rows)) if rows else None,
        "decision": "observe_without_new_trade",
        "research_protocol": {
            "status": "available_on_demand", "live_policy_changed": False,
            "comparisons": ["weekly_frozen", "monthly_frozen", "weekly_no_trade_band"],
            "required_metrics": ["net_return", "drawdown", "turnover", "sector_exposure", "benchmark_excess"],
            "promotion": "new_version_after_out_of_sample_review",
        },
        "comparison": comparison,
        "series": [{"date": r["as_of_date"].isoformat(), "nav": float(r["nav"]) if r["nav"] is not None else None} for r in rows],
        "evidence_status": "unproven", "personalized": False,
        "limitations": ["rebalance_date_valuations_only", "simulation_not_broker_fills",
                        "no_dividend_tax_or_cash_interest_adjustment"],
    }


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
    due = int(await pool.fetchval(
        "SELECT count(*) FROM l2_order WHERE strategy_id=$1 AND status='pending' AND signal_date<$2",
        int(row["strategy_id"]), latest_completed_xnys_session(),
    ) or 0)
    return {
        "status": "execution_delayed" if due else "active" if row["last_fill_date"] else "awaiting_forward_run",
        "overdue_orders": due,
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
