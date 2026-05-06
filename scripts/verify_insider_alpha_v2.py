"""Insider Form 4 alpha verifier v2 — walk-forward + medium-cap.

Run after the 3y backfill completes. Strengthens the v1 verifier:

  1. v1 baseline: full SP500, static 80/20 train/test, sector-neutral
     long-short. Reports the dollar variant (5/30/60/180d) + count variant.
  2. **Walk-forward** for the borderline-significant 60d count variant.
     Rolling 252d windows stepping 63d → ~9 OOS samples on a 752d panel.
     Lets us see if the α-t holds across sub-periods or hides in one.
  3. **Medium-cap subset**: drop top 20% of tickers by avg cap. Per
     CMP 2012, insider trading alpha is concentrated in smaller-cap
     names where 10b5-1 mechanical tax-driven sales are less dominant.
     Run static + walk-forward for the count variant.

The medium-cap subset is implemented by monkey-patching `_load_panel`
to mask out high-cap tickers via the panel's `is_member` field. The
factor evaluator (kernel.evaluate_factor_full) NaNs out non-member cells,
so they cannot enter the long/short basket.
"""
from __future__ import annotations

import sys
import warnings
from dataclasses import replace
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

import alpha_agent.factor_engine.factor_backtest as fb
from alpha_agent.factor_engine.factor_backtest import run_factor_backtest
from alpha_agent.core.types import FactorSpec


SMOOTH_WINDOWS = [5, 30, 60, 180]
WF_WINDOW_DAYS = 252
WF_STEP_DAYS = 63
MEDIUM_CAP_DROP_TOP_PCT = 0.20


def _make_medium_cap_loader(drop_top_pct: float, orig_loader):
    """Return a `_load_panel` replacement that drops the top N% of tickers
    by avg cap by AND-ing them out of `is_member`. Avg cap is used (not
    last-day cap) so a ticker that crossed the threshold mid-panel gets a
    stable inclusion decision.

    `orig_loader` is captured at patch time so the restore logic can put
    back exactly what was there.
    """
    def _patched():
        p = orig_loader()
        if p.cap is None:
            print("WARNING: panel.cap is None; medium-cap filter is a no-op")
            return p
        # Per-ticker avg cap, ignoring NaN. Some tickers may be all-NaN if
        # they were never SP500 — those get a NaN avg, which compares False
        # to any real threshold, so they end up KEPT. AND with is_member
        # then masks them out via the existing membership logic.
        avg_cap = np.nanmean(p.cap, axis=0)
        threshold = np.nanpercentile(avg_cap, 100 * (1 - drop_top_pct))
        keep = (avg_cap < threshold) & np.isfinite(avg_cap)
        n_keep = int(keep.sum())
        n_total = int(np.isfinite(avg_cap).sum())
        print(f"  [medium-cap filter] keep {n_keep}/{n_total} tickers "
              f"(threshold ${threshold/1e9:.1f}B avg cap)")
        if p.is_member is None:
            new_member = np.broadcast_to(keep, p.close.shape).copy()
        else:
            new_member = p.is_member & keep[np.newaxis, :]
        return replace(p, is_member=new_member)

    return _patched


def _spec(name: str, expression: str, ops: list[str], lookback: int) -> FactorSpec:
    return FactorSpec(
        name=name, hypothesis="", expression=expression,
        operators_used=ops, lookback=lookback, universe="SP500",
        justification="",
    )


def _print_static_row(label: str, r) -> None:
    m = r.test_metrics
    print(f"  {label:<28s}  SR={m.sharpe:+.3f}  IC={m.ic_spearman:+.4f}  "
          f"IC_p={m.ic_pvalue:.3f}  PSR={m.psr:.2f}  "
          f"α-t={r.alpha_t_stat:+.2f}  α-p={r.alpha_pvalue:.3f}")


def _print_wf_summary(label: str, r) -> None:
    if r.walk_forward is None:
        print(f"  {label}: walk_forward=None (mode=static run?)")
        return
    sharpes = [w.get("test_sharpe", 0.0) for w in r.walk_forward]
    ics = [w.get("test_ic", 0.0) for w in r.walk_forward]
    n_pos = sum(1 for s in sharpes if s > 0)
    print(f"  {label}: {len(sharpes)} windows  "
          f"mean_SR={np.mean(sharpes):+.3f}  median_SR={np.median(sharpes):+.3f}  "
          f"win_rate={n_pos}/{len(sharpes)}  "
          f"mean_IC={np.mean(ics):+.4f}")


def _coverage_report(panel) -> None:
    nd = panel.insider_form4["insider_net_dollars"]
    nb = panel.insider_form4["insider_n_buys"]
    ns = panel.insider_form4["insider_n_sells"]
    n_active = (~np.isnan(nd)).sum()
    print(f"  panel: T={len(panel.dates)} N={len(panel.tickers)}  "
          f"date {panel.dates[0]} → {panel.dates[-1]}")
    print(f"  active ticker-days: {n_active:,} / {nd.size:,} "
          f"({100*n_active/nd.size:.2f}%)")
    print(f"  net_dollars: median={np.nanmedian(nd):,.0f}  "
          f"std={np.nanstd(nd):,.0f}")
    print(f"  n_buys total={int(np.nansum(nb)):,}  "
          f"n_sells total={int(np.nansum(ns)):,}")


def main() -> int:
    panel = fb._load_panel()
    print("=" * 80)
    print("=== coverage ===")
    if not panel.insider_form4:
        print("panel.insider_form4 is None — Form 4 parquet missing or empty.")
        return 1
    _coverage_report(panel)

    # ── Block 1: full SP500 static (v1 baseline) ──
    print()
    print("=" * 80)
    print("=== full SP500, static train/test (v1 baseline) ===")
    for w in SMOOTH_WINDOWS:
        spec = _spec(f"insider_dollar_{w}d",
                     f"rank(ts_mean(insider_net_dollars, {w}))",
                     ["rank", "ts_mean"], w)
        r = run_factor_backtest(spec, direction="long_short", neutralize="sector")
        _print_static_row(f"dollar_{w}d", r)

    spec_count60 = _spec("insider_count_60d",
                         "rank(ts_mean(subtract(insider_n_buys, insider_n_sells), 60))",
                         ["rank", "ts_mean", "subtract"], 60)
    r_count = run_factor_backtest(spec_count60, direction="long_short", neutralize="sector")
    _print_static_row("count_60d", r_count)

    # ── Block 2: full SP500 walk-forward (count variant only) ──
    print()
    print("=" * 80)
    print(f"=== full SP500, walk-forward (window={WF_WINDOW_DAYS}d step={WF_STEP_DAYS}d) ===")
    r_wf = run_factor_backtest(
        spec_count60, direction="long_short", neutralize="sector",
        mode="walk_forward",
        wf_window_days=WF_WINDOW_DAYS, wf_step_days=WF_STEP_DAYS,
    )
    _print_wf_summary("count_60d_full", r_wf)
    if r_wf.walk_forward:
        for i, w in enumerate(r_wf.walk_forward):
            print(f"    win {i+1:>2}: SR={w.get('test_sharpe', 0):+.3f}  "
                  f"IC={w.get('test_ic', 0):+.4f}  "
                  f"alpha_t={w.get('alpha_t_stat', 0):+.2f}")

    # ── Block 3: medium-cap subset, static + walk-forward ──
    print()
    print("=" * 80)
    print(f"=== medium-cap subset (drop top {int(MEDIUM_CAP_DROP_TOP_PCT*100)}% by avg cap) ===")
    orig_loader = fb._load_panel
    fb._load_panel = _make_medium_cap_loader(MEDIUM_CAP_DROP_TOP_PCT, orig_loader)
    try:
        for w in SMOOTH_WINDOWS:
            spec = _spec(f"insider_dollar_{w}d_mc",
                         f"rank(ts_mean(insider_net_dollars, {w}))",
                         ["rank", "ts_mean"], w)
            r = run_factor_backtest(spec, direction="long_short", neutralize="sector")
            _print_static_row(f"dollar_{w}d (mc)", r)

        r_count_mc = run_factor_backtest(spec_count60, direction="long_short", neutralize="sector")
        _print_static_row("count_60d (mc)", r_count_mc)

        r_wf_mc = run_factor_backtest(
            spec_count60, direction="long_short", neutralize="sector",
            mode="walk_forward",
            wf_window_days=WF_WINDOW_DAYS, wf_step_days=WF_STEP_DAYS,
        )
        _print_wf_summary("count_60d_mc_walkforward", r_wf_mc)
    finally:
        # Restore default loader so the E/P sanity (and any later import) sees
        # the unfiltered SP500.
        fb._load_panel = orig_loader

    # ── Block 4: reference E/P sanity ──
    print()
    print("=" * 80)
    print("=== reference E/P (sanity, full SP500) ===")
    spec_ep = _spec("ep_ref",
                    "rank(divide(net_income_adjusted, multiply(close, shares_outstanding)))",
                    ["rank", "divide", "multiply"], 5)
    r_ep = run_factor_backtest(spec_ep, direction="long_short", neutralize="sector")
    _print_static_row("ep_5d", r_ep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
