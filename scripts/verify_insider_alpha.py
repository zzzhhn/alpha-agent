"""Quick verification of the insider_net_dollars factor's alpha.

Runs after Form 4 pipeline finishes to confirm the new operand produces
a meaningful signal vs the platform's existing factors. Reports:
  1. Coverage: how many ticker-days have any insider activity
  2. Signal sparsity (most ticker-days are NaN by design)
  3. Factor backtest results (long_short, sector-neutral, vs SPY) for
     several smoothed variants (5d, 30d, 60d, 180d rolling means)
  4. Comparison to existing Tier-A factors from long_short selection
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from alpha_agent.factor_engine.factor_backtest import _load_panel, run_factor_backtest
from alpha_agent.core.types import FactorSpec


# Test smoothing windows. Cohen-Malloy-Pomorski 2012 found 60-180d
# rolling net buying carries the alpha; single-day signal is too noisy.
SMOOTH_WINDOWS = [5, 30, 60, 180]


def main() -> int:
    panel = _load_panel()
    print(f"=== panel: T={len(panel.dates)} N={len(panel.tickers)} ===")
    if not panel.insider_form4:
        print("panel.insider_form4 is None — Form 4 parquet missing or empty.")
        return 1

    nd = panel.insider_form4["insider_net_dollars"]
    nb = panel.insider_form4["insider_n_buys"]
    ns = panel.insider_form4["insider_n_sells"]
    n_active = (~np.isnan(nd)).sum()
    print(f"\n=== coverage ===")
    print(f"  active ticker-days (any insider tx): {n_active:,} / {nd.size:,} ({100*n_active/nd.size:.2f}%)")
    print(f"  net_dollars: median={np.nanmedian(nd):,.0f}  "
          f"mean={np.nanmean(nd):,.0f}  std={np.nanstd(nd):,.0f}")
    print(f"  n_buys: total={int(np.nansum(nb)):,}  n_sells: total={int(np.nansum(ns)):,}")
    n_pos = int((nd > 0).sum())
    n_neg = int((nd < 0).sum())
    print(f"  positive (net buying) days: {n_pos:,}; negative (net selling): {n_neg:,}")

    print(f"\n=== factor backtest: rank(ts_mean(insider_net_dollars, W)) long_short sector-neutral ===")
    print(f"{'window':>10} | {'test SR':>8} | {'IC':>7} | {'IC p':>6} | {'PSR':>5} | "
          f"{'α (ann)':>8} | {'α-t':>6} | {'α-p':>6}")
    print("-" * 80)
    for w in SMOOTH_WINDOWS:
        spec = FactorSpec(
            name=f"insider_{w}d", hypothesis="",
            expression=f"rank(ts_mean(insider_net_dollars, {w}))",
            operators_used=["rank", "ts_mean"],
            lookback=w, universe="SP500", justification="",
        )
        try:
            r = run_factor_backtest(spec, direction="long_short", neutralize="sector")
            m = r.test_metrics
            print(f"{w:>9}d | {m.sharpe:>+8.3f} | {m.ic_spearman:>+7.4f} | "
                  f"{m.ic_pvalue:>6.3f} | {m.psr:>5.2f} | "
                  f"{(r.alpha_annualized or 0)*100:>+7.2f}% | "
                  f"{r.alpha_t_stat or 0:>+6.2f} | {r.alpha_pvalue or 1:>6.3f}")
        except Exception as exc:
            print(f"{w:>9}d | FAIL: {type(exc).__name__}: {str(exc)[:60]}")

    print(f"\n=== count-based variant: rank(subtract(insider_n_buys, insider_n_sells)) ===")
    spec = FactorSpec(
        name="insider_count_net_60", hypothesis="",
        expression="rank(ts_mean(subtract(insider_n_buys, insider_n_sells), 60))",
        operators_used=["rank", "ts_mean", "subtract"],
        lookback=60, universe="SP500", justification="",
    )
    try:
        r = run_factor_backtest(spec, direction="long_short", neutralize="sector")
        m = r.test_metrics
        print(f"  count_net_60d: SR={m.sharpe:+.3f}  IC_p={m.ic_pvalue:.3f}  "
              f"PSR={m.psr:.2f}  α-t={r.alpha_t_stat:+.2f} α-p={r.alpha_pvalue:.3f}")
    except Exception as exc:
        print(f"  count_net_60d: FAIL {exc}")

    print(f"\n=== reference: existing Tier-A factor for sanity ===")
    spec = FactorSpec(
        name="ep_ref", hypothesis="",
        expression="rank(divide(net_income_adjusted, multiply(close, shares_outstanding)))",
        operators_used=["rank", "divide", "multiply"],
        lookback=5, universe="SP500", justification="",
    )
    r = run_factor_backtest(spec, direction="long_short", neutralize="sector")
    print(f"  ep (E/P sector-neutral long_short): "
          f"SR={r.test_metrics.sharpe:+.3f}  α-t={r.alpha_t_stat:+.2f} α-p={r.alpha_pvalue:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
