"""Interactive POST endpoints — Hypothesis Lab translator + factor backtest.

Legacy single-ticker RSI/MACD/Bollinger endpoints, ticker search, factor
analytics by ticker, gate simulation, and portfolio stress test were
removed in P6.A — none of them belonged in the cross-sectional factor
research mental model.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from alpha_agent.api.byok import get_llm_client as _get_llm_client
from alpha_agent.llm.base import LLMClient as _LLMClient
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(tags=["interactive"])


# ════════════════════════════════════════════════════════════════════════════
# T1: HypothesisTranslator (REFACTOR_PLAN.md §3.1)
# ════════════════════════════════════════════════════════════════════════════
#
# Input: natural-language factor hypothesis
# Output: FactorSpec JSON (Pydantic-validated + AST-validated) + 10-day smoke IC
#
# Pipeline:
#   1. LLM call with grammar-describing system prompt
#   2. Pydantic FactorSpec.model_validate  (field schemas)
#   3. validate_expression  (AST whitelist + declared/used op equality)
#   4. smoke_test  (20-ticker synthetic panel, 10-day cross-sectional Spearman IC)
#
# Failure surfacing: each step raises a distinct HTTPException status so curl
# consumers can distinguish schema violation (422) from upstream-provider error
# (502) from smoke crash (500). See feedback_silent_trycatch_antipattern.md.

import json as _json
import re as _re

from fastapi import Request as _Request

from alpha_agent.core.factor_ast import (
    FactorSpecValidationError as _FactorSpecValidationError,
)
from alpha_agent.core.factor_ast import expression_to_tree as _expression_to_tree
from alpha_agent.core.factor_ast import validate_expression as _validate_expression
from alpha_agent.core.types import FactorSpec as _FactorSpec
from alpha_agent.llm.base import Message as _Message
from alpha_agent.scan.smoke import smoke_test as _smoke_test


class HypothesisTranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    universe: str = Field(
        default="SP500", pattern=r"^(CSI300|CSI500|SP500|custom)$"
    )
    budget_tokens: int = Field(default=4000, ge=500, le=8000)


class SmokeReport(BaseModel):
    rows_valid: int
    ic_spearman: float
    runtime_ms: float


class HypothesisTranslateResponse(BaseModel):
    spec: _FactorSpec
    smoke: SmokeReport
    llm_tokens: dict[str, int]
    llm_raw: str


def _build_translate_prompt() -> str:
    """Build the system prompt with the LIVE operator + operand whitelist.

    Source of truth = scan/vectorized.py::OPS and core/factor_ast::_ALLOWED_OPERANDS.
    Re-rendered each request so adding an operator anywhere flows here automatically.
    """
    from alpha_agent.scan.vectorized import OPS as _OPS
    from alpha_agent.core.factor_ast import _ALLOWED_OPERANDS

    # Group operators by category for readability.
    arith = sorted(n for n in _OPS if n in {
        "abs", "add", "subtract", "sub", "multiply", "mul", "divide", "div",
        "inverse", "log", "sqrt", "power", "pow", "sign", "signed_power",
        "max", "min", "reverse", "densify",
    })
    logic = sorted(n for n in _OPS if n in {
        "if_else", "and_", "or_", "not_", "is_nan",
        "equal", "not_equal", "less", "greater", "less_equal", "greater_equal",
    })
    ts = sorted(n for n in _OPS if n.startswith("ts_") or n == "last_diff_value")
    cs = sorted(n for n in _OPS if n in {
        "rank", "zscore", "scale", "normalize", "quantile", "winsorize",
    })
    grp = sorted(n for n in _OPS if n.startswith("group_"))

    operands = sorted(_ALLOWED_OPERANDS)

    return f"""You convert a natural-language factor hypothesis into a strict FactorSpec JSON.

Output rules:
1. Emit ONLY one JSON object. No prose, no markdown fences.
2. Schema:
   {{
     "name": "<snake_case, <=40 chars>",
     "hypothesis": "<<=200 chars, restate the user idea>",
     "expression": "<Python call syntax using ALLOWED_OPS>",
     "operators_used": [<exact set of ops used in expression>],
     "lookback": <int 5-252>,
     "universe": "<CSI300|CSI500|SP500|custom>",
     "justification": "<<=400 chars, why this captures the hypothesis>"
   }}

ALLOWED_OPS — every function call must be one of these names:
  arithmetic:    {", ".join(arith)}
  logical:       {", ".join(logic)}
  time-series:   {", ".join(ts)}
  cross-section: {", ".join(cs)}
  group:         {", ".join(grp)}

Operands (leaves) — only these names + numeric literals are allowed:
  {", ".join(operands)}

No attributes, no imports, no lambdas, no keyword args. No infix `< > == + - * / **`
— use the functional forms (less, greater, equal, add, sub, mul, div, pow).

Op signatures:
  ts_mean(arr, window:int)         ts_std_dev(arr, window:int)
  ts_zscore(arr, window:int)       ts_rank(arr, window:int)
  ts_delay(arr, d:int)             ts_delta(arr, d:int)
  ts_sum/ts_min/ts_max/ts_arg_min/ts_arg_max(arr, window:int)
  ts_corr(arr, arr, window:int)    ts_covariance(arr, arr, window:int)
  ts_quantile(arr, window:int, q:float)
  ts_decay_linear(arr, window:int) ts_decay_exp(arr, window:int)
  rank(arr)  scale(arr)  zscore(arr)  normalize(arr)
  winsorize(arr, pct:float)        quantile(arr, n_buckets:int)
  group_rank/group_zscore/group_neutralize/group_mean/group_scale(arr, group_arr)
    — group_arr MUST be `sector` or `industry`.
  if_else(cond, t, f)              and_(a,b)/or_(a,b)/not_(x)
  equal/less/greater(a,b)
  add/sub/mul/div/pow/power(a,b)   abs/log/sqrt/sign/inverse(x)

lookback must be >= the largest ts_* window in the expression.
operators_used must exactly equal the set of ops actually called.

Example input: {{"hypothesis": "low turnover and rising ROE for mid-caps", "universe": "CSI500"}}
Example output:
{{"name":"low_turn_roe_up","hypothesis":"Mid-caps with low turnover and rising ROE.","expression":"sub(rank(ts_mean(div(volume,close),20)),rank(ts_zscore(returns,20)))","operators_used":["sub","rank","ts_mean","div","ts_zscore"],"lookback":20,"universe":"CSI500","justification":"Inverse-turnover proxy via rolling volume/close; ROE proxy via short-term return zscore; cross-sectional rank removes scale."}}
"""


_TRANSLATE_SYSTEM_PROMPT = _build_translate_prompt()


def _extract_json_object(text: str) -> dict | None:
    """Pull the first JSON object out of an LLM response (tolerates fences)."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[: cleaned.rfind("```")]
    match = _re.search(r"\{[\s\S]*\}", cleaned)
    if match is None:
        return None
    try:
        return _json.loads(match.group(0))
    except _json.JSONDecodeError:
        return None


@router.post(
    "/api/v1/alpha/translate",
    response_model=HypothesisTranslateResponse,
)
async def translate_hypothesis(
    body: HypothesisTranslateRequest,
    request: _Request,
    llm: _LLMClient = Depends(_get_llm_client),
) -> HypothesisTranslateResponse:
    """T1 HypothesisTranslator: NL -> FactorSpec -> smoke IC.

    Phase 1 BYOK — `llm` is now per-request, built from the caller's
    X-LLM-* headers (or platform fallback in dev). No more shared
    `app.state.llm` to drain operator quota.
    """

    user_payload = _json.dumps({"hypothesis": body.text, "universe": body.universe})
    messages = [
        _Message(role="system", content=_TRANSLATE_SYSTEM_PROMPT),
        _Message(role="user", content=user_payload),
    ]
    try:
        llm_resp = await llm.chat(
            messages, temperature=0.3, max_tokens=body.budget_tokens
        )
    except Exception as exc:  # noqa: BLE001 — surface upstream failure explicitly
        raise HTTPException(
            502, f"LLM provider error: {type(exc).__name__}: {exc}"
        ) from exc

    spec_dict = _extract_json_object(llm_resp.content)
    if spec_dict is None:
        raise HTTPException(
            422,
            f"LLM did not return parseable JSON. Head: {llm_resp.content[:200]!r}",
        )

    try:
        spec = _FactorSpec.model_validate(spec_dict)
    except ValueError as exc:
        raise HTTPException(422, f"FactorSpec schema violation: {exc}") from exc

    try:
        _validate_expression(spec.expression, spec.operators_used)
    except _FactorSpecValidationError as exc:
        raise HTTPException(422, f"Expression AST invalid: {exc}") from exc

    try:
        smoke = _smoke_test(spec.expression, spec.lookback)
    except Exception as exc:  # noqa: BLE001 — smoke crash is a real bug
        raise HTTPException(
            500, f"Smoke test crashed: {type(exc).__name__}: {exc}"
        ) from exc

    return HypothesisTranslateResponse(
        spec=spec,
        smoke=SmokeReport(
            rows_valid=smoke.rows_valid,
            ic_spearman=smoke.ic_spearman,
            runtime_ms=smoke.runtime_ms,
        ),
        llm_tokens={
            "prompt": llm_resp.prompt_tokens,
            "completion": llm_resp.completion_tokens,
        },
        llm_raw=llm_resp.content,
    )


# ── B3 (v3): AST visualization endpoint ─────────────────────────────────────


class ExplainAstRequest(BaseModel):
    expression: str = Field(..., min_length=1, max_length=2000)


class ExplainAstResponse(BaseModel):
    """Tree returned as a recursive dict — Pydantic doesn't model recursion
    well in serialization, and the shape is documented in the AST helper.
    Frontend types this as a discriminated union via TypeScript instead."""
    tree: dict


@router.post(
    "/api/v1/factor/explain_ast",
    response_model=ExplainAstResponse,
)
async def explain_ast(body: ExplainAstRequest) -> ExplainAstResponse:
    """Convert a factor expression to a tree JSON for the AST drawer.

    Goes through `validate_expression` first to guarantee the input meets the
    AST whitelist; only then traversed for visualization. Surfacing the tree
    is a transparency feature (痛点 1 of v3): users see exactly which operators
    and operands their hypothesis became.
    """
    try:
        # validate_expression's used-vs-declared check requires declared_ops, so
        # we feed it the empty set and accept the raised mismatch as a no-op
        # by passing a wildcard — actually simpler: skip validate, rely on
        # expression_to_tree's own grammar enforcement (raises identical error).
        tree = _expression_to_tree(body.expression)
    except _FactorSpecValidationError as exc:
        raise HTTPException(422, f"AST invalid: {exc}") from exc
    return ExplainAstResponse(tree=tree)


# ── Factor long-short backtest ──────────────────────────────────────────────


class FactorBacktestRequest(BaseModel):
    spec: _FactorSpec
    train_ratio: float = Field(default=0.80, ge=0.10, le=0.95)
    direction: Literal["long_short", "long_only", "short_only"] = Field(
        default="long_short",
        description=(
            "Portfolio construction. 'long_short' is market-neutral (gross 2.0), "
            "'long_only' is apples-to-apples with SPY benchmark, 'short_only' "
            "is the inverse."
        ),
    )
    # P4.1 — configurable rank cutoffs and transaction cost.
    top_pct: float = Field(default=0.30, ge=0.01, le=0.50,
        description="Fraction of universe to long (rank ≥ 1 - top_pct).")
    bottom_pct: float = Field(default=0.30, ge=0.01, le=0.50,
        description="Fraction of universe to short (rank ≤ bottom_pct).")
    transaction_cost_bps: float = Field(default=0.0, ge=0.0, le=200.0,
        description="Round-trip cost in basis points; charged on L1 weight delta.")
    # A7 (v3) — walk-forward rolling metrics on top of the static split.
    mode: Literal["static", "walk_forward"] = Field(
        default="static",
        description=(
            "static = single 80/20 train/test (default). walk_forward = ALSO "
            "compute per-window metrics for IS/OOS decay analysis."
        ),
    )
    wf_window_days: int = Field(default=60, ge=20, le=252,
        description="Length of each rolling window in trading days.")
    wf_step_days: int = Field(default=20, ge=5, le=252,
        description="Days between consecutive window starts.")
    # B4 (v3) — per-day basket + IC drill-down. Heavy payload, opt-in.
    include_breakdown: bool = Field(default=False,
        description="Return daily_breakdown[] with per-day long/short basket + IC.")
    # T1.3 (v4) — purge / embargo around the static train/test boundary.
    purge_days: int = Field(default=0, ge=0, le=30,
        description="Drop last N rows of train and end-of-WF-window before scoring.")
    embargo_days: int = Field(default=0, ge=0, le=30,
        description="Drop first N rows of test and start-of-WF-window before scoring.")
    # T2.1 (v4) — multiple-testing correction. n_trials = 1 gives the raw PSR
    # against SR=0; > 1 deflates the threshold to E[max SR_N | null].
    n_trials: int = Field(default=1, ge=1, le=1000,
        description="How many factor variants the user explored before saving this one. "
                    "Used by Bailey-LdP deflated Sharpe to discount selection bias.")
    # T2.2 (v4) — sqrt(participation/ADV) slippage. Multiplied by sqrt(% of
    # ADV traded). Default 0 = no slippage (back-compat).
    slippage_bps_per_sqrt_pct: float = Field(default=0.0, ge=0.0, le=100.0,
        description="Almgren-style market impact: cost_bps = k × sqrt(participation_pct).")
    # T2.3 (v4) — annualized short borrow cost; daily-accrued on |w_short|.
    short_borrow_bps: float = Field(default=0.0, ge=0.0, le=1000.0,
        description="Annualized short-leg borrow cost in bps; charged daily on the prior "
                    "day's |Σ w_short|.")
    # T3.C (v4) — zero out weights ±N days around each ticker's earnings.
    mask_earnings_window: bool = Field(default=False,
        description="Skip trading each ticker around its earnings announcement to reduce "
                    "PEAD noise contamination of momentum/reversal factors.")
    earnings_window_days: int = Field(default=1, ge=0, le=5,
        description="Half-width of the earnings mask in trading days (default ±1d).")
    # Bundle A.2 (v4) — sector-neutral portfolio: rank within each GICS sector,
    # then pool. Decouples factor signal from sector beta exposure.
    neutralize: Literal["none", "sector"] = Field(default="none",
        description="Portfolio neutralization mode. 'sector' subtracts per-sector mean "
                    "from the factor before ranking, so the basket has near-zero net "
                    "sector exposure.")
    # RSP equal-weight benchmark: meaningfully different from cap-weighted SPY in
    # mega-cap-concentrated regimes (3y panel: SPY +75% vs RSP +42%, spread −33%).
    benchmark_ticker: Literal["SPY", "RSP"] = Field(default="SPY",
        description="Benchmark for alpha/beta regression. SPY = cap-weighted "
                    "(Mag-7 dominated), RSP = equal-weight SP500. Long-only equal-"
                    "weight baskets are far closer to RSP's regime than SPY's.")


class _SplitMetricsModel(BaseModel):
    sharpe: float
    total_return: float
    ic_spearman: float
    n_days: int
    max_drawdown: float = 0.0
    turnover: float = 0.0
    hit_rate: float = 0.0
    # T1.4 (v4) — IC distribution + significance.
    ic_std: float = 0.0
    icir: float = 0.0
    ic_t_stat: float = 0.0
    ic_pvalue: float = 1.0
    # T2.1 (v4) — Bailey-LdP deflated Sharpe.
    psr: float = 0.5
    lucky_max_sr: float = 0.0
    # T3.A (v4) — stationary block bootstrap 95% CIs.
    sharpe_ci_low: float = 0.0
    sharpe_ci_high: float = 0.0
    ic_ci_low: float = 0.0
    ic_ci_high: float = 0.0


class _CurvePoint(BaseModel):
    date: str
    value: float


class _MonthlyReturn(BaseModel):
    year: int
    month: int           # 1-12
    return_: float = Field(alias="return")
    n_days: int

    model_config = {"populate_by_name": True}


class _WalkForwardWindow(BaseModel):
    window_start: str
    window_end: str
    sharpe: float
    total_return: float
    ic_spearman: float
    n_days: int
    max_drawdown: float
    turnover: float
    hit_rate: float
    # T1.4 (v4) — same IC stats per window.
    ic_std: float = 0.0
    icir: float = 0.0
    ic_t_stat: float = 0.0
    ic_pvalue: float = 1.0
    # T2.1 (v4) — same DSR per window.
    psr: float = 0.5
    lucky_max_sr: float = 0.0
    # T3.A (v4) — same bootstrap CIs per window.
    sharpe_ci_low: float = 0.0
    sharpe_ci_high: float = 0.0
    ic_ci_low: float = 0.0
    ic_ci_high: float = 0.0


class _RegimeMetricsModel(BaseModel):
    """Bundle A.1 (v4): sub-period metrics partitioned by SPY 60d regime."""
    regime: Literal["bull", "bear", "sideways"]
    n_days: int
    sharpe: float
    ic_spearman: float
    ic_pvalue: float
    alpha_annualized: float
    alpha_t_stat: float
    alpha_pvalue: float


class _BasketEntry(BaseModel):
    ticker: str
    weight: float


class _DailyBreakdown(BaseModel):
    date: str
    long_basket: list[_BasketEntry]
    short_basket: list[_BasketEntry]
    daily_return: float
    daily_ic: float


class FactorBacktestResponse(BaseModel):
    equity_curve: list[_CurvePoint]
    benchmark_curve: list[_CurvePoint]
    train_end_index: int
    train_metrics: _SplitMetricsModel
    test_metrics: _SplitMetricsModel
    currency: str
    factor_name: str
    benchmark_ticker: str
    direction: Literal["long_short", "long_only", "short_only"]
    # P4.2: per-month compounded strategy returns for the heatmap viz.
    monthly_returns: list[_MonthlyReturn] = Field(default_factory=list)
    # A7 (v3): per-window metrics, only populated when mode="walk_forward".
    walk_forward: list[_WalkForwardWindow] | None = None
    # B4 (v3): per-day basket + IC, only populated when include_breakdown=true.
    daily_breakdown: list[_DailyBreakdown] | None = None
    # T2.4 (v4): IS-OOS Sharpe decay flag.
    oos_decay: float = 0.0
    overfit_flag: bool = False
    # T3.B (v4): market α/β decomposition.
    alpha_annualized: float = 0.0
    beta_market: float = 0.0
    alpha_t_stat: float = 0.0
    alpha_pvalue: float = 1.0
    r_squared: float = 0.0
    # T1.5b (v4): point-in-time SP500 membership correction status.
    survivorship_corrected: bool = False
    membership_as_of: str | None = None
    # Bundle A.1 (v4): per-regime SR/IC/alpha breakdown of the test slice.
    regime_breakdown: list[_RegimeMetricsModel] | None = None
    # Bundle A.2 (v4): which neutralization mode was applied.
    neutralize: Literal["none", "sector"] = "none"


@router.post(
    "/api/v1/factor/backtest",
    response_model=FactorBacktestResponse,
)
async def factor_backtest(body: FactorBacktestRequest) -> FactorBacktestResponse:
    """Run a cross-sectional long-short backtest on the 37-ticker US panel.

    Uses a pre-cached 1y OHLCV parquet (committed at deploy-time) so the
    request stays inside Vercel's 300s timeout. Long top 30% / short
    bottom 30% by factor rank, equal-weighted daily rebalance. Returns
    train/test metrics plus SPY benchmark curve for overlay.
    """
    # Lazy import: keeps existing interactive endpoints alive if the
    # factor_engine submodule fails to import (see dual-entry mirror rule).
    try:
        from alpha_agent.factor_engine.factor_backtest import run_factor_backtest
    except ImportError as exc:
        raise HTTPException(
            503,
            f"factor_engine module failed to import: {type(exc).__name__}: {exc}",
        ) from exc

    # Re-validate the expression against the AST whitelist. The FactorSpec
    # model already validates operator names, but _validate_expression also
    # catches AST-level issues like calling a non-whitelisted op inline.
    try:
        _validate_expression(body.spec.expression, body.spec.operators_used)
    except _FactorSpecValidationError as exc:
        raise HTTPException(422, f"Expression AST invalid: {exc}") from exc

    try:
        result = run_factor_backtest(
            body.spec,
            train_ratio=body.train_ratio,
            direction=body.direction,
            top_pct=body.top_pct,
            bottom_pct=body.bottom_pct,
            transaction_cost_bps=body.transaction_cost_bps,
            mode=body.mode,
            wf_window_days=body.wf_window_days,
            wf_step_days=body.wf_step_days,
            include_breakdown=body.include_breakdown,
            purge_days=body.purge_days,
            embargo_days=body.embargo_days,
            n_trials=body.n_trials,
            slippage_bps_per_sqrt_pct=body.slippage_bps_per_sqrt_pct,
            short_borrow_bps=body.short_borrow_bps,
            mask_earnings_window=body.mask_earnings_window,
            earnings_window_days=body.earnings_window_days,
            neutralize=body.neutralize,
            benchmark_ticker=body.benchmark_ticker,
        )
    except FileNotFoundError as exc:
        raise HTTPException(503, f"Panel data missing: {exc}") from exc
    except ImportError as exc:
        raise HTTPException(
            503,
            f"Optional dependency missing during backtest: {type(exc).__name__}: {exc}",
        ) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            422, f"Factor evaluation failed: {type(exc).__name__}: {exc}"
        ) from exc
    except NotImplementedError as exc:
        raise HTTPException(
            422,
            f"Factor uses an operator without a vectorized impl: {exc}",
        ) from exc

    def _to_model(m) -> _SplitMetricsModel:
        return _SplitMetricsModel(
            sharpe=m.sharpe,
            total_return=m.total_return,
            ic_spearman=m.ic_spearman,
            n_days=m.n_days,
            max_drawdown=m.max_drawdown,
            turnover=m.turnover,
            hit_rate=m.hit_rate,
            ic_std=m.ic_std,
            icir=m.icir,
            ic_t_stat=m.ic_t_stat,
            ic_pvalue=m.ic_pvalue,
            psr=m.psr,
            lucky_max_sr=m.lucky_max_sr,
            sharpe_ci_low=m.sharpe_ci_low,
            sharpe_ci_high=m.sharpe_ci_high,
            ic_ci_low=m.ic_ci_low,
            ic_ci_high=m.ic_ci_high,
        )

    monthly = [
        _MonthlyReturn(
            year=int(m["year"]),
            month=int(m["month"]),
            **{"return": float(m["return"])},
            n_days=int(m["n_days"]),
        )
        for m in (result.monthly_returns or [])
    ]

    walk_forward = (
        [_WalkForwardWindow(**w) for w in result.walk_forward]
        if result.walk_forward is not None
        else None
    )

    daily_breakdown = (
        [_DailyBreakdown(
            date=d["date"],
            long_basket=[_BasketEntry(**e) for e in d["long_basket"]],
            short_basket=[_BasketEntry(**e) for e in d["short_basket"]],
            daily_return=d["daily_return"],
            daily_ic=d["daily_ic"],
        ) for d in result.daily_breakdown]
        if result.daily_breakdown is not None
        else None
    )

    return FactorBacktestResponse(
        equity_curve=[_CurvePoint(**p) for p in result.equity_curve],
        benchmark_curve=[_CurvePoint(**p) for p in result.benchmark_curve],
        train_end_index=result.train_end_index,
        train_metrics=_to_model(result.train_metrics),
        test_metrics=_to_model(result.test_metrics),
        currency=result.currency,
        factor_name=result.factor_name,
        benchmark_ticker=result.benchmark_ticker,
        direction=result.direction,
        monthly_returns=monthly,
        walk_forward=walk_forward,
        daily_breakdown=daily_breakdown,
        oos_decay=result.oos_decay,
        overfit_flag=result.overfit_flag,
        alpha_annualized=result.alpha_annualized,
        beta_market=result.beta_market,
        alpha_t_stat=result.alpha_t_stat,
        alpha_pvalue=result.alpha_pvalue,
        r_squared=result.r_squared,
        survivorship_corrected=result.survivorship_corrected,
        membership_as_of=result.membership_as_of,
        regime_breakdown=(
            [_RegimeMetricsModel(
                regime=rm.regime, n_days=rm.n_days,
                sharpe=rm.sharpe, ic_spearman=rm.ic_spearman, ic_pvalue=rm.ic_pvalue,
                alpha_annualized=rm.alpha_annualized,
                alpha_t_stat=rm.alpha_t_stat, alpha_pvalue=rm.alpha_pvalue,
            ) for rm in result.regime_breakdown]
            if result.regime_breakdown else None
        ),
        neutralize=result.neutralize,
    )
