# Consolidation Plan: a single Signal Registry

Status: proposed (2026-06-19). Author note: this plan was scoped after integrating
the RSRS factor, which required edits to ~10 separate registration sites. That
exercise is the evidence base below.

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

New module `alpha_agent/signals/registry.py`:

```python
@dataclass(frozen=True)
class SignalMeta:
    name: str
    module: str          # importable as alpha_agent.signals.<module>
    weight: float        # default fusion weight
    horizon_days: int    # native forward horizon
    core: bool           # in the coverage-damping core set?
    tier: str            # fast-cron cadence: "tech" | "mid" | "slow"
    label_zh: str
    label_en: str
    cap: float | None = None   # optional STATIC_V2 guardrail cap

SIGNAL_REGISTRY: tuple[SignalMeta, ...] = ( ... one entry per signal ... )
```

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
- A registry-integrity test: every registered signal has an importable module with
  a `fetch_signal`; weights sum to 1.0; no name appears in a derived list but not
  the registry. This test is what makes future drift impossible.
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
