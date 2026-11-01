"""Read-only reporting of actual marks. Missing sessions are not zero returns."""
from __future__ import annotations

import math

from alpha_agent.market_session import xnys_sessions


def performance_series(rows, *, initial_cash: float, prices: dict, cost_bps: float) -> dict:
    if not rows:
        return {"series": [], "comparison": None, "windows": {}, "missing_sessions": 0}
    by_date = {r["as_of_date"]: r for r in rows}
    sessions = xnys_sessions(rows[0]["as_of_date"], rows[-1]["as_of_date"])
    first = sessions[0]
    series = []
    peak, drawdown = initial_cash, 0.0
    for day in sessions:
        row = by_date.get(day)
        stale = bool(row and (row["stale_count"] or row["missing_count"]))
        nav = float(row["nav"]) if row and row["nav"] is not None else None
        if nav is not None and not math.isfinite(nav):
            nav = None
        if nav is not None:
            peak = max(peak, nav)
            drawdown = min(drawdown, nav / peak - 1)
        point = {"date": day.isoformat(), "nav": nav,
                 "net": 100 * nav / initial_cash if nav is not None else None,
                 "stale": stale, "cash": 100.0}
        for ticker in ("SPY", "RSP"):
            start, value = prices.get((first, ticker)), prices.get((day, ticker))
            point[ticker.lower()] = (100 * value / start / (1 + cost_bps / 10000)
                                    if start and value else None)
        series.append(point)
    last = series[-1]
    comparison = {"from": first.isoformat(), "to": last["date"],
                  "strategy": last["net"] / 100 - 1 if last["net"] is not None else None,
                  "spy": last["spy"] / 100 - 1 if last["spy"] is not None else None,
                  "rsp": last["rsp"] / 100 - 1 if last["rsp"] is not None else None,
                  "cash_no_interest": 0.0, "includes_initial_costs": True}
    windows = {}
    for n in (5, 21):
        window = series[-(n + 1):]
        valid = (len(window) == n + 1 and
                 all(p["net"] is not None and not p["stale"] for p in window))
        result = {"sessions": n, "status": "ready" if valid else "insufficient_complete_marks",
                  "net_return": None, "spy_return": None, "rsp_return": None}
        if valid:
            for key, target in (("net", "net_return"), ("spy", "spy_return"), ("rsp", "rsp_return")):
                if all(p[key] is not None for p in window) and window[0][key] > 0:
                    result[target] = window[-1][key] / window[0][key] - 1
            result.update({"from": window[0]["date"], "to": window[-1]["date"]})
        windows[str(n)] = result
    return {"series": series, "comparison": comparison, "windows": windows,
            "observed_max_drawdown": drawdown,
            "missing_sessions": len(sessions) - len(rows),
            "stale_sessions": sum(p["stale"] for p in series)}
