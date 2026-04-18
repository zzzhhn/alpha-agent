"""evaluate layer: IC, ICIR, Sharpe, MaxDD, turnover, alpha decay.

Pure pandas/numpy. Called by both scan/ (fast path) and backtest/ (slow path).
LLM MUST NEVER compute these numbers. See REFACTOR_PLAN.md section 9 red-line #1.
"""
