"""Offline kernel replay; point PYTHONPATH at either checkout and pass one parquet."""
import json
import sys

import pandas as pd

from alpha_agent.core.types import FactorSpec
from alpha_agent.factor_engine.factor_backtest import _Panel
from alpha_agent.factor_engine.kernel import KernelParams, run_kernel


def replay(path):
    # Fixed illustration, not a point-in-time index membership or an investment study.
    tickers = "AAPL ABBV AMGN AMZN BA CAT CVX DIS GE GOOGL HD IBM JPM KO MCD MSFT NKE NVDA PG XOM".split()
    rows = pd.read_parquet(path, filters=[("ticker", "in", tickers + ["SPY"])],
                           columns=["ticker", "date", "open", "high", "low", "close", "volume"])
    rows["date"] = pd.to_datetime(rows["date"])
    rows = rows.loc[rows.date.between("2025-01-02", "2025-06-30")]
    prices = rows.pivot(index="date", columns="ticker", values="close").sort_index()

    def field(key):
        return rows.pivot(index="date", columns="ticker", values=key).reindex(
            index=prices.index, columns=tickers).to_numpy(dtype=float)

    if prices[tickers + ["SPY"]].isna().any().any() or len(prices) < 100:
        raise ValueError("fixed replay requires complete prices")
    panel = _Panel(dates=prices.index.to_numpy(), tickers=tuple(tickers), close=field("close"),
                   open_=field("open"), high=field("high"), low=field("low"), volume=field("volume"),
                   benchmark_close=prices["SPY"].to_numpy())
    spec = FactorSpec(name="share_volume", expression="volume", hypothesis="Replay control",
                      justification="Frozen data and parameters", universe="SP500", lookback=5, operators_used=[])
    out = {"sessions": len(prices), "first": str(prices.index[0].date()), "last": str(prices.index[-1].date())}
    for label, direction in (("half_and_half", "long_short"), ("short_control", "short_only")):
        k = run_kernel(panel, spec, KernelParams(top_pct=0.5, bottom_pct=0.5,
                       direction=direction, transaction_cost_bps=10.0))
        out[label] = {"first_net_exposure": round(float(k.weights[0].sum()), 8),
                      "ending_nav": round(float(k.equity[-1]), 2),
                      "test_return_pct": round(k.test_metrics.total_return * 100, 4),
                      "test_drawdown_pct": round(k.test_metrics.max_drawdown * 100, 4)}
    return out


if __name__ == "__main__":
    print(json.dumps(replay(sys.argv[1]), indent=2))
