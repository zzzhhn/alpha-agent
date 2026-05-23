# Phase 3: LLM Factor Invention Design Spec

> Builds on Phase 1 + 2 (forward returns, adaptive weights, calibration, methodology proposer, approval queue). Phase 3 is the human-in-the-loop LLM exploration layer for new factor expressions and new operators. Inspired by Karpathy autoresearch (single editable surface, fixed eval budget, single comparable metric).

**Status:** Brainstorm complete 2026-05-23. Awaiting user sign-off before writing implementation plan.

---

## 1. Goals

1. From the `/factor-lab` admin page, one click runs:
   - A diagnostic pass that picks the current weakest signal + worst OOS fold (no LLM).
   - One BYOK LLM call (admin's own key) that returns N candidates, each containing one factor expression and optionally a small number of new operator definitions.
   - Validation of every candidate via the Phase 2a purged walk-forward harness, with each new operator executed in a sandboxed subprocess.
   - Writes survivors as pending rows in a new `factor_proposals` table.
2. Admin reviews each proposal (expression preview, new-operator code, evidence) and clicks Approve or Reject.
3. Approve: the operator code is registered in an `extended_operators` store (always sandboxed at runtime, never inlined), and `factor.custom_expression` is set so the live factor pipeline uses the new expression on the next signal refresh.
4. Reject: status only; no engine_config write.
5. Rollback: reverts `factor.custom_expression` to its previous value. Operator code stays registered (so any prior approvals using it stay reproducible), but the active expression is reverted.

## 2. Non-Goals

- No cron, no overnight autonomy. The whole subsystem is admin-button-driven (preserves BYOK).
- LLM proposals for combine strategy, rating thresholds, or IC-accept threshold (those are Phase 2-pre knobs and Phase 2a's territory).
- Cross-validation beyond DSR-lite (full CPCV remains explicitly out, same as Phase 2a).
- Multi-tenant factor isolation (admin tier only; per-user factor proposals are deferred).
- LLM-proposed changes to non-factor code (kernel, data layer, etc.).

## 3. Decisions Locked (2026-05-23 brainstorm)

| Knob | Decision |
|------|----------|
| LLM key source | Admin BYOK on-demand (one click = one LLM call) |
| Proposal scope | Expression + new operator |
| Approval surface | Standalone `/factor-lab` + new `factor_proposals` table (do NOT extend `config_change_log`) |
| Sandbox model | Subprocess + RLIMIT + seccomp (linux prod) / restricted-globals fallback (macOS dev) |
| Trigger UX | System diagnostic auto-populates prompt, admin clicks Propose (no free-form admin prompt in v1) |
| Live expression storage | New `factor.custom_expression` knob; overrides `factor.mode` short/long preset when set |
| Default proposal batch size N | 5 candidates per click (broader exploration; tradeoff is higher BYOK token cost the admin pays once) |
| Per-operator sandbox timeout | 30 s per evaluation (wider than the 5 s draft; some legitimate operators on a 252-day panel may need more); validator-total cap stays ~10 min |
| pyseccomp dependency | Hard dependency on Linux (CI + prod); macOS dev skips seccomp and uses RLIMIT + restricted globals + timeout fallback. CI runs the Linux profile so prod parity is guaranteed |
| Rollback semantics for new operators | Operators stay registered after rollback (already journaled, reproducibility). Only `factor.custom_expression` reverts |
| Code-tier model | 3 layers only: rejected / pending / approved. Approved operators ALWAYS run in subprocess sandbox forever (no Promote-to-inline tier). Performance is mitigated via persistent worker pool + shared-memory IPC, dropping single-call cost from ~50 ms (fork-per-call) to ~5 ms (warm worker + shared mem) |

## 4. Architecture

```
admin clicks Propose in /factor-lab
        |
        v
diagnostic engine (no LLM): picks weakest signal + worst OOS fold + symptom summary
        |
        v
prompt template + diagnostic snapshot
        |
        v  (admin's BYOK LLM key)
LLM call (single round, N=3 candidates by default, structured JSON)
        |
        v
for each candidate:
    AST validate expression (whitelist = built-ins UNION extended_operators UNION proposal's new ops)
    for each new operator:
        spawn subprocess sandbox; run canned tests (signature, NaN, shape)
        reject candidate if any test fails
    run Phase 2a harness (purged WF folds + DSR-lite) with sandbox dispatch for new ops
        |
        v
write factor_proposals rows: expression, new_operators[], evidence, diagnostic
        |
        v
admin reviews in /factor-lab table; approves or rejects
        |
        v  (on approve)
register new operators in extended_operators (sandboxed forever);
set_config('factor.custom_expression', expression, source='approved')
        |
        v
next signal refresh picks up the new expression via _resolve_default_expr()
```

## 5. Components

### 5.1 Diagnostic engine
File: `alpha_agent/evolution/diagnostics.py`

Inputs: pool, current effective expression (`get_config("factor.custom_expression")` or `_resolve_default_expr()` fallback), recent IC history.

Output: structured `Diagnostic`:
```python
@dataclass(frozen=True)
class Diagnostic:
    current_expression: str
    weak_signal: str | None             # lowest 30d IC, from signal_ic_history
    weak_signal_ic: float | None
    worst_fold_sharpe: float | None     # from a fold trace cached at last validator run
    worst_fold_window: tuple[str, str] | None  # ISO dates
    symptom_summary: str                # 2 or 3 sentences for the prompt
```

Pure read path. No LLM. The output JSON-serializes into the LLM prompt.

### 5.2 LLM factor proposer
File: `alpha_agent/evolution/llm_factor_proposer.py`

```python
async def propose_factors(
    pool, diagnostic: Diagnostic, user_id: int, n: int = 3
) -> list[RawProposal]:
    ...
```

- BYOK: pulls the user's LLM client via the existing BYOK plumbing (the user-keyed `create_llm_client` path used elsewhere in alpha-agent). Never touches a platform key.
- Prompt template embeds the diagnostic snapshot, the AST grammar (operator and operand whitelists), and the structured-output contract:
  ```json
  {"proposals":[{
     "expression":"<dsl>",
     "new_operators":[{"name":"lf_<snake>","signature":"(x: ndarray, window: int) -> ndarray","python_impl":"...","doc":"..."}],
     "rationale":"<2 to 3 sentences>"
  }]}
  ```
- Naming rule enforced server-side: every new operator must match `^lf_[a-z_][a-z0-9_]{1,30}$`. The `lf_` prefix prevents collision with the 68 built-ins.
- One retry on JSON parse failure. Hard token cap (e.g. 8000 output tokens, to accommodate N=5 proposals with operator code). Hard wall-clock cap on the LLM call (60 s).
- Default `n=5` (admin-tunable per call up to a hard cap of 8).

### 5.3 Subprocess sandbox
Directory: `alpha_agent/evolution/sandbox/`

- `runner.py`: `class SandboxRunner` manages a **persistent worker pool** (size configurable, default 2). Each worker is a long-lived subprocess that handles many sequential `evaluate(op_code, op_name, columns)` calls. Arrays cross the IPC seam via `multiprocessing.shared_memory` (zero-copy for large ndarrays); only the op_code string and dtype/shape metadata go through `pipe.send_pyobj`. Per-call timeout: 30 s.
- `worker.py`: the subprocess entrypoint.
  - Linux prod (hard pyseccomp dep): sets `RLIMIT_CPU=60`, `RLIMIT_AS=1G`, `RLIMIT_NPROC=0`, `RLIMIT_NOFILE=8`; installs a seccomp filter via `pyseccomp` allowing only `read, write, mmap, mremap, brk, futex, sigreturn, exit_group, rt_sigaction, shm_open` (last one for the shared-memory ndarray channel). No `fork`, `execve`, `open` (writable), `socket`, `connect`.
  - macOS dev fallback: `RLIMIT_CPU` + per-call `signal.alarm()` timeout + restricted `__builtins__`. NO seccomp on macOS. Documented explicitly as dev-only; CI runs the Linux profile so prod parity is enforced.
  - `exec` runs each operator inside a FRESH globals dict per call (`{"np": numpy, "__builtins__": _RESTRICTED_BUILTINS, ...bound_args}`), so worker reuse never carries operator-A's state into operator-B. No `import`, no `__builtins__.open`, no attribute access on builtins beyond a whitelist.
  - Worker recycling: after every 1000 calls OR 10 minutes wall-clock OR any uncaught exception, the worker is killed and respawned. Bounds blast radius from any future sandbox escape.
- IPC payload: op_code (str) + op_name + arg metadata go via pickle over a pipe; ndarrays are zero-copy via `multiprocessing.shared_memory`. Single-call latency target ~5 ms (warm worker), ~50 ms (cold spawn at pool init).
- Vectorization: per-row dispatch into the subprocess would be ~250 ms per ticker per timestep. Mitigation: the kernel calls each operator at the COLUMN level (one ndarray pass per ticker, or one matrix pass per panel timestep); one IPC round-trip per operator invocation per panel-pass, not per row. Typical validation cost (N=5 candidates × 3 folds × ~5 column evaluations × 5 ms warm IPC) ~375 ms total subprocess overhead.

### 5.4 Validator (extends Phase 2a)
File: `alpha_agent/evolution/factor_validation.py`

```python
@dataclass(frozen=True)
class FactorCandidateResult:
    expression: str
    new_operators: list[NewOperatorSpec]
    sharpes: list[float]            # per-fold OOS Sharpe
    ic_oos: float
    n_folds: int
    operator_test_results: list[dict]  # one entry per new op (pass / fail + reason)

async def evaluate_factor_candidate(
    pool, expression: str, new_operators: list[NewOperatorSpec]
) -> FactorCandidateResult | None:
    ...
```

- Reuses `purged_fold_indices` and `deflated_sharpe_lite` from `alpha_agent/evolution/validation.py`.
- For each new operator: run a 3-test canned suite (random ndarray, NaN-only input, single-row input). Reject the whole candidate if any test fails.
- Wires a per-call dispatch: when the kernel encounters an op_name with `lf_` prefix or in the proposal's `new_operators`, it routes the column through `SandboxRunner`; otherwise the existing in-process path.
- Returns `None` when usable `daily_prices` history yields fewer than MIN_FOLDS folds (dormant-when-starved, same guard as 2a).

### 5.5 factor_proposals schema (V016)
```sql
-- V016__factor_proposals.sql (2026-05-23)
CREATE TABLE factor_proposals (
    id              bigserial PRIMARY KEY,
    status          text NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending','approved','rejected')),
    expression      text NOT NULL,
    new_operators   jsonb NOT NULL DEFAULT '[]'::jsonb,
    evidence        jsonb NOT NULL,
    diagnostic      jsonb NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    decided_at      timestamptz,
    decided_by      bigint
);
CREATE INDEX idx_factor_proposals_status_created
    ON factor_proposals (status, created_at DESC);
```

- `new_operators`: list of `{name, signature, python_impl, doc, test_results}`.
- `evidence`: `{sharpes, ic_oos, deflated_sharpe, baseline_sharpe, n_folds, n_trials, llm_rationale}`.
- `diagnostic`: the `Diagnostic` snapshot at propose time.
- `decided_by`: admin `user_id` (audit trail).

### 5.6 extended_operators registry
- New table `extended_operators(name PRIMARY KEY, signature text, python_impl text, doc text, registered_at timestamptz, registered_by bigint, source_proposal_id bigint REFERENCES factor_proposals(id))`.
- On approval the implementation is INSERTed once; subsequent identical reproposals are detected by `python_impl` hash and dedup.
- The `ExprEvaluator` at module load merges this table into its dispatch table as ALWAYS-SANDBOXED routes (routed through the persistent worker pool). No in-process exec of LLM-authored code, ever, even after approval. The cost of permanent sandboxing is acceptable because (a) approved operators are a small handful, (b) the sandbox is column-batched, (c) the worker pool keeps warm processes so single-call latency is ~5 ms not ~50 ms, and (d) there is no Promote-to-inline tier (decision locked 2026-05-23: pure permanent sandbox).
- The AST validator `_ALLOWED_OPS` becomes `_BUILTIN_OPS | _load_extended_op_names()`, computed at module load. Reload on operator add.

### 5.7 factor.custom_expression knob
- Add to `alpha_agent/config_store.py::DEFAULTS`: `"factor.custom_expression": None`.
- Patch `alpha_agent/signals/factor.py::_resolve_default_expr`:
  ```python
  def _resolve_default_expr() -> str:
      custom = get_config("factor.custom_expression", None)
      if custom:
          return custom
      mode = get_config("factor.mode", os.environ.get("ALPHA_FACTOR_MODE", "short")).strip().lower()
      return LONG_TERM_FACTOR_EXPR if mode == "long" else SHORT_TERM_FACTOR_EXPR
  ```
- Reading `factor.custom_expression` is cheap (process cache). No DB hit on hot path.

### 5.8 Backend endpoints (new router `alpha_agent/api/routes/factor_lab.py`)
- `GET /api/factor-lab/diagnostic` (admin auth): current `Diagnostic` snapshot for the panel.
- `POST /api/factor-lab/propose` (admin auth, accepts the user's BYOK LLM key via the existing user-key header convention): diagnostic + LLM + validation + writes pending rows. Returns `{evaluated, proposed, dormant}`.
- `GET /api/factor-lab/proposals?status=pending` (admin auth).
- `POST /api/factor-lab/proposals/{id}/approve` (admin auth): registers operators in `extended_operators`, calls `set_config('factor.custom_expression', expression, source='approved')`.
- `POST /api/factor-lab/proposals/{id}/reject` (admin auth): status only.
- `POST /api/factor-lab/proposals/{id}/rollback` (admin auth): reverts `factor.custom_expression` to its prior value via `set_config(..., source='rollback')`. Operators stay registered.
- Router must be enumerated in BOTH `alpha_agent/api/app.py` AND `api/index.py` (dual-entry rule).

### 5.9 /factor-lab UI
File: `frontend/src/app/(dashboard)/factor-lab/page.tsx` (server component; admin-only).

Layout (TmPane sections, matching the existing tm-* token style):
1. CURRENT LIVE EXPRESSION (read of `_resolve_default_expr` result, source label: custom vs preset).
2. DIAGNOSTIC SNAPSHOT (rendering `GET /diagnostic` output).
3. PROPOSE button + spinner + last-run summary (`evaluated: N proposed: M dormant: bool`).
4. PENDING PROPOSALS table (expression preview with monospace, new-operator code in a collapsible details, deflated_sharpe vs baseline bar, Approve / Reject buttons; in-flight disable per row, same pattern as ProposalsTable in 2b).
5. HISTORY tab (approved + rejected, decided_at, decided_by; rollback button per approved row).

Client helpers go into `frontend/src/lib/api/factor-lab.ts` (mirrors `lib/api/evolution.ts` shape).

## 6. Security

- BYOK LLM key: passed in the user's existing key header; never written to `factor_proposals` or any log row.
- Subprocess sandbox: no network (seccomp blocks `socket`), no fs writes (no `open` in write modes), no `fork`/`exec`, hard CPU and memory caps. Operator code is read-only inside the worker.
- AST validation runs BEFORE the sandbox spawn: a malformed proposal never reaches `exec`.
- Approved operator code is persistently sandboxed at runtime; no path inlines LLM code into the main process.
- Operator additions journal `registered_by` + `source_proposal_id` for audit.
- BYOK key absence: if the user has not stored an LLM key, `/propose` returns 412 "no LLM key on file" with a UI prompt to set one, instead of falling back to a platform key.

## 7. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Sandbox IPC overhead slows IC engine | Persistent worker pool + shared-memory ndarray IPC drops single-call to ~5 ms; column-batched dispatch (one subprocess call per panel-level op invocation, not per row); validation cap ~10 min per propose click |
| Worker reuse leaks state across operators | Fresh globals dict per call + worker recycle after 1000 calls / 10 min / any uncaught exception |
| macOS dev parity with Linux seccomp | Document the gap; CI runs the Linux profile; dev sandbox uses RLIMIT + restricted globals + timeout (good enough for dev iteration; prod parity guaranteed in CI) |
| DSR-lite trial inflation with new operators | Each proposal counts as 1 trial, regardless of how many new ops it bundles (conservative; matches 2a's accounting) |
| LLM hallucinates a built-in operator name with new code | The `lf_` prefix is enforced server-side; mismatch rejects the proposal pre-AST |
| Approved operator turns out malicious | Always-sandboxed (no inlining), no network, no fs writes; worst case is wasted compute on that operator's invocations |
| Multiple admins racing on approve | factor.custom_expression is journaled via set_config; rollback is per-row by id, race-free |

## 8. Phasing

Each sub-phase is independently mergeable and testable. Recommended order:

- **3a foundation**: V016 schema, `factor.custom_expression` knob, `_resolve_default_expr` extension, AST whitelist union with `extended_operators`, `extended_operators` registry table.
- **3b sandbox**: subprocess runner + worker + canned operator test harness; unit tests covering seccomp-block behavior (Linux CI) and macOS-dev fallback.
- **3c validator + LLM proposer**: diagnostic engine, prompt template, `evaluate_factor_candidate`, the `POST /propose` route.
- **3d UI + approval**: `/factor-lab` page, approve/reject/rollback endpoints + tests, frontend client + table component.

Each sub-phase will get its own implementation plan via `superpowers:writing-plans` once this spec is approved.

## 9. Open Questions for User Sign-off (resolved 2026-05-23)

1. **Default proposal batch size N**: `5`. Hard cap 8 per call.
2. **Per-operator sandbox timeout**: `30 s` per operator evaluation (wider than the 5 s draft; validator-total cap stays ~10 min).
3. **`pyseccomp` dependency level**: hard dep on Linux (CI + prod); macOS dev falls back to RLIMIT + restricted globals + timeout (no seccomp on Darwin). CI gate enforces prod profile.
4. **Rollback semantics for new operators**: operators stay registered after rollback; only `factor.custom_expression` reverts.
5. **Tier model**: 3 layers (rejected / pending / approved), no Promote-to-inline tier. Approved operators always sandboxed forever, with persistent worker pool + shared-memory IPC keeping single-call cost ~5 ms.

## 10. Out of Scope (deferred)

- LLM proposing combine strategy or rating thresholds (Phase 2-pre's domain).
- Full CPCV / nested CV validation.
- Multi-tenant factor proposals.
- Cron-driven autonomous mode.
- LLM iterative refinement loop (Karpathy-style "edit, eval, keep/discard" within a single propose call). v1 returns N candidates per click, no internal iteration. The iterative loop is a 3e stretch.
