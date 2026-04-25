"""Augment the raw WorldQuant operator/field catalog with implementation flags.

Reads operators_raw.json + fields_raw.json (parsed from Lark docx).
Writes operators_augmented.json + fields_augmented.json with two extra fields
per item:

    "tier":         "T1" | "T2" | "T3" — when this item becomes available
    "implemented":  bool — whether the evaluator currently supports it

Source of truth for what's implemented:
  * Operators: alpha_agent.scan.vectorized.OPS dict
  * Operands: alpha_agent.core.factor_ast._ALLOWED_OPERANDS

Run from this directory:
    python3 augment_catalog.py

Re-run whenever the OPS dict or panel schema changes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent  # repo root
sys.path.insert(0, str(ROOT))

# --- T1 implementation list (must match scan/vectorized.py::OPS after refactor)
# Comparison aliases (less, greater, etc.) replace the infix forms (<, >, ==).
T1_OPERATORS: set[str] = {
    # arithmetic (15)
    "abs", "add", "subtract", "multiply", "divide", "inverse", "log", "sqrt",
    "power", "sign", "signed_power", "max", "min", "reverse", "densify",
    # logical (8 functional + 6 comparison aliases = 14)
    "if_else", "and_", "or_", "not_", "is_nan",
    "equal", "not_equal", "less", "greater", "less_equal", "greater_equal",
    # time-series (21 — skip ts_regression as 3-output, ts_backfill needs care)
    "ts_delay", "ts_delta", "ts_mean", "ts_std_dev", "ts_sum", "ts_product",
    "ts_min", "ts_max", "ts_rank", "ts_zscore", "ts_arg_min", "ts_arg_max",
    "ts_corr", "ts_covariance", "ts_quantile", "ts_decay_linear",
    "ts_decay_exp", "ts_count_nans", "last_diff_value",
    # cross-section (6)
    "rank", "zscore", "scale", "normalize", "quantile", "winsorize",
}

# T2 needs sector / group field — implementable once new parquet has it.
T2_OPERATORS: set[str] = {
    "group_neutralize", "group_rank", "group_zscore", "group_mean",
    "group_scale", "group_backfill",
}

# T3 = catalog-only (semantics unclear or specialized). Includes vector ops
# (user-skipped), niche transformational ops, and infix comparisons (replaced
# by the functional aliases in T1).
T3_OPERATORS: set[str] = {
    "vec_avg", "vec_sum",          # user said skip
    "bucket", "trade_when", "hump",  # niche transformational
    "==", "!=", "<", ">", "<=", ">=",  # infix — use functional aliases instead
    "ts_regression", "ts_backfill",  # special return types
}


# --- T1/T2 operand list (data fields available now or in T2 panel rebuild)
# T1 = OHLCV + derived (in current parquet)
T1_OPERANDS: set[str] = {
    "open", "high", "low", "close", "volume", "vwap", "returns",
}

# T2 = price/volume derived + 8 high-frequency fundamentals (rebuilt parquet)
T2_OPERANDS: set[str] = {
    # price/volume metadata
    "cap", "adv20", "sector", "industry", "subindustry",
    # 8 fundamentals (high-frequency, financial-datasets free tier)
    "revenue", "net_income_adjusted", "ebitda", "eps",
    "equity", "assets", "free_cash_flow", "gross_profit",
}

# T3 = anything in WorldQuant catalog not in T1+T2 (premium / unavailable data)
# These are catalog-only — auto-derived from raw JSON minus T1+T2.


def main() -> None:
    raw_ops = json.loads((HERE / "operators_raw.json").read_text())
    raw_fields = json.loads((HERE / "fields_raw.json").read_text())

    # --- operators
    ops_aug: list[dict] = []
    for cat, items in raw_ops.items():
        for it in items:
            name = it["name"]
            tier = (
                "T1" if name in T1_OPERATORS else
                "T2" if name in T2_OPERATORS else
                "T3"
            )
            ops_aug.append({
                **it,
                "tier": tier,
                "implemented": tier == "T1",  # T2 lit up after T2 ship
            })

    # --- fields
    fields_aug: list[dict] = []
    for cat, items in raw_fields.items():
        for it in items:
            name = it["name"]
            tier = (
                "T1" if name in T1_OPERANDS else
                "T2" if name in T2_OPERANDS else
                "T3"
            )
            fields_aug.append({
                **it,
                "tier": tier,
                "implemented": tier == "T1",
            })

    (HERE / "operators_augmented.json").write_text(
        json.dumps(ops_aug, ensure_ascii=False, indent=2)
    )
    (HERE / "fields_augmented.json").write_text(
        json.dumps(fields_aug, ensure_ascii=False, indent=2)
    )

    # --- summary
    by_tier_op = {"T1": 0, "T2": 0, "T3": 0}
    for op in ops_aug:
        by_tier_op[op["tier"]] += 1
    by_tier_field = {"T1": 0, "T2": 0, "T3": 0}
    for f in fields_aug:
        by_tier_field[f["tier"]] += 1

    print(f"operators: T1={by_tier_op['T1']} T2={by_tier_op['T2']} T3={by_tier_op['T3']} | total {len(ops_aug)}")
    print(f"fields:    T1={by_tier_field['T1']} T2={by_tier_field['T2']} T3={by_tier_field['T3']} | total {len(fields_aug)}")


if __name__ == "__main__":
    main()
