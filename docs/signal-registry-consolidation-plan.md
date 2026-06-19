# Consolidation Plan: a single Signal Registry

Status: proposed (2026-06-19), revised same day per the llm-council review
(`docs/_council-consolidation-review/FINAL_verdict.md`). Council call: GO WITH
CHANGES (data-only manifest with string import paths, not decorator/eager imports;
split the vague `tier`; CI-fail-on-stale codegen; lazy-import test). It is now
**step 3** of the master plan (`docs/ROADMAP.md`): the product ledger + run-health
gates (steps 1-2) come first, because the registry is internal hygiene while the
ledger is what makes the product honest. Author note: scoped after integrating the
RSRS factor, which required edits to ~10 separate registration sites (evidence below).

## 1. Diagnosis (what is actually wrong)

The felt problem is "the engine is too fragmented, adding/changing a factor breaks
my thought-chain." Grounding that against the code gives a precise, and partly
counter-intuitive, root cause:

- The factor **logic** is NOT over-split. `factor_engine/` (ast_nodes -> parser ->
  evaluator -> kernel) is a compiler pipeline; `evolution/` is factor discovery +
  sandboxed validation; `signals/factor.py` is a thin consumer of the kernel;
  `factors/alpha158.py` is an expression library. These are layered by
  responsibility, not duplicated. Merging them would break separation of concerns
  and the kernel's reuse by the screener and tests. **We will not merge these.**
- The real fragmentation is the **signal-registration spread**: a single signal's
  identity is hand-maintained in ~10 independent places with no single source of
  truth. Adding one signal (RSRS) required coordinated edits to all of them; miss
  one and you get a silent bug (e.g. a signal that is weighted but never computed,
  or shown in the UI with the wrong horizon).

### The 10 hand-maintained registration sites

Backend (7):
1. `fusion/weights.py` -> `DEFAULT_WEIGHTS` (name -> weight)
2. `signals/horizons.py` -> `SIGNAL_HORIZON_DAYS` (name -> horizon)
3. `fusion/policy.py` -> `_CORE_SIGNALS` (which names are core)
4. `backtest/ic_engine.py` -> `_ACTIVE_SIGNALS` (which names get IC tracked)
5. `cli/build_card.py` -> `_SIGNAL_NAMES` (+ a fixture z-map)
6. `api/cron/fast_intraday.py` -> `_ALL_MODULES` (name -> module) + `_TIERS` (cadence)
7. `api/routes/health.py` -> `_SIGNAL_NAMES` (monitoring)

Frontend (3) — hand-written mirrors of the backend, with NO codegen:
8. `frontend/src/lib/weights-override.ts` -> `DEFAULT_WEIGHTS`
9. `frontend/src/lib/signal-horizons.ts` -> `SIGNAL_HORIZON_DAYS`
10. `frontend/src/lib/signal-labels.ts` -> `SIGNAL_DISPLAY_LABEL_FALLBACK`

There is no single source of truth. Each list drifts independently (today's
`build_card._SIGNAL_NAMES` and `health._SIGNAL_NAMES` are already missing
`geopolitical_impact`/`supply_chain`, i.e. they have already drifted).

## 2. Non-goals (deliberately NOT doing)

- Not merging `factor_engine` / `evolution` / `signals/factor` / `factors`
  (correct layering; merging risks circular imports and breaks reuse).
- Not touching the `fusion <-> backtest` seam (it is cleanly decoupled through the
  `signal_weight_current` table; measurement vs application is the right boundary).
- Not changing any signal's numeric behavior. Every phase below is structural; the
  composite a card gets must be byte-identical before and after.

## 3. The fix, phased (each phase independently shippable + reversible)

### Phase 1 — backend `SIGNAL_REGISTRY` (highest ROI, low risk)

New module `alpha_agent/signals/registry.py`. It must be a **data-only manifest**:
pure dataclasses, NO imports of pandas / yfinance / signal modules / fusion / cron /
api. Signal implementation modules must NOT import the registry (no circular dep).
Reference signal code by **string import path**, resolved lazily by the consumer
that actually needs the module (the cron), never at registry import time. Do not use
decorator self-registration (rejected by council: it forces importing every signal
module to populate the registry, which breaks serverless cold-start hygiene and makes
discovery depend on import side effects).

Split the one vague `tier` into explicit, separately-meaningful fields:

```python
@dataclass(frozen=True)
class SignalMeta:
    name: str
    module_path: str       # "alpha_agent.signals.rsrs" (string; lazy-resolved)
    compute_fn: str        # "fetch_signal"
    cron_group: str        # refresh cadence: "tech" | "mid" | "slow" | "full"
    core_for_coverage: bool  # in the sqrt-coverage core set?
    active_in_ic: bool     # tracked by ic_engine?
    enabled_in_live: bool
    default_weight: float
    horizon_days: int
    fusion_cap: float | None  # STATIC_V2 guardrail cap
    label_zh: str
    label_en: str
    data_deps: tuple[str, ...] = ()  # e.g. ("daily_prices.high", "daily_prices.low")

SIGNAL_REGISTRY: tuple[SignalMeta, ...] = ( ... one entry per signal ... )
```

(`rating_tier` BUY/OW/HOLD/UW/SELL is a separate concept and stays out of the
registry; it is rating OUTPUT, not signal metadata.)

Then the 7 backend sites become one-line derivations, e.g.:

```python
DEFAULT_WEIGHTS   = {s.name: s.weight for s in SIGNAL_REGISTRY}
SIGNAL_HORIZON_DAYS = {s.name: s.horizon_days for s in SIGNAL_REGISTRY}
_CORE_SIGNALS     = tuple(s.name for s in SIGNAL_REGISTRY if s.core)
_ACTIVE_SIGNALS   = tuple(s.name for s in SIGNAL_REGISTRY)
_SIGNAL_NAMES     = [s.name for s in SIGNAL_REGISTRY]
_ALL_MODULES      = {s.name: import_module(f"alpha_agent.signals.{s.module}") for s in SIGNAL_REGISTRY}
_TIERS            = {t: [s.name for s in SIGNAL_REGISTRY if s.tier == t] for t in ("tech","mid","slow")} | {"full": [...]}
```

Net effect: adding a signal becomes ONE registry entry + the signal module
(down from ~10 edits). `cli/build_card`'s fixture z-map and `policy.py`'s
per-signal caps fold in via the same registry.

Verification (the safety of this phase):
- A migration test that asserts each derived dict EQUALS a golden snapshot of the
  current hardcoded values (so the refactor provably changes nothing).
- A registry-integrity test: every registered signal's `module_path` resolves to a
  module exposing `compute_fn`; weights sum to 1.0; no name appears in a derived
  list but not the registry. This is what makes future drift impossible.
- A lazy-import regression test (council must-have): `import
  alpha_agent.signals.registry` must NOT pull in `yfinance`, `pandas`, or any signal
  module (assert they are absent from `sys.modules` after a clean import). This is
  what keeps the manifest data-only and serverless-cold-start-safe.
- Full suite green; build a card before/after and assert identical composite.

### Phase 2 — frontend codegen (kill the hand-written mirrors)

- Add `GET /api/_signal_registry` returning the registry (name -> {weight, horizon,
  label_zh, label_en, core}).
- Generate the frontend maps from it instead of hand-writing them. Two options:
  (a) build-time: a small script writes `frontend/src/lib/signal-registry.gen.ts`
      from the endpoint / openapi (mirrors how `api-types.gen.ts` is generated), or
  (b) the existing `weights-override.ts` / `signal-horizons.ts` / `signal-labels.ts`
      re-export from the generated file.
- Verification: regenerate openapi + the gen file; `tsc` + frontend tests green; the
  generated values match the backend registry exactly (drift becomes a build error).

### Phase 3 — delete dead `llm/_legacy/` (independent cleanup)

- `llm/_legacy/{openai,kimi,ollama}.py` are superseded by the LiteLLM client and only
  reachable behind `LLM_USE_LEGACY`. Confirm the flag is unset in prod, then delete
  the three modules + the fallback branch in `llm/factory.py` + the reference in
  `api/byok.py`.
- Verification: factory tests pass with the flag removed; grep shows no remaining
  `_legacy` import; one release of monitoring before deletion if you want a margin.

## 4. Sequencing + success criteria

Order: Phase 1 -> Phase 2 -> Phase 3. Phase 1 is self-contained and fully testable
(equality snapshot = zero behavior change); Phase 2 builds on it; Phase 3 is
unrelated dead-code removal that can happen any time.

Done when:
- Adding a signal = 1 registry entry + 1 signal module (verified by re-deriving the
  RSRS integration as a single entry).
- A drift test fails if any list disagrees with the registry.
- Frontend signal maps are generated, not hand-written.
- `llm/_legacy/` is gone.

What this explicitly does NOT promise: a smaller package count. The win is a single
source of truth for signal identity, not fewer files. The factor/discovery/fusion
layering stays, because it is correct.
