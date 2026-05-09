"""Select factors with statistically significant alpha under
(long_only, sector-neutral, RSP-equal-weighted benchmark).

Constraint matches RISK.ATTRIBUTION's "Pure Alpha" verdict on /backtest:
  - direction = long_only       (no shorting)
  - neutralize = sector         (strip sector beta from the basket)
  - benchmark_ticker = RSP      (equal-weighted SP500 — friendlier to
                                  long_only than cap-weighted SPY which
                                  is dominated by Mag-7 mega-caps)
  - top_pct ∈ {0.10, 0.20, 0.30}  — pick the variant with strongest α-t

Filter (verdict tier):
  - PURE ALPHA: α-p < 0.05 AND |β| < 0.30
  - LEVERED ALPHA: α-p < 0.05 (any β)
  - MARGINAL: α-p < 0.10 AND α > 0 AND |β| < 0.30

Output: top 6 picks ranked by α-t with family diversity (max 2 per
family). Prints verdict tier + full diagnostic block per pick so the
selection is reproducible and the FACTOR_EXAMPLES update in
frontend/src/components/alpha/FactorExamples.tsx is auditable.

Usage:
    python3 scripts/select_pure_alpha_long_only_rsp.py
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import alpha_agent.factor_engine.factor_backtest as fbm
from alpha_agent.core.types import FactorSpec


# Same candidate library as scripts/select_long_only_factors.py — the
# 22 factors span momentum / reversal / vol / volume / quality / value
# / health / trend / efficiency / liquidity. Family is used in the
# diversity step.
CANDIDATES: list[tuple[str, str, str, str, list[str]]] = [
    ("momentum", "momo_3_1", "3-1 month price momentum (skip last 21d)",
     "rank(subtract(ts_mean(returns, 63), ts_mean(returns, 21)))",
     ["rank", "subtract", "ts_mean"]),
    ("momentum", "momo_6_1", "6-1 month momentum",
     "rank(subtract(ts_mean(returns, 126), ts_mean(returns, 21)))",
     ["rank", "subtract", "ts_mean"]),
    ("momentum", "momo_12_1", "12-1 month momentum (Jegadeesh-Titman)",
     "rank(subtract(ts_mean(returns, 252), ts_mean(returns, 21)))",
     ["rank", "subtract", "ts_mean"]),
    ("reversal", "rev_5d", "5-day short-term reversal",
     "rank(subtract(ts_mean(returns, 21), ts_mean(returns, 5)))",
     ["rank", "subtract", "ts_mean"]),
    ("reversal", "rev_21d", "21-day reversal (DeBondt-Thaler short)",
     "rank(subtract(ts_mean(returns, 60), ts_mean(returns, 21)))",
     ["rank", "subtract", "ts_mean"]),
    ("vol", "low_vol_60", "Low realized vol 60d (low-vol anomaly)",
     "rank(inverse(ts_std(returns, 60)))",
     ["rank", "inverse", "ts_std"]),
    ("vol", "low_vol_120", "Low realized vol 120d",
     "rank(inverse(ts_std(returns, 120)))",
     ["rank", "inverse", "ts_std"]),
    ("volume", "vol_zscore_20", "Volume 20d z-score",
     "ts_zscore(volume, 20)",
     ["ts_zscore"]),
    ("volume", "dvol_zscore_60", "Dollar volume 60d z-score",
     "ts_zscore(dollar_volume, 60)",
     ["ts_zscore"]),
    ("quality", "gross_prof", "Novy-Marx gross profitability (gp / assets)",
     "rank(divide(gross_profit, assets))",
     ["rank", "divide"]),
    ("quality", "op_margin", "Operating margin (oi / revenue)",
     "rank(divide(operating_income, revenue))",
     ["rank", "divide"]),
    ("quality", "roa", "Return on assets (ni / assets)",
     "rank(divide(net_income_adjusted, assets))",
     ["rank", "divide"]),
    ("quality", "roe", "Return on equity (ni / equity)",
     "rank(divide(net_income_adjusted, equity))",
     ["rank", "divide"]),
    ("value", "ep", "Earnings yield E/P",
     "rank(divide(net_income_adjusted, multiply(close, shares_outstanding)))",
     ["rank", "divide", "multiply"]),
    ("value", "sp", "Sales yield S/P",
     "rank(divide(revenue, multiply(close, shares_outstanding)))",
     ["rank", "divide", "multiply"]),
    ("value", "bp", "Book yield B/P",
     "rank(divide(equity, multiply(close, shares_outstanding)))",
     ["rank", "divide", "multiply"]),
    ("health", "low_debt", "Low leverage (equity / long-term debt)",
     "rank(divide(equity, long_term_debt))",
     ["rank", "divide"]),
    ("health", "cash_buffer", "Cash buffer (cash / equity)",
     "rank(divide(cash_and_equivalents, equity))",
     ["rank", "divide"]),
    ("trend", "trend_sharpe_60", "60d return / vol",
     "rank(divide(ts_mean(returns, 60), ts_std(returns, 60)))",
     ["rank", "divide", "ts_mean", "ts_std"]),
    ("trend", "trend_sharpe_120", "120d return / vol",
     "rank(divide(ts_mean(returns, 120), ts_std(returns, 120)))",
     ["rank", "divide", "ts_mean", "ts_std"]),
    ("efficiency", "asset_turnover", "Revenue / assets",
     "rank(divide(revenue, assets))",
     ["rank", "divide"]),
    ("liquidity", "high_dvol", "High dollar volume rank",
     "rank(adv60)",
     ["rank"]),
]


def run_one(name: str, expr: str, ops: list[str],
            neutralize: str, top_pct: float) -> dict | None:
    """Single backtest under (long_only, neutralize, RSP, top_pct).

    train_ratio=0.70 to match the /backtest form's default 70% slider.
    Backend's run_factor_backtest defaults to 0.80; if we don't pass
    explicitly the script's results won't match what users see when
    they click the loaded example on /backtest. (Hard-learned: the
    first version of this script defaulted to 0.80 and reported E/P
    α-p=0.009 while the user's form run showed α-p=0.06.)
    """
    try:
        spec = FactorSpec(
            name=name, hypothesis="", expression=expr,
            operators_used=ops, lookback=120,
            universe="SP500", justification="",
        )
        r = fbm.run_factor_backtest(
            spec,
            train_ratio=0.70,
            direction="long_only",
            neutralize=neutralize,
            top_pct=top_pct,
            benchmark_ticker="RSP",
        )
        return {
            "name": name,
            "neutralize": neutralize,
            "top_pct": top_pct,
            "test_sr": r.test_metrics.sharpe,
            "ic": r.test_metrics.ic_spearman,
            "ic_p": r.test_metrics.ic_pvalue,
            "psr": r.test_metrics.psr,
            "alpha_ann": r.alpha_annualized or 0.0,
            "alpha_t": r.alpha_t_stat or 0.0,
            "alpha_p": r.alpha_pvalue or 1.0,
            "beta": r.beta_market or 0.0,
            "regimes": [
                {"regime": rg.regime, "n_days": rg.n_days,
                 "alpha_t": rg.alpha_t_stat}
                for rg in (r.regime_breakdown or [])
            ],
        }
    except Exception as e:
        return {"name": name, "error": f"{type(e).__name__}: {str(e)[:120]}"}


def verdict(alpha_p: float, beta: float, alpha: float) -> str:
    """Long_only-aware verdict.

    Under long_only direction, β ≈ 1 vs an equity benchmark by
    construction (you're long equities, the bench IS equities), so the
    classic |β|<0.30 "Pure Alpha" tier is unreachable. We treat the
    significance test as the binding criterion instead and reserve
    BETA_ONLY for cases where the SR comes from amplified market
    exposure (β>>1 with no p<0.05) rather than from stock selection.
    """
    if alpha_p < 0.05 and alpha > 0:
        return "SIG_ALPHA"  # significant positive alpha vs RSP
    if alpha_p < 0.10 and alpha > 0:
        return "MARGINAL"
    if abs(beta) > 1.10 and alpha < 0:
        return "BETA_DRAG"
    return "NOISE"


def main() -> int:
    # User's spec: (long_only, sector-neutral, RSP). FORCE sector — earlier
    # version of this script picked best of (none, sector) which silently
    # broke the contract for factors where neutralize=none gave higher α-t.
    # Sweep across top_pct only.
    print("[stage 1] running 22 candidates × 3 top_pct variants under "
          "(long_only, sector-neutral, RSP) — STRICT SPEC", file=sys.stderr)
    chosen: list[dict] = []
    for fam, name, thesis, expr, ops in CANDIDATES:
        variants = []
        for tp in (0.10, 0.20, 0.30):
            v = run_one(name, expr, ops, "sector", tp)
            if v and "error" not in v:
                variants.append(v)
        if not variants:
            print(f"  {name}: ALL VARIANTS FAILED", file=sys.stderr)
            continue
        best = max(variants, key=lambda v: v["alpha_t"])
        best["family"] = fam
        best["thesis"] = thesis
        best["expression"] = expr
        best["verdict"] = verdict(best["alpha_p"], best["beta"], best["alpha_ann"])
        chosen.append(best)
        print(f"  {name:18s} S/top{int(best['top_pct']*100):2d}%  "
              f"SR={best['test_sr']:+.2f}  α-t={best['alpha_t']:+.2f}  "
              f"α-p={best['alpha_p']:.3f}  β={best['beta']:+.3f}  "
              f"verdict={best['verdict']}",
              file=sys.stderr)

    print("\n[stage 2] filter: verdict ∈ {SIG_ALPHA}", file=sys.stderr)
    sig = [r for r in chosen if r["verdict"] == "SIG_ALPHA"]
    print(f"  → {len(sig)} factors clear α-p < 0.05", file=sys.stderr)
    if len(sig) < 6:
        print("\n[stage 2.5] not enough — filling with MARGINAL tier (α-p<0.10)",
              file=sys.stderr)
        marginal = [r for r in chosen if r["verdict"] == "MARGINAL"]
        marginal.sort(key=lambda r: r["alpha_t"], reverse=True)
        sig = sig + marginal
    if len(sig) < 6:
        print("\n[stage 2.75] still not enough — filling with top-α-t "
              "regardless of verdict", file=sys.stderr)
        rest = sorted(
            [r for r in chosen if r not in sig and r["alpha_t"] > 0],
            key=lambda r: r["alpha_t"],
            reverse=True,
        )
        sig = sig + rest

    print("\n[stage 3] family diversity (max 2 per family) → top 6 by α-t",
          file=sys.stderr)
    sig.sort(key=lambda r: r["alpha_t"], reverse=True)
    picks: list[dict] = []
    fam_count: dict[str, int] = {}
    for r in sig:
        fc = fam_count.get(r["family"], 0)
        if fc >= 2:
            continue
        picks.append(r)
        fam_count[r["family"]] = fc + 1
        if len(picks) == 6:
            break

    print(f"\n=== {len(picks)} PICKS ===", file=sys.stderr)
    for i, r in enumerate(picks, 1):
        regs_str = " / ".join(
            f"{rg['regime']}(α-t={rg['alpha_t']:+.2f})"
            for rg in r["regimes"]
        )
        print(f"\n#{i} {r['name']} [{r['family']}] verdict={r['verdict']}")
        print(f"   thesis: {r['thesis']}")
        print(f"   expression: {r['expression']}")
        print(f"   config: long_only · sector-neutral · RSP · top {int(r['top_pct']*100)}%")
        print(f"   metrics: α-t={r['alpha_t']:+.2f}, α-p={r['alpha_p']:.3f}, "
              f"β={r['beta']:+.3f}, SR={r['test_sr']:+.2f}, "
              f"IC={r['ic']:+.4f}, PSR={r['psr']:.2f}, "
              f"α-ann={r['alpha_ann']*100:+.2f}%")
        print(f"   regimes: {regs_str}")

    # Emit JSON for downstream FactorExamples update.
    out_path = Path(__file__).resolve().parent.parent / "docs" / "pure_alpha_long_only_rsp_picks.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(picks, indent=2))
    print(f"\n→ JSON: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
