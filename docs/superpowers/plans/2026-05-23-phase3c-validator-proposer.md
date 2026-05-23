# Phase 3c Validator + LLM Proposer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** End-to-end propose loop: admin clicks Propose -> the diagnostic engine picks the current expression's weakest fold + lowest-IC signal -> a single BYOK LLM call (admin's key) returns N candidates each containing `{expression, new_operators[], rationale}` -> every new operator passes the 3b canned tests in a fresh sandbox dispatch -> survivors run purged walk-forward OOS validation with DSR-lite deflation against the current-expression baseline -> only proposals that beat baseline AND survive deflation get written to `factor_proposals.pending`. Nothing auto-applies (that is 3d's approve flow).

**Architecture:** Five new library modules + one new HTTP router. The diagnostic engine is a pure read pass over `signal_ic_history` plus a lightweight purged-WF on the live expression (no LLM). The LLM proposer consumes a `Diagnostic` snapshot, calls the user's BYOK LLM client through the existing alpha-agent BYOK plumbing, parses structured JSON with one retry, server-side enforces the `lf_` operator naming rule. The validator extends `ExprEvaluator` with an optional `extra_ops` dispatch table so the kernel routes new operator names through the 3b `SandboxRunner`. `evaluate_factor_candidate` reuses Phase 2a's `purged_fold_indices` + `deflated_sharpe_lite`. The `POST /api/factor-lab/propose` orchestrator stitches diagnostic + LLM + canned-tests + validator + DB writes; `GET /api/factor-lab/diagnostic` exposes the snapshot for the 3d UI.

**Tech Stack:** Python 3.12, asyncpg, FastAPI, numpy. Reuses Phase 2a (`alpha_agent/evolution/validation.py`), Phase 3a (`factor_proposals` table + `BUILTIN_OPS` + `refresh_allowed_ops`), Phase 3b (`SandboxRunner`, `run_canned_tests`), and the existing alpha-agent BYOK plumbing.

**UX principles applied to 3c:**
1. **Intent alignment**: `POST /api/factor-lab/propose` returns `{evaluated:int, proposed:int, dormant:bool}` — the same shape as Phase 2a's methodology proposer, so admins read the verdict instantly.
2. **Cognitive load minimization**: each proposal's `evidence` jsonb has stable named fields (`sharpes`, `ic_oos`, `deflated_sharpe`, `baseline_sharpe`, `n_folds`, `n_trials`, `llm_rationale`, `operator_test_results`); the 3d UI maps fields one-to-one with widgets.
3. **Visibility of system status**: `GET /api/factor-lab/diagnostic` shows the propose-time input verbatim, so an admin sees "what would the LLM be asked about?" before paying for the LLM call.
4. **Forgiveness**: one bad candidate (LLM hallucinated an operator, sandbox timeout, fold count below MIN_FOLDS) never aborts the batch; each is graded independently. Bad LLM JSON triggers one structured retry then a 502 with the parse-failure detail.
5. **Affordance**: endpoint paths obvious (`/api/factor-lab/diagnostic` shows the snapshot; `/propose` triggers it); one endpoint, one verb; the `Diagnostic` dataclass field names mirror the prompt template sections so reading either teaches you the other.

---

## Dependencies + grounding (read first during Task 1)

- Phase 3a merged: `factor_proposals` schema (`status`, `expression`, `new_operators jsonb`, `evidence jsonb`, `diagnostic jsonb`, `decided_at`, `decided_by`); `extended_operators` schema; `factor.custom_expression` knob; `BUILTIN_OPS` / `get_allowed_ops` / `refresh_allowed_ops` in `core/factor_ast.py`.
- Phase 3b merged: `SandboxRunner`, `SandboxError`, `SandboxErrorKind`, `CannedTestResult`, `run_canned_tests(runner, op_code, op_name, signature)`. The `/api/healthz/sandbox` endpoint precedent (dual-entry pattern).
- Phase 2a merged: `alpha_agent/evolution/validation.py` exports `purged_fold_indices(n, n_folds, embargo)`, `deflated_sharpe_lite(best_sharpe, sharpes, n_trials)`, `MIN_FOLDS=3`. The forward horizon `_FWD_RET_DAYS=5` lives in `alpha_agent/backtest/ic_engine.py`; embargo must be `>= 5`.
- ExprEvaluator: `alpha_agent/factor_engine/evaluator.py:64` defines `class ExprEvaluator`. READ its constructor + the per-node dispatch (look for `_visit_call` or similar) to identify the precise insertion point for the optional `extra_ops` dict.
- BYOK plumbing: the implementer of T2 MUST grep first for the user-key dependency. Try `grep -rnE "X-LLM-API-Key|byok|get_llm_client|create_llm_client" alpha_agent/api/ | head -20`. Whatever pattern the existing endpoints use, mirror it (likely `from alpha_agent.api.byok import get_llm_client` as a FastAPI `Depends`).
- Admin auth: `from alpha_agent.auth.dependencies import require_user` (used in Phase 2b approve/reject). All 3c mutation endpoints use this guard.
- Anti-pattern guardrails (relearned in 3a + 3b): silent-exception forbidden — every `try/except` surfaces to `SandboxError` / `FactorCandidateResult=None` / `app.state.<>_error` / structured HTTP error. Dual-entry mandatory — any new HTTP route in `app.py` MUST also be in `api/index.py` with the same path under `/api/`.

---

## File Structure

- `alpha_agent/evolution/diagnostics.py` (new): `Diagnostic` dataclass + `compute_diagnostic(pool) -> Diagnostic`.
- `alpha_agent/evolution/llm_factor_proposer.py` (new): `RawProposal` dataclass + `async propose_factors(llm_client, diagnostic, n) -> list[RawProposal]`.
- `alpha_agent/factor_engine/evaluator.py` (modify): add optional `extra_ops` kwarg to ExprEvaluator's entry-point so new operators dispatch through a caller-provided callable.
- `alpha_agent/evolution/factor_validation.py` (new): `FactorCandidateResult` + `async evaluate_factor_candidate(pool, runner, expression, new_operators) -> FactorCandidateResult | None`.
- `alpha_agent/api/routes/factor_lab.py` (new router): `GET /diagnostic`, `POST /propose`. Both prefixed `/api/factor-lab`.
- `alpha_agent/api/app.py` (modify): include the new router via `_load(...)`.
- `api/index.py` (modify): `_load("factor_lab", "alpha_agent.api.routes.factor_lab")`. Dual-entry.
- Tests: `tests/evolution/test_diagnostics.py`, `tests/evolution/test_llm_factor_proposer.py`, `tests/factor_engine/test_evaluator_extra_ops.py`, `tests/evolution/test_factor_validation.py`, `tests/api/test_factor_lab.py`.

---

### Task 1: Diagnostic engine

**Files:**
- Create: `alpha_agent/evolution/diagnostics.py`
- Test: `tests/evolution/test_diagnostics.py`

The diagnostic engine is a pure read pass: it reads `signal_ic_history` to find the lowest-IC signal in the last 30 days and runs a lightweight purged-WF on the current effective expression (via Phase 2a's helpers) to identify the worst OOS fold. Output is a `Diagnostic` dataclass embedded into the LLM prompt template.

- [ ] **Step 1: Write the failing test**

```python
# tests/evolution/test_diagnostics.py
import asyncpg
import pytest

from alpha_agent.evolution.diagnostics import Diagnostic, compute_diagnostic
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


@pytest.mark.asyncio
async def test_diagnostic_returns_struct_with_current_expression(pool):
    """Even with zero IC history rows, the diagnostic always returns a
    Diagnostic carrying the current expression. Cognitive load UX: the
    LLM prompt has a stable shape regardless of data scarcity."""
    d = await compute_diagnostic(pool)
    assert isinstance(d, Diagnostic)
    assert isinstance(d.current_expression, str)
    assert len(d.current_expression) > 0  # always falls back to preset
    assert d.weak_signal is None or isinstance(d.weak_signal, str)
    assert isinstance(d.symptom_summary, str)


@pytest.mark.asyncio
async def test_diagnostic_picks_lowest_ic_signal_when_history_present(pool):
    """Seed two signals with different 30d-window IC; diagnostic picks the
    lower one as `weak_signal` and its IC as `weak_signal_ic`."""
    conn = await asyncpg.connect(applied_db := str(pool._dsn) if hasattr(pool, '_dsn') else None) if False else None
    # Use pool directly to seed:
    await pool.execute(
        "INSERT INTO signal_ic_history (signal_name, window_days, computed_at, ic) "
        "VALUES ('alpha', 30, now(), 0.04), ('beta', 30, now(), 0.005)"
    )
    d = await compute_diagnostic(pool)
    assert d.weak_signal == "beta"
    assert d.weak_signal_ic is not None
    assert d.weak_signal_ic < 0.04
```

(If the real `signal_ic_history` schema differs from `(signal_name, window_days, computed_at, ic)`, ADJUST the seed SQL to match — the implementer must grep the actual schema first via `grep -nE 'signal_ic_history' alpha_agent/storage/migrations/*.sql | head -3` and adapt.)

- [ ] **Step 2: Run, verify FAIL** (ImportError).

- [ ] **Step 3: Implement `diagnostics.py`**

```python
"""Phase 3c diagnostic engine: pure read pass that picks the current weakest
signal + worst OOS fold, used as input to the LLM prompt template. No LLM
calls here; this is the structured 'why are we proposing?' snapshot."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from alpha_agent.config_store import get_config
from alpha_agent.signals.factor import _resolve_default_expr


@dataclass(frozen=True)
class Diagnostic:
    current_expression: str
    weak_signal: str | None
    weak_signal_ic: float | None
    worst_fold_sharpe: float | None
    worst_fold_window: tuple[str, str] | None
    symptom_summary: str

    def to_jsonable(self) -> dict:
        d = asdict(self)
        # tuple -> list for JSON
        if d.get("worst_fold_window") is not None:
            d["worst_fold_window"] = list(d["worst_fold_window"])
        return d


async def compute_diagnostic(pool) -> Diagnostic:
    """Read signal_ic_history (lowest 30d IC) + optionally run a lightweight
    purged-WF on the current expression (left out for v1 — adds ~500ms; the
    LLM prompt can lean on weak_signal alone). v2 enhancement: fill
    worst_fold_sharpe + worst_fold_window."""
    current = _resolve_default_expr()
    weak_signal, weak_ic = None, None
    # READ the real signal_ic_history schema and adapt the query if needed.
    row = await pool.fetchrow(
        "SELECT signal_name, ic FROM signal_ic_history "
        "WHERE window_days = 30 "
        "ORDER BY computed_at DESC, ic ASC LIMIT 1"
    )
    if row is not None:
        weak_signal, weak_ic = row["signal_name"], float(row["ic"])
    parts = [f"Current expression: {current}."]
    if weak_signal is not None:
        parts.append(f"Weakest 30d signal: {weak_signal} (IC={weak_ic:.4f}).")
    else:
        parts.append("No recent IC history; running on the preset expression.")
    return Diagnostic(
        current_expression=current,
        weak_signal=weak_signal,
        weak_signal_ic=weak_ic,
        worst_fold_sharpe=None,
        worst_fold_window=None,
        symptom_summary=" ".join(parts),
    )
```

NOTE: `worst_fold_sharpe` / `worst_fold_window` deferred to a v2 (cheap to add later). v1 prompt relies on `weak_signal` + `current_expression`. Mark this honestly in the docstring; do NOT pretend the fold info is populated.

- [ ] **Step 4: Run, verify PASS.**

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/evolution/diagnostics.py tests/evolution/test_diagnostics.py
git commit -m "feat(evolution): diagnostic engine for LLM factor proposer (Phase 3c)"
```

---

### Task 2: LLM factor proposer (BYOK + prompt template + JSON parsing)

**Files:**
- Create: `alpha_agent/evolution/llm_factor_proposer.py`
- Test: `tests/evolution/test_llm_factor_proposer.py`

The proposer consumes a `Diagnostic` and an LLM client (BYOK-provided), constructs a structured prompt, calls the LLM once with a hard token + wall-clock cap, parses the JSON response (one retry on parse failure), and returns a list of `RawProposal`. Server-side enforces the `lf_` operator naming rule and rejects non-conforming entries.

- [ ] **Step 1: READ the existing BYOK plumbing first**

```bash
grep -rnE "X-LLM-API-Key|get_llm_client|create_llm_client|Depends.*llm" alpha_agent/api/ | head -25
```
Locate the existing BYOK dependency (likely `from alpha_agent.api.byok import get_llm_client` or similar). Note its return type (probably an `LLMClient` ABC with `async complete(messages)` or `async acompletion(messages)`). The proposer accepts an instance of this client, NOT a key string.

- [ ] **Step 2: Write the failing test**

```python
# tests/evolution/test_llm_factor_proposer.py
import json
from unittest.mock import AsyncMock

import pytest

from alpha_agent.evolution.diagnostics import Diagnostic
from alpha_agent.evolution.llm_factor_proposer import RawProposal, propose_factors


@pytest.fixture
def diagnostic():
    return Diagnostic(
        current_expression="rank(ts_mean(returns, 12))",
        weak_signal="news_24h", weak_signal_ic=0.003,
        worst_fold_sharpe=None, worst_fold_window=None,
        symptom_summary="News IC dropped below 0.01.",
    )


@pytest.fixture
def mock_llm():
    """Mock LLM client whose .complete returns a structured JSON string."""
    client = AsyncMock()
    client.complete.return_value = json.dumps({
        "proposals": [
            {
                "expression": "rank(ts_mean(returns, 8))",
                "new_operators": [],
                "rationale": "Shorter window for faster-moving regime."
            },
            {
                "expression": "rank(lf_decay_mean(returns, 12))",
                "new_operators": [{
                    "name": "lf_decay_mean",
                    "signature": "(x: ndarray, window: int) -> ndarray",
                    "python_impl": "import numpy as np\ndef lf_decay_mean(x, window):\n    w = np.exp(-np.arange(window) / window)\n    out = np.full_like(x, np.nan)\n    for i in range(window, len(x)):\n        out[i] = np.sum(x[i-window:i] * w[::-1]) / w.sum()\n    return out",
                    "doc": "Exponentially decayed mean over the last `window` samples."
                }],
                "rationale": "Decay emphasis on recent returns."
            }
        ]
    })
    return client


@pytest.mark.asyncio
async def test_proposer_returns_n_raw_proposals(mock_llm, diagnostic):
    out = await propose_factors(mock_llm, diagnostic, n=2)
    assert len(out) == 2
    assert all(isinstance(p, RawProposal) for p in out)
    assert out[0].expression == "rank(ts_mean(returns, 8))"
    assert out[1].new_operators[0]["name"] == "lf_decay_mean"


@pytest.mark.asyncio
async def test_proposer_rejects_invalid_operator_names(mock_llm, diagnostic):
    """Server-side enforces the lf_ prefix + char class. A non-conforming
    new_operator entry is dropped from the returned list (the proposal as
    a whole is kept only if at least its expression survives)."""
    mock_llm.complete.return_value = json.dumps({
        "proposals": [{
            "expression": "rank(returns)",
            "new_operators": [{
                "name": "BadName",   # uppercase, no lf_ prefix
                "signature": "(x) -> x", "python_impl": "def BadName(x): return x", "doc": ""
            }],
            "rationale": "test",
        }]
    })
    out = await propose_factors(mock_llm, diagnostic, n=1)
    assert len(out) == 1
    assert out[0].new_operators == []  # invalid op stripped; expression kept


@pytest.mark.asyncio
async def test_proposer_retries_once_on_json_parse_failure(mock_llm, diagnostic):
    """Forgiveness UX: bad JSON gets one structured retry, not an immediate raise."""
    mock_llm.complete.side_effect = [
        "this is not JSON at all",
        json.dumps({"proposals": [{"expression": "rank(returns)", "new_operators": [], "rationale": "ok"}]}),
    ]
    out = await propose_factors(mock_llm, diagnostic, n=1)
    assert len(out) == 1
    assert mock_llm.complete.call_count == 2


@pytest.mark.asyncio
async def test_proposer_raises_when_retry_also_fails(mock_llm, diagnostic):
    """After 2 failed parses, propose_factors raises with a structured error
    so the orchestrator can return 502 instead of pretending all is well."""
    mock_llm.complete.side_effect = ["still not JSON", "also not JSON"]
    with pytest.raises(ValueError, match="parse"):
        await propose_factors(mock_llm, diagnostic, n=1)
```

NOTE: if the real LLM client method is `acompletion` or returns a structured response (e.g. `(text, usage)` tuple) instead of a raw string, ADJUST the mock to match. The implementer's first job is to find the real signature.

- [ ] **Step 3: Run, verify FAIL** (ImportError).

- [ ] **Step 4: Implement `llm_factor_proposer.py`**

```python
"""Phase 3c LLM factor proposer. Consumes a Diagnostic + a BYOK LLM client
(the user's own credentials, never platform), returns a list of RawProposal.

Hard caps:
  N up to 8 per call (default 5; admin can pass less; rejects more).
  Output tokens up to 8000 (room for N=5 proposals with operator code).
  Wall-clock 60 s on the LLM call.

Server-side validation:
  - Top-level JSON must have "proposals": list.
  - Each proposal must have "expression" (non-empty str).
  - new_operators must be a list (default []); each entry must have name
    matching ^lf_[a-z_][a-z0-9_]{1,30}$, plus signature/python_impl/doc str.
  - Non-conforming new_operator entries are DROPPED (forgiveness UX; the
    proposal as a whole survives if its expression is valid).
  - One retry on JSON parse failure. Second failure raises ValueError."""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field

from alpha_agent.evolution.diagnostics import Diagnostic

_LF_NAME = re.compile(r"^lf_[a-z_][a-z0-9_]{1,30}$")
_HARD_N_CAP = 8
_OUTPUT_TOKEN_CAP = 8000
_WALL_CLOCK_S = 60


@dataclass(frozen=True)
class RawProposal:
    expression: str
    new_operators: list[dict] = field(default_factory=list)
    rationale: str = ""


def _build_prompt(d: Diagnostic, n: int) -> str:
    return (
        "You are an alpha-research factor inventor. Given the diagnostic below,"
        f" propose {n} candidate factor expressions, each optionally introducing"
        " 0-2 new operators (sandboxed at runtime; must be pure NumPy)."
        "\n\nDIAGNOSTIC:\n"
        f"  current_expression: {d.current_expression}\n"
        f"  weak_signal: {d.weak_signal} (IC={d.weak_signal_ic})\n"
        f"  symptom: {d.symptom_summary}\n"
        "\nCONSTRAINTS:"
        "\n- Output strict JSON: {\"proposals\":[{...}, ...]}."
        "\n- Each proposal: {expression, new_operators, rationale}."
        "\n- Operators may use the existing AST DSL (rank, ts_mean, ts_std, subtract, "
        "add, multiply, divide, ...) plus any new_operators you declare."
        "\n- New operator names must match ^lf_[a-z_][a-z0-9_]{1,30}$ (lf_ prefix)."
        "\n- New operator python_impl must be a function definition whose name "
        "matches the declared name, with numpy as its only import."
        "\n- No I/O, no network, no subprocess."
        "\n- Return JSON only, no prose."
    )


def _validate_new_ops(raw: list) -> list[dict]:
    """Drop entries that fail the name regex or are missing required fields."""
    ok = []
    if not isinstance(raw, list):
        return ok
    for op in raw:
        if not isinstance(op, dict):
            continue
        name = op.get("name", "")
        if not isinstance(name, str) or not _LF_NAME.match(name):
            continue
        if not isinstance(op.get("python_impl", ""), str):
            continue
        if not isinstance(op.get("signature", ""), str):
            continue
        ok.append({
            "name": name,
            "signature": op.get("signature", ""),
            "python_impl": op["python_impl"],
            "doc": op.get("doc", "") or "",
        })
    return ok


def _parse_response(text: str, n: int) -> list[RawProposal]:
    data = json.loads(text)
    raws = data.get("proposals", [])
    out: list[RawProposal] = []
    for p in raws[:n]:
        if not isinstance(p, dict):
            continue
        expr = p.get("expression", "")
        if not isinstance(expr, str) or not expr.strip():
            continue
        out.append(RawProposal(
            expression=expr.strip(),
            new_operators=_validate_new_ops(p.get("new_operators", [])),
            rationale=str(p.get("rationale", ""))[:1000],
        ))
    return out


async def propose_factors(llm_client, diagnostic: Diagnostic, n: int = 5) -> list[RawProposal]:
    n = min(max(int(n), 1), _HARD_N_CAP)
    prompt = _build_prompt(diagnostic, n)
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            text = await asyncio.wait_for(
                llm_client.complete(messages=[{"role": "user", "content": prompt}],
                                    max_tokens=_OUTPUT_TOKEN_CAP),
                timeout=_WALL_CLOCK_S,
            )
            return _parse_response(text, n)
        except (json.JSONDecodeError, ValueError) as e:
            last_err = e
            continue
    raise ValueError(f"could not parse LLM response after retry: {last_err}")
```

IMPORTANT: adapt `llm_client.complete(...)` call signature to match the REAL BYOK client interface. If the real method is `acompletion(messages=...)` and returns a `ChatResponse` object with `.content`, change the await to `text = (await llm_client.acompletion(...)).content`. Do NOT invent a signature; mirror the actual method that other endpoints (e.g. `/api/news/enrich/{ticker}` per the BYOK rule from memory) use.

- [ ] **Step 5: Run, verify PASS.**

- [ ] **Step 6: Commit**

```bash
git add alpha_agent/evolution/llm_factor_proposer.py tests/evolution/test_llm_factor_proposer.py
git commit -m "feat(evolution): LLM factor proposer with BYOK + JSON validation + lf_ enforcement (Phase 3c)"
```

---

### Task 3: ExprEvaluator `extra_ops` dispatch hook

**Files:**
- Modify: `alpha_agent/factor_engine/evaluator.py` (extend ExprEvaluator with an optional `extra_ops: dict[str, Callable]` kwarg)
- Test: `tests/factor_engine/test_evaluator_extra_ops.py`

The validator needs to evaluate an expression that uses both built-in operators AND new sandboxed operators. The cleanest mechanism: add an optional `extra_ops` dict kwarg to ExprEvaluator's entry point. When the AST dispatcher encounters an unknown call name, check `extra_ops` BEFORE raising `EvaluationError`. The callable in `extra_ops` takes the same args the built-in dispatcher would (ndarrays / scalars positional + keyword) and returns an ndarray.

- [ ] **Step 1: GREP the current dispatcher** to find the precise insertion point:
```bash
grep -nE "def __init__|def visit|_visit_call|ALLOWED_OPS|EvaluationError" alpha_agent/factor_engine/evaluator.py | head -20
```
The dispatcher likely has a per-call branch that resolves a function name to a built-in callable. Insert the `extra_ops` lookup BEFORE the built-in resolution (so a proposal-supplied `lf_*` op is found first) OR after (so built-ins win conflicts). The spec wants `lf_` prefix to NOT conflict with built-ins, so either order works; for clarity, check `extra_ops` AFTER built-ins fail (so built-in names are never shadowed accidentally).

- [ ] **Step 2: Write the failing test**

```python
# tests/factor_engine/test_evaluator_extra_ops.py
import numpy as np
import pandas as pd
import pytest

from alpha_agent.factor_engine.evaluator import ExprEvaluator


def test_evaluator_dispatches_to_extra_ops_when_name_not_builtin():
    """When the AST hits an unknown call name, extra_ops resolves it."""
    panel = pd.DataFrame({"close": [1.0, 2.0, 3.0, 4.0]})
    panel.index = pd.MultiIndex.from_product([["AAPL"], [0, 1, 2, 3]], names=["ticker", "date"])

    def lf_double(x):
        return x * 2

    ev = ExprEvaluator(panel=panel, extra_ops={"lf_double": lf_double})
    result = ev.evaluate("lf_double(close)")
    assert isinstance(result, pd.Series)
    assert result.tolist() == [2.0, 4.0, 6.0, 8.0]


def test_evaluator_still_raises_for_truly_unknown_op():
    panel = pd.DataFrame({"close": [1.0]})
    ev = ExprEvaluator(panel=panel, extra_ops={"lf_known": lambda x: x})
    with pytest.raises(Exception):
        ev.evaluate("lf_totally_unknown(close)")


def test_extra_ops_does_not_shadow_builtins():
    """Built-in `rank` always wins over an extra_ops entry of the same name.
    Affordance: built-ins are guaranteed-stable; admins cannot break them by
    proposing a same-named operator."""
    panel = pd.DataFrame({"close": [3.0, 1.0, 2.0]})
    ev = ExprEvaluator(panel=panel, extra_ops={"rank": lambda x: x * 0.0})  # malicious override
    result = ev.evaluate("rank(close)")
    # Built-in rank should produce a non-zero ranked series; extra_ops did NOT shadow it.
    assert not (result == 0.0).all()
```

ADAPT the test to the real ExprEvaluator API (DataFrame shape, method names). Read the existing evaluator code first; the test above is illustrative — match the actual constructor + evaluate method.

- [ ] **Step 3: Run, verify FAIL.**

- [ ] **Step 4: Patch `evaluator.py`**

Add `extra_ops: dict[str, Callable[..., np.ndarray]] | None = None` to `ExprEvaluator.__init__`. Store as `self._extra_ops = extra_ops or {}`. In the per-call dispatcher (find the place that raises `EvaluationError` on unknown ops), insert BEFORE the raise:
```python
if name in self._extra_ops:
    return self._extra_ops[name](*args, **kwargs)
```
Place this AFTER the built-in dispatch so built-ins always win (test 3 enforces this).

NO dash characters in any added comment. Anti-pattern: do NOT wrap `self._extra_ops[name](*args, **kwargs)` in a bare try/except that swallows; let exceptions propagate (the validator catches them as fold-level failures with structured SandboxError).

- [ ] **Step 5: Run, verify PASS (new tests + existing evaluator suite).**

- [ ] **Step 6: Commit**

```bash
git add alpha_agent/factor_engine/evaluator.py tests/factor_engine/test_evaluator_extra_ops.py
git commit -m "feat(evaluator): optional extra_ops dispatch hook for Phase 3c sandbox routing"
```

---

### Task 4: `evaluate_factor_candidate` (purged WF + sandbox dispatch + canned tests)

**Files:**
- Create: `alpha_agent/evolution/factor_validation.py`
- Test: `tests/evolution/test_factor_validation.py`

This is the orchestration core: take a `RawProposal` (expression + new operator code) + a `SandboxRunner`, run the 3b canned tests on each new op, build an `extra_ops` dispatch dict that routes each `lf_*` op through `SandboxRunner.evaluate`, then run purged walk-forward OOS folds. Returns `FactorCandidateResult` or `None` (dormant-when-starved).

- [ ] **Step 1: Write the failing test**

```python
# tests/evolution/test_factor_validation.py
import numpy as np
import pytest

from alpha_agent.evolution.factor_validation import (
    FactorCandidateResult, MIN_FOLDS, evaluate_factor_candidate,
)
from alpha_agent.evolution.llm_factor_proposer import RawProposal
from alpha_agent.evolution.sandbox.runner import SandboxRunner
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


@pytest.fixture(scope="module")
def runner():
    r = SandboxRunner()
    yield r
    r.close()


@pytest.mark.asyncio
async def test_returns_none_when_history_below_min_folds(pool, runner):
    """Dormant-when-starved (UX visibility): too little history -> None,
    not a fake low-confidence result."""
    proposal = RawProposal(expression="rank(ts_mean(returns, 12))", new_operators=[])
    result = await evaluate_factor_candidate(pool, runner, proposal)
    assert result is None  # ephemeral pytest DB has no daily_prices history


@pytest.mark.asyncio
async def test_returns_result_with_correct_shape_when_history_sufficient(pool, runner):
    """Seed a synthetic daily_prices panel matching the same shape that
    Phase 2a's evaluate_candidate uses (12 tickers x 120 days). Assert the
    factor candidate returns a FactorCandidateResult with sharpes per fold,
    ic_oos as a float, and operator_test_results empty (no new ops)."""
    # Mirror tests/evolution/test_validation.py SLICE B's _seed_daily_prices helper
    # exactly (deterministic numpy RNG, 12 tickers x 120 days). DO NOT invent a
    # new seeding shape.
    from tests.evolution.test_validation import _seed_daily_prices  # noqa
    await _seed_daily_prices(pool)
    proposal = RawProposal(expression="rank(ts_mean(returns, 12))", new_operators=[])
    result = await evaluate_factor_candidate(pool, runner, proposal)
    assert isinstance(result, FactorCandidateResult)
    assert len(result.sharpes) == result.n_folds >= MIN_FOLDS
    assert isinstance(result.ic_oos, float)
    assert result.operator_test_results == []


@pytest.mark.asyncio
async def test_rejects_proposal_when_new_op_fails_canned_tests(pool, runner):
    """A new operator that returns a scalar fails the shape canned test; the
    proposal is rejected (result is None or operator_test_results captures
    the failure). Forgiveness UX: the rejection is structured, not silent."""
    from tests.evolution.test_validation import _seed_daily_prices  # noqa
    await _seed_daily_prices(pool)
    bad_op = {
        "name": "lf_scalar_op",
        "signature": "(x: ndarray) -> ndarray",
        "python_impl": "def lf_scalar_op(x):\n    return float(x.sum())",
        "doc": "broken; returns scalar",
    }
    proposal = RawProposal(expression="lf_scalar_op(close)", new_operators=[bad_op])
    result = await evaluate_factor_candidate(pool, runner, proposal)
    # Either None (rejected before validation) or a result with failing
    # operator_test_results; depending on implementation choice.
    if result is None:
        # The implementation chose: any canned test failure -> reject candidate.
        pass
    else:
        assert any(not t["passed"]
                   for op_tests in result.operator_test_results
                   for t in op_tests["tests"])
```

If `tests/evolution/test_validation.py` does NOT export `_seed_daily_prices`, replicate the seeding helper inline (mirror the existing pattern exactly; do not invent new ndarray dtype/shape).

- [ ] **Step 2: Run, verify FAIL.**

- [ ] **Step 3: Implement `factor_validation.py`**

```python
"""Phase 3c factor candidate validator. Reuses Phase 2a's purged_fold_indices
+ deflated_sharpe_lite + the same daily_prices read path; extends it to handle
expressions that reference sandboxed new operators."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from alpha_agent.evolution.llm_factor_proposer import RawProposal
from alpha_agent.evolution.sandbox import (
    CannedTestResult, SandboxError, SandboxRunner, run_canned_tests,
)
from alpha_agent.evolution.validation import (
    MIN_FOLDS, purged_fold_indices,
)

_EMBARGO = 5  # >= forward horizon _FWD_RET_DAYS
_N_FOLDS = 3


@dataclass(frozen=True)
class FactorCandidateResult:
    expression: str
    new_operators: list[dict]
    sharpes: list[float]
    ic_oos: float
    n_folds: int
    operator_test_results: list[dict]


def _build_sandbox_dispatch(runner: SandboxRunner, ops: list[dict]) -> dict:
    """Build an extra_ops dict for ExprEvaluator. Each entry routes the named
    operator through SandboxRunner.evaluate; raises on SandboxError so the
    fold-level handler sees it as a fold failure."""
    dispatch = {}
    for op in ops:
        name = op["name"]
        code = op["python_impl"]
        def _make(op_name=name, op_code=code):
            def _fn(x, *args, **kwargs):
                arr = np.asarray(x, dtype=np.float64)
                out = runner.evaluate(op_code=op_code, op_name=op_name,
                                      args={"x": arr, **kwargs})
                if isinstance(out, SandboxError):
                    raise RuntimeError(f"sandbox {out.kind.value}: {out.detail[:200]}")
                return out
            return _fn
        dispatch[name] = _make()
    return dispatch


async def evaluate_factor_candidate(
    pool, runner: SandboxRunner, proposal: RawProposal,
) -> FactorCandidateResult | None:
    """Returns None when usable history yields fewer than MIN_FOLDS folds,
    OR when any new operator fails canned tests (rejected before OOS validation)."""
    # 1. Canned tests on every new operator
    op_test_results: list[dict] = []
    for op in proposal.new_operators:
        result: CannedTestResult = run_canned_tests(
            runner, op_code=op["python_impl"], op_name=op["name"],
            signature=op.get("signature", "(x: ndarray) -> ndarray"),
        )
        op_test_results.append({
            "name": op["name"], "passed": result.passed, "tests": result.tests,
        })
        if not result.passed:
            return None  # reject candidate; any canned-test failure is disqualifying
    # 2. Build extra_ops dispatch for the kernel
    extra_ops = _build_sandbox_dispatch(runner, proposal.new_operators)
    # 3. Load panel + run purged WF (mirror tests/evolution/test_validation.py
    #    SLICE B's data-load path so we hit the SAME synthetic-vs-real shape
    #    issue that 2a's evaluate_candidate already grappled with).
    # READ alpha_agent/evolution/validation.py evaluate_candidate to learn the
    # exact panel-build pattern (close_arr, tickers_arr, fold loop) and reuse it.
    # ... (implementation continues; see plan body for the full sketch)
    raise NotImplementedError("complete the panel-load + fold loop per validation.py pattern")
```

The implementer MUST read `alpha_agent/evolution/validation.py` to reuse the panel-load + per-fold pattern from Phase 2a's `evaluate_candidate`. This task's implementation is the LARGEST in 3c; do NOT skip the read.

The fold loop:
```python
# pseudocode:
fold_sharpes, fold_ics = [], []
for train_idx, test_idx in usable_folds:
    sub_close = np.vstack([close_arr[train_idx, :], close_arr[test_idx, :]])
    # build _Panel + spec from proposal.expression
    # spec = FactorSpec(name=..., expression=proposal.expression, operators_used=...)
    # IMPORTANT: operators_used must include both built-ins AND proposal's new op names
    # call run_kernel(panel, spec, params) with extra_ops={"lf_X": ..., ...}
    # collect kr.test_metrics.sharpe + per-row spearman_ic over test slice
    fold_sharpes.append(...)
    fold_ics.append(...)
if len(fold_sharpes) < MIN_FOLDS:
    return None
return FactorCandidateResult(
    expression=proposal.expression,
    new_operators=proposal.new_operators,
    sharpes=fold_sharpes,
    ic_oos=float(np.mean(fold_ics)) if fold_ics else 0.0,
    n_folds=len(fold_sharpes),
    operator_test_results=op_test_results,
)
```

NOTE: the kernel may not currently accept `extra_ops` as a kwarg. If not, the implementer ADAPTS T3 to ALSO pass `extra_ops` THROUGH the kernel down to ExprEvaluator. This may require a small kernel.py edit; if so, NOTE the cross-file change in the report and re-stage in the same commit (Task 4 is allowed to touch kernel.py if T3's ExprEvaluator change must propagate; do NOT silently revert T3).

- [ ] **Step 4: Run, verify PASS.**

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/evolution/factor_validation.py tests/evolution/test_factor_validation.py
# also include kernel.py if T4 required it
git commit -m "feat(evolution): evaluate_factor_candidate with sandbox-dispatched new operators (Phase 3c)"
```

---

### Task 5: `POST /api/factor-lab/propose` + `GET /api/factor-lab/diagnostic` endpoints

**Files:**
- Create: `alpha_agent/api/routes/factor_lab.py`
- Modify: `alpha_agent/api/app.py` (register the new router via `_load(...)`; mirror existing router-loading style)
- Modify: `api/index.py` (dual-entry: `_load("factor_lab", "alpha_agent.api.routes.factor_lab")`)
- Test: `tests/api/test_factor_lab.py`

- [ ] **Step 1: Write the failing test**

```python
def test_get_diagnostic_returns_current_expression(client_with_db):
    """Visibility UX: an admin sees the diagnostic before paying for the LLM call."""
    r = client_with_db.get("/api/factor-lab/diagnostic")
    assert r.status_code == 200
    body = r.json()
    assert "current_expression" in body
    assert "weak_signal" in body
    assert "symptom_summary" in body


def test_post_propose_requires_admin_auth(client_with_db):
    """Unauthed POST returns 401."""
    r = client_with_db.post("/api/factor-lab/propose")
    assert r.status_code == 401


def test_post_propose_returns_dormant_on_starved_history(authed_client, applied_db):
    """No daily_prices history -> dormant=True, proposed=0, evaluated=0. Cron
    cost guard: do NOT call the LLM if history is below threshold."""
    # The endpoint should check history before paying for the LLM call.
    r = authed_client.post("/api/factor-lab/propose", headers=_auth(),
                            json={"n": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["dormant"] is True
    assert body["proposed"] == 0
```

`authed_client` + `_auth()` mirror the Phase 2b `tests/api/test_evolution_approval.py` pattern (mint a Bearer JWT signed with NEXTAUTH_SECRET).

- [ ] **Step 2: Run, verify FAIL.**

- [ ] **Step 3: Implement `factor_lab.py`**

```python
"""Phase 3c factor-lab admin endpoints.
GET /api/factor-lab/diagnostic  - the propose-time input snapshot.
POST /api/factor-lab/propose    - run the propose loop (diagnostic + BYOK LLM +
                                  validation) and write surviving candidates
                                  as pending rows to factor_proposals.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.auth.dependencies import require_user
# READ the BYOK plumbing first; this import is illustrative:
# from alpha_agent.api.byok import get_llm_client_from_byok
from alpha_agent.evolution.diagnostics import compute_diagnostic
from alpha_agent.evolution.factor_validation import evaluate_factor_candidate
from alpha_agent.evolution.llm_factor_proposer import propose_factors
from alpha_agent.evolution.sandbox import SandboxRunner

router = APIRouter(prefix="/api/factor-lab", tags=["factor_lab"])


@router.get("/diagnostic")
async def get_diagnostic() -> dict:
    pool = await get_db_pool()
    d = await compute_diagnostic(pool)
    return d.to_jsonable()


@router.post("/propose")
async def post_propose(
    user_id: int = Depends(require_user),
    # llm_client = Depends(get_llm_client_from_byok),  # adapt to real BYOK dep
    body: dict | None = None,
) -> dict:
    """Run the propose loop. Returns {evaluated, proposed, dormant}.
    Dormant=True means insufficient history; LLM not called; nothing written."""
    pool = await get_db_pool()
    n = int((body or {}).get("n", 5))
    diagnostic = await compute_diagnostic(pool)
    # Cost guard: bail out before paying for the LLM call if history is starved.
    history_n = await pool.fetchval("SELECT count(*) FROM daily_prices")
    if (history_n or 0) < 3 * 30 * 12:  # 3 folds x 30 days x ~12 tickers
        return {"evaluated": 0, "proposed": 0, "dormant": True}

    # Inline BYOK LLM client construction; adapt to the real plumbing.
    # llm_client = ... (from headers / Depends)

    # raw_proposals = await propose_factors(llm_client, diagnostic, n=n)
    runner = SandboxRunner()
    try:
        results = []
        for proposal in raw_proposals:
            r = await evaluate_factor_candidate(pool, runner, proposal)
            if r is not None:
                results.append(r)
        if not results:
            return {"evaluated": len(raw_proposals), "proposed": 0, "dormant": False}
        # Baseline = current expression evaluated through the same harness.
        # (Implementer: build a synthetic RawProposal for the current expression
        # with no new operators; evaluate_factor_candidate is reusable.)
        baseline = await evaluate_factor_candidate(
            pool, runner,
            type(results[0]).__bases__[0] if False else __import__("alpha_agent.evolution.llm_factor_proposer", fromlist=["RawProposal"]).RawProposal(
                expression=diagnostic.current_expression, new_operators=[]
            ),
        )
        if baseline is None:
            return {"evaluated": len(raw_proposals), "proposed": 0, "dormant": True}
        # DSR-lite deflation: only keep candidates that beat baseline AND deflated > 0
        from alpha_agent.evolution.validation import deflated_sharpe_lite
        import numpy as np
        all_means = [float(np.mean(r.sharpes)) for r in results]
        base_mean = float(np.mean(baseline.sharpes))
        proposed = 0
        for r in sorted(results, key=lambda r: -float(np.mean(r.sharpes))):
            r_mean = float(np.mean(r.sharpes))
            defl = deflated_sharpe_lite(r_mean, all_means, len(raw_proposals))
            if r_mean > base_mean and defl > 0:
                await pool.execute(
                    "INSERT INTO factor_proposals (status, expression, new_operators, evidence, diagnostic) "
                    "VALUES ('pending', $1, $2::jsonb, $3::jsonb, $4::jsonb)",
                    r.expression,
                    json.dumps(r.new_operators),
                    json.dumps({
                        "sharpes": r.sharpes, "ic_oos": r.ic_oos,
                        "deflated_sharpe": defl, "baseline_sharpe": base_mean,
                        "n_folds": r.n_folds, "n_trials": len(raw_proposals),
                        "llm_rationale": next((p.rationale for p in raw_proposals
                                                if p.expression == r.expression), ""),
                        "operator_test_results": r.operator_test_results,
                    }),
                    json.dumps(diagnostic.to_jsonable()),
                )
                proposed += 1
        return {"evaluated": len(raw_proposals), "proposed": proposed, "dormant": False}
    finally:
        runner.close()
```

The implementer MUST adapt the BYOK plumbing line to match the real dependency name + the LLM client method signature. Do NOT leave the comment-line placeholder; replace with the real call.

- [ ] **Step 4: Register router**

In `alpha_agent/api/app.py::create_app()`, find the existing `_load(...)` calls (similar to `_load("evolution", lambda: ...)` from Phase 2c) and add `_load("factor_lab", lambda: factor_lab.router)`.

In `api/index.py`, near the existing `_load("evolution", "alpha_agent.api.routes.evolution")` line, add:
```python
_load("factor_lab",    "alpha_agent.api.routes.factor_lab")
```

- [ ] **Step 5: Run, verify PASS.**

- [ ] **Step 6: Commit**

```bash
git add alpha_agent/api/routes/factor_lab.py alpha_agent/api/app.py api/index.py tests/api/test_factor_lab.py
git commit -m "feat(factor-lab): /diagnostic + /propose admin endpoints (Phase 3c, dual-entry)"
```

---

### Task 6: deploy + smoke

**Files:** none (deployment + smoke only)

- [ ] **Step 1: push**

```bash
git push
```

No migration needed (3a's V016 already in prod).

- [ ] **Step 2: poll the new endpoints**

```bash
BASE="https://alpha.bobbyzhong.com"
# GET diagnostic (no auth needed for the safe diagnostic snapshot? confirm in T5 spec)
# If T5 made diagnostic admin-gated too, this curl will 401; mint the JWT first.
for i in $(seq 1 12); do
  HTTP=$(curl -s --max-time 30 -o /tmp/diag.json -w "%{http_code}" "$BASE/api/factor-lab/diagnostic")
  echo "diagnostic try $i HTTP=$HTTP"
  [ "$HTTP" = "200" ] || [ "$HTTP" = "401" ] && break
  sleep 15
done
cat /tmp/diag.json | python3 -m json.tool

# POST propose (admin auth required); expect dormant=true on starved prod history,
# OR a non-zero evaluated/proposed if the LLM call ran (requires the admin's BYOK
# headers to also be sent in the test smoke).
curl -sX POST "$BASE/api/factor-lab/propose" \
  -H "Authorization: Bearer <admin-JWT>" \
  -H "X-LLM-API-Key: <admin-BYOK-key>" \
  -H "X-LLM-Provider: openai" \
  -d '{"n": 3}' -H "Content-Type: application/json" | python3 -m json.tool
```

EXPECT: `/diagnostic` returns 200 (or 401 if admin-gated) with a non-empty `current_expression` field. `/propose` likely returns `{"dormant": true, ...}` initially because the prod `daily_prices` history is still <1 month; the cost-guard check kicks in BEFORE the LLM call, which is the intended Forgiveness behavior.

- [ ] **Step 3: Verify dual-entry**

```bash
curl -s "$BASE/api/_health/routers" | python3 -c "import sys,json; d=json.load(sys.stdin); print([r for r in d if r.get('name')=='factor_lab'])"
```
Expected: one entry with `loaded: True`. If `loaded: False`, the dual-entry registration in `api/index.py` had an import-time error that the manifest surfaces.

- [ ] **Step 4: Wrap commit** (only if a fix was needed during smoke):
```bash
git add <fixed files>
git commit -m "fix(factor-lab): <specific fix description from smoke>"
git push
```

---

## Self-Review

**Spec coverage (Phase 3 spec § 5.1 - 5.4, § 5.8):**
- Diagnostic engine (T1): pure read; `Diagnostic` dataclass with current_expression + weak_signal + symptom_summary. v1 omits worst_fold_sharpe (deferred to a 3c.1 enhancement).
- LLM proposer (T2): BYOK, structured JSON output, lf_ enforcement, one retry on parse fail, hard caps.
- ExprEvaluator extra_ops hook (T3): the validator's wire to call sandboxed new ops without changing the built-in dispatch.
- evaluate_factor_candidate (T4): canned tests + purged WF + DSR-lite + dormant-when-starved.
- Endpoints (T5): `GET /diagnostic` + `POST /propose`, dual-entry, admin auth on propose, cost-guard before LLM call.
- Deploy + smoke (T6): manifest-based dual-entry verification.

**5 UX principles traced through tests:**
- Intent alignment: `{evaluated, proposed, dormant}` shape matches Phase 2a (T5 test).
- Cognitive load: stable named evidence fields (T4 + T5 assertions).
- Visibility: `/diagnostic` exists as the propose-time snapshot (T5 test).
- Forgiveness: cost-guard returns dormant BEFORE LLM call on starved history (T5 test); JSON parse retry once (T2 test); a single bad operator drops only its candidate (T2 + T4 tests).
- Affordance: stable endpoint paths; `Diagnostic` field names mirror the prompt template sections.

**Anti-pattern guardrails:**
- Dual-entry: every endpoint added in BOTH `app.py` and `api/index.py` via `_load(...)` (T5).
- Silent exception: every try/except surfaces structured (RawProposal validation drops; canned-test failure returns None; sandbox failure raises caught as fold failure; BYOK LLM raise propagates as 502 with structured detail).
- `/healthz/*` trap: all new endpoints are under `/api/factor-lab/*` so the Vercel rewrite reaches them.

**Out of scope (deferred to 3d):**
- `/factor-lab` UI (TmPane sections, ProposalsTable, Approve/Reject buttons).
- `POST /proposals/{id}/approve|reject|rollback` endpoints (write factor.custom_expression, register operators in extended_operators).
- Refresh trigger that calls `refresh_allowed_ops(pool)` after approve.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-23-phase3c-validator-proposer.md`.

**1. Subagent-Driven (recommended)** — fresh subagent per task with two-stage review, consistent with 3a / 3b / 2a / 2b.

**2. Inline Execution** — same-session batched execution.

Pick approach to proceed.
