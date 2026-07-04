# Decompose `PlanIngestionWorkflow._execute` — Implementation Plan

**Version:** 1.1 (post-CRP R1 + Stage-1 re-anchor)
**Date:** 2026-07-04
**Branch:** `refactor/plan-ingestion-execute` (off `origin/main` `faef9d1f`)
**Type:** Behavior-preserving decomposition of a god-method
**Precedent:** the `context_seed` phases/ refactor (`docs/design/context-seed-refactor/`) — same
family of work, but this one is **higher-coupling** (see §4).
**Status:** Stage 0 (golden) + Stage 1 (`_finalize_success`) implemented & green; Stages 2–4 pending, CRP-hardened.

## 0. Post-CRP triage (v1.1)

> A code-grounded CRP (R1, Appendix C) verified against the live method changed the design of Stages 2–4.
> All 9 suggestions accepted (Appendix A). The four that matter:
> - **R1-S1** — line numbers were stale post-Stage-1; re-anchored to symbolic references (below).
> - **R1-S2** — `check_cost`/`fail`/`save_state` **cannot** be `_IngestionRun` methods: `fail` needs
>   `self.metadata.workflow_id` and `save_state` needs `state_dir`; they become **workflow methods
>   taking `run`**, and `_IngestionRun` stays a pure data bag (§4 rewritten).
> - **R1-S3** — `_execute` has **two early-exit shapes with different span-close behavior**; each
>   extracted `_run_<phase>` must **own its phase-span lifecycle** (§5 Stage 4 constraint).
> - **R1-S6** — the golden covers only the success path; a **forced-`_fail` forensics test is now a
>   Stage-2 precondition** (§5 / §6).

---

## 1. Problem & the reframe from investigation

`workflows/builtin/plan_ingestion_workflow.py` (~5,036 lines post-Stage-1); the target method
`_execute` runs to EOF. *(Symbolic anchors — grep, don't trust absolute L-numbers; per CRP R1-S1 the
original v1.0 numbers were pre-Stage-1.)* After Stage 1, `_finalize_success` occupies the first ~163
lines (was L3812–3975) and `_execute` is **~1,059 lines** (was 1,176; anchor: `def _execute`).

**Investigation (2026-07-04) reframed the target.** The phase *logic* is **already extracted**
into dedicated methods — `_phase_parse` (115), `_phase_assess` (133), `_phase_transform` (127),
`_phase_refine` (84), `_phase_emit` (64). `_execute` does **not** inline phase logic. Its body is
three regions (anchor by the marker comments, not line numbers):

| Region | Anchor | ~LOC | What it is |
|---|---|---|---|
| **Setup** | method top → `_root_span_ctx =` | ~230 | typed config + local aliases, kaizen-config discovery, Mottainai onboarding load, capability propagation (Layer 5, **and its `_fail` fires *before* the root span opens — R1-S5**), OTel root span, and **4 nested closures** |
| **Phase pipeline** | `# --- DISCOVER` → `# --- DONE` | ~795 | orchestration *glue* around each `_phase_*` call: DISCOVER → PREFLIGHT → MANIFEST → PARSE (+acyclicity gate, degenerate-parse) → ASSESS (+low-quality) → TRANSFORM → REFINE (+spend gate, guards, kaizen capture, snapshot) → EMIT (+traceability) → DONE |
| **Finalization** | ✅ **already extracted** to `_finalize_success` (Stage 1) | — | kaizen diagnostics, quality signals, seed-quality, provenance, OTel finalize, success `WorkflowResult` |

So the decomposition is not "extract the phases" (done) — it's **thin out the orchestration glue and
the bookends**, whose bloat is driven by shared mutable state threaded through 4 closures.

## 2. What already exists (do NOT re-derive)

- **`state = IngestionState()`** — an existing run-state object (`state.total_cost`, `state.current_phase`,
  `state.error`, `state.to_dict()`). Partial run-context infrastructure.
- **Phase methods** `_phase_{parse,assess,transform,refine,emit}` — keep as-is; they are the callees.
- **Good test coverage** — ~15+ `tests/unit/contractors/test_*` + `tests/unit/test_plan_ingestion_workflow.py`
  exercise this path. (Note: that last file has ~25 **pre-existing** `ContextContract` failures unrelated
  to this work — baseline them before starting; see §6.)

## 3. The coupling that makes this hard — the 4 nested closures

`_execute` defines 4 closures that the pipeline glue calls throughout, each capturing locals:

| Closure | @L | Captures | Semantics to preserve |
|---|---|---|---|
| `progress(msg)` | 3944 | `nonlocal current_step`, `on_progress`, `total_steps` | increments a step counter, fires the callback |
| `_check_cost(label)` | 3950 | `warn_cost_usd`, `max_cost_usd`, `state` | **early-exit**: returns a `WorkflowResult` when a cost cap is exceeded |
| `_save_state()` | 3968 | `state_dir`, `state`, `_tracer` | persists `state.to_dict()` under an OTel io span |
| `_fail(msg)` | 3991 | `state`, `_save_state`, `output_dir`, `_forensics` (ledger), `plan_path`, `steps`, `self` | sets FAILED, persists failure-forensics JSON, returns an error `WorkflowResult` |

These closures are the reason the glue can't be trivially cut into methods: any extracted block that
calls `_check_cost`/`_fail` depends on ~10 captured locals. **The decomposition's central design
decision is how to carry that state.**

## 4. Core design decision — run-context (data) + orchestration methods (behavior)

**Corrected v1.1 (CRP R1-S2/S8/S9).** The v1.0 draft made the closures methods *on* the dataclass —
that cannot work: `fail()` needs `self.metadata.workflow_id` (via `WorkflowResult.from_error`) and
`save_state()` needs `state_dir` + the module-level `_tracer`, none of which a pure dataclass carries.
So split responsibilities:

**`_IngestionRun` — a pure data bag** of cross-phase **mutable run-state** (passed *by reference*,
never `deepcopy`-ed — the `state` and `forensics` accumulation depends on shared identity, R1-S8):

```python
@dataclass
class _IngestionRun:            # one per _execute() invocation — DATA ONLY
    state: IngestionState
    steps: list
    output_dir: Path
    plan_path: Path
    state_dir: Path             # added (R1-S2): save_state needs it
    forensics: dict             # the _forensics ledger — mutated in-place at ~6 sites (R1-S8)
    total_steps: int
    current_step: int = 0
    on_progress: Callable | None = None
    warn_cost_usd: float | None = None
    max_cost_usd: float | None = None
    def progress(self, msg): ...          # ONLY this is safe as a run method (pure counter + callback)
```

**The 3 stateful closures become workflow methods taking `run`** (they keep `self.metadata`, `_tracer`):
```python
def _rt_check_cost(self, run, label) -> WorkflowResult | None: ...   # early-exit signal
def _rt_save_state(self, run): ...
def _rt_fail(self, run, msg) -> WorkflowResult: ...                  # uses self.metadata.workflow_id
```

**Results are NOT run-state (R1-S9).** Phase *outputs* — `parsed_plan`, `complexity`, `route`,
`emit_result`, `translation_quality`, `rounds_completed` — stay as explicit returns / a separate results
shape and remain `_finalize_success`'s params. Do **not** fold them into `_IngestionRun` or it becomes
the god-object this refactor is dissolving.

Then each pipeline stage becomes `_run_<phase>(self, run, …) -> WorkflowResult | None` (non-None =
"early-exit — propagate it"). `_execute` constructs the `run`, calls stages in order, returns on the
first non-None.

> **"Introduce a parameter object"** — a *real* structural change (not a byte-move), so
> behavior-preservation is not automatic. The `-> WorkflowResult | None` sentinel ("None means
> continue; no `check_cost`/`fail` result is ever dropped"), the `nonlocal current_step` increment, AND
> the per-shape span-close ordering (§5 Stage 4 / R1-S3) must be preserved exactly.

## 5. Staged plan (ascending risk — each stage its own commit, tests between)

**Stage 0 — Characterization safety net.** Before touching `_execute`, confirm which of its paths the
suite actually covers (cost-cap early-exit, `_fail` forensics write, degenerate-parse, low-quality
ASSESS, refine spend-gate). Add characterization tests for any uncovered early-exit path. *Rationale:
the suite stayed green through vacuous patches in the last refactor — coverage has gaps, and this
decomposition changes control flow, so the safety net must exist first.*

**Stage 1 — Extract the finalization block. ✅ DONE (commit `7c347ce8`).** `_finalize_success` extracted
(`_execute` 1,176 → 1,059); golden green; 18-param signature is the deliberate Fowler intermediate.

**Stage 2 — Introduce `_IngestionRun` (data bag) + move the 3 stateful closures to workflow methods
(medium).** Define the dataclass (§4); convert `_check_cost`/`_save_state`/`_fail` to `_rt_check_cost`/
`_rt_save_state`/`_rt_fail` **methods on the workflow** (they keep `self.metadata`/`_tracer`); `progress`
becomes `run.progress`. Rewrite the call sites (grep: `_check_cost(` ~4 deferred + `_fail(` = 11 direct;
`progress(` / `_save_state(`). No block extraction yet. Preserve early-exit + `current_step` semantics.
- **ENTRY PRECONDITION (R1-S6):** before Stage 2, add a **forced-`_fail` forensics characterization
  test** (trip a quality gate or `max_cost_usd=0`, deterministic, zero-LLM) that byte-compares
  `plan-ingestion-failure-forensics.json`. The Stage-0 golden covers only the *success* path; the
  `_fail`/forensics path — exactly what Stage 2/4 rethread — is currently unexercised. This gate is
  mandatory, not optional.

**Stage 3 — Extract the setup block (medium). Two OTel behavior-preservation traps (R1-S4/S5):**
setup (config/aliases/kaizen/Mottainai/capability-propagation) → `_build_run(self, …) -> _IngestionRun`.
- **R1-S5:** the capability-validation `_fail` fires **before** the root span opens and **outside** the
  `try` — that path emits **no** root span today. `_build_run` must **not** hoist root-span construction
  ahead of it (would newly emit a span — a telemetry regression the golden won't catch).
- **R1-S4:** every `_fail` early-exit closes the root span with **UNSET** status via the outer `finally`
  `__exit__(None,None,None)`; only the `except` handler sets ERROR. A context-manager rewrite must
  **not** set error status on the `_fail` path. Keep the root-span open/close in `_execute` (not in
  `_build_run`) unless a context manager provably reproduces both behaviors.

**Stage 4 — Extract per-phase orchestration wrappers (medium, iterative). SPAN-LIFECYCLE CONSTRAINT
(R1-S3, critical):** `_execute` has **two early-exit shapes** — deferred cost-cap (`cost_err =
_check_cost(x)` → close phase span → `if cost_err: return`, ×4) vs. **11 direct `return _fail(...)`**
that leave the phase span open for the outer `finally`. Therefore each `_run_<phase>(self, run, …) ->
WorkflowResult | None` **must own its phase-span lifecycle** (context manager / its own `finally`) — you
cannot pull a glue block into a method while leaving span open/close in `_execute`, or the span leaks on
the mid-phase `_fail` path. Cut order: DISCOVER/PREFLIGHT/MANIFEST → PARSE (acyclicity + degenerate) →
ASSESS → TRANSFORM → **REFINE last**.
- **REFINE ordering (R1-S7):** the REFINE tail runs `total_cost += refine_cost` → zero-round guard
  clears `review_output` → **kaizen `persist_prompt_response` (FILE WRITES)** → `design_snapshot` →
  `check_cost("refine")` → span close → deferred return. The kaizen file-writes happen **before** the
  cost-cap return today (so they occur even on a refine cost-trip). `_run_refine` must preserve that
  order — a naive "check cost first" drops those artifacts (Mottainai loss + non-byte-identical output).

**Target:** `_execute` → ~150–200 lines (construct-run + ordered stage calls + return).

## 6. Verification (every stage)

```bash
# fresh branch off origin/main; pin PYTHONPATH to THIS worktree (multi-worktree hazard)
PYTHONPATH=src python3 -m pytest tests/unit/test_plan_ingestion_workflow.py \
  tests/unit/contractors -k "plan_ingestion or ingestion or preflight or refine" -q
PYTHONPATH=src python3 -m pytest tests/unit/contractors -q   # affected-surface before merge
```
- **Baseline the pre-existing failures first** (`test_plan_ingestion_workflow.py` `ContextContract`
  drift) on the branch point, so "no NEW failures vs. parent" is the bar (not "full green").
- **Behavior-preservation gate:** the JSON artifacts `_execute` writes (`plan_ingestion_state.json`,
  traceability report, seed) must be **byte-identical** (modulo path/timestamp normalization) for a
  fixed input before/after each stage. **Success path: ✅ done** — `test_plan_ingestion_golden.py`
  (Stage 0). **Failure path: REQUIRED before Stage 2 (R1-S6)** — a forced-`_fail` test byte-comparing
  `plan-ingestion-failure-forensics.json`, since that path is not yet exercised and is exactly what
  Stage 2/4 rethread.
- **Span characterization (R1-S3/S4/S5):** assert exactly one `ingestion.<phase>` span closes per phase
  on both the success and mid-phase-`_fail` paths; assert the root span status stays UNSET on `_fail`
  (only ERROR in the `except`); assert the capability-error path emits **zero** root spans.

## 7. Risk assessment & recommendation

**This is harder than `context_seed`.** That was byte-exact class moves (behavior structurally
guaranteed). This threads a mutable state bag and rewrites early-exit closures into methods — a real
refactor where a dropped `nonlocal` increment or a swallowed early-exit is a silent behavior change on
a **hot, cost-incurring path** (plan ingestion spends LLM budget; a broken cost-cap is a real bug).

**Recommendation:** do **Stage 0 → 1 → 2** as the high-value, bounded first PR (safety net + finalization
extraction + context object). That alone makes `_execute` materially more legible and de-risks the rest.
Treat **Stages 3–4** as a second PR, and consider a **CRP / reflective-requirements pass** before Stage 4
(the OTel-span lifecycle and REFINE guards are the parts most likely to hide a behavior-preservation
trap). Do not attempt all four stages in one sitting.

## 8. Non-goals

- Not changing any phase *logic* (`_phase_*` methods untouched), routing, cost accounting, or artifacts.
- Not decomposing the other large methods in this file (`_derive_tasks_from_features` 360,
  `_extend_inventory_with_ingestion` 163, `metadata` 214) — separate, lower priority.
- Not touching the pre-existing `ContextContract` test failures (unrelated; triage separately).
- Not merging via the shared working tree — land via worktree-off-`origin/main` + FF-push.
- **Not folding phase *results* into `_IngestionRun` (R1-S9).** The context object carries only
  cross-phase mutable run-state; `parsed_plan`/`complexity`/`route`/`emit_result`/`translation_quality`/
  `rounds_completed` are outputs and stay as explicit returns / `_finalize_success` params. Collapsing
  them recreates the god-object being dissolved.

---

*Plan v1.1 — post-CRP R1 (all 9 suggestions applied; see Appendix A) + Stage-1 re-anchor. The CRP,
grounded in the live method, corrected the run-context design (methods on the workflow, not the
dataclass), added the two-shape span-lifecycle constraint, the OTel telemetry-preservation traps, the
forced-`_fail` Stage-2 precondition, and the REFINE file-write ordering. Ready to begin Stage 2.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | Re-anchor stale line numbers post-Stage-1 | CRP R1 | ACCEPTED — §1 rewritten to symbolic anchors ("grep, don't trust L-numbers"); noted `_finalize_success` done + `_execute` ~1,059. | 2026-07-04 |
| R1-S2 | check_cost/fail/save_state must be workflow methods, not dataclass methods | CRP R1 | ACCEPTED (critical) — verified: `_save_state` uses `state_dir` (L4130), `_fail` uses `self.metadata.workflow_id`. §4 rewritten: `_IngestionRun`=data bag (+`state_dir`); `_rt_check_cost/_rt_save_state/_rt_fail` on the workflow. | 2026-07-04 |
| R1-S3 | Each _run_<phase> must own its phase-span lifecycle | CRP R1 | ACCEPTED (critical) — verified two shapes: deferred cost-cap (close span then return, ×4) vs 11 direct `return _fail` (span left open). Added as §5 Stage-4 constraint. | 2026-07-04 |
| R1-S4 | _fail closes root span UNSET (only except sets ERROR) — don't change | CRP R1 | ACCEPTED — §5 Stage 3 telemetry-preservation note + §6 span characterization. | 2026-07-04 |
| R1-S5 | Cap-validation _fail fires before root span opens → no root span today | CRP R1 | ACCEPTED — §1 region table + §5 Stage 3 note: `_build_run` must not hoist root-span construction. | 2026-07-04 |
| R1-S6 | Forced-_fail forensics test as a Stage-2 PRECONDITION | CRP R1 | ACCEPTED (critical) — golden only covers success; §5 Stage 2 entry gate + §6 made it mandatory. | 2026-07-04 |
| R1-S7 | REFINE kaizen file-write must precede the cost gate | CRP R1 | ACCEPTED — §5 Stage 4 REFINE ordering note (Mottainai loss if reordered). | 2026-07-04 |
| R1-S8 | state/forensics are shared-mutable by-reference; never deepcopy | CRP R1 | ACCEPTED — §4 note (pass by reference; forensics mutated in-place). | 2026-07-04 |
| R1-S9 | Results stay separate from run-context (don't fold into the bag) | CRP R1 | ACCEPTED — §4 "results are not run-state" + §8 non-goal. | 2026-07-04 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8[1m] — 2026-07-04

- **Reviewer**: claude-opus-4-8[1m]
- **Date**: 2026-07-04 23:05:00 UTC
- **Scope**: Plan-only CRP of Stages 2–4 (behavior-preservation traps), grounded in the live
  `plan_ingestion_workflow.py` (`_execute` = L3977–5036; `_finalize_success` already at L3812–3975).

##### Focus-ask answers

**Ask 1 — Is `_IngestionRun` the right design, and is the staging order correct?**
- **Summary answer:** Partial — the parameter-object is right, but "closures → methods on the dataclass" is the wrong shape; and the dataclass as drafted omits fields the methods need.
- **Rationale:** `fail()` calls `WorkflowResult.from_error(self.metadata.workflow_id, …)` (L4182) and `save_state()` uses module-level `_tracer` (L4136) and `state_dir` (L4130). If these become methods on `_IngestionRun`, they lose `self.metadata`; the §4 dataclass lists neither `workflow_id` nor `state_dir`. `_tracer` is module-scoped (L80/83) so it survives, but `metadata` does not. Staging order is sound (context object before block-extraction), and §7's "Stage 0→1→2 as PR-1" is the right bounded cut.
- **Assumptions / conditions:** `_tracer` remains module-level; `state` and `IngestionState` are unchanged.
- **Suggested improvements:** See R1-S2. Make `check_cost/fail/save_state` methods **on the workflow** that take `run` (they keep `self.metadata`, `_tracer`), and let `_IngestionRun` be a pure data bag (`state, steps, output_dir, plan_path, forensics, state_dir, total_steps, current_step, on_progress, warn/max_cost`). Only `progress()` (pure counter+callback) is safe as a run method.

**Ask 2 — Early-exit semantics contract.**
- **Summary answer:** The contract is subtler than §4 states: there are **two** early-exit shapes, and they close spans differently.
- **Rationale:** (a) Deferred cost-cap sites — `cost_err = _check_cost(x)` then close the phase span with `__exit__(None,None,None)` then `if cost_err: return cost_err` — appear 4× (L4489–4502, 4636–4650, 4713–4721, 4912–4922). (b) Direct `return _fail(...)` sites (L4254, 4260, 4362, 4463, 4564, 4615, 4654, 4710, plus 5032) return **without** closing the open phase span, relying on the single outer `finally` (L5034–5035). `_check_cost` also calls `_fail` internally (L4123), so `save_state` + forensics-write happen inside the still-open phase span in case (a). Any conversion must preserve "no `_check_cost` result is ever dropped, and `None` means continue" AND the span-close ordering per shape.
- **Assumptions / conditions:** none.
- **Suggested improvements:** See R1-S3. Codify the `-> WorkflowResult | None` sentinel and the per-shape span-close rule as a Stage-4 constraint.

**Ask 3 — OTel root-span lifecycle across the extraction boundary.**
- **Summary answer:** Yes, moving span construction risks two concrete regressions.
- **Rationale:** (1) The root span opens at **L4191**, *after* the deferred capability-validation `_fail` at L4187–4188, which is **outside** the `try` (L4198) — that failure path emits **no** root span today. If Stage 3's `_build_run` opens the root span, the cap-error path would newly emit one (telemetry change). (2) The root span only gets ERROR status in the `except` handler (L5028–5030); every `_fail` early-exit closes it via the `finally` `__exit__(None,None,None)` (L5036) with **unset** status. A context-manager rewrite that sets error status on `_fail` changes emitted telemetry.
- **Assumptions / conditions:** behavior-preservation includes emitted span status/attributes (per §6 "byte-identical artifacts" spirit).
- **Suggested improvements:** See R1-S4, R1-S5.

**Ask 4 — REFINE guard ordering.**
- **Summary answer:** Yes — one guard has a file-writing side effect that must precede the cost gate.
- **Rationale:** The REFINE tail runs in a fixed order: `state.total_cost += refine_cost` (L4872) → zero-round guard clears `review_output` (L4878–4885) → **kaizen `persist_prompt_response(...)` writes files** (L4888–4898) → `design_snapshot` (L4901–4910) → `cost_err = _check_cost("refine")` (L4912) → span close (L4918) → `if cost_err: return` (L4921). Because `_check_cost` sees the *already-added* refine cost, a refine cost-cap trip is possible; the kaizen file-writes happen **before** that return today, so they occur even on the trip. A naive `_run_refine` that checks cost earlier would drop those artifacts (Mottainai loss).
- **Assumptions / conditions:** none.
- **Suggested improvements:** See R1-S7.

**Ask 5 — Is the safety net sufficient for Stages 2–4?**
- **Summary answer:** No — the `_fail`/forensics path is uncharacterized; add a forced-`_fail` test as a Stage-2 precondition.
- **Rationale:** `test_plan_ingestion_golden.py` has only `test_v01_run_is_deterministic_and_zero_llm` and `test_v01_artifacts_match_golden` (success, zero-LLM). `plan-ingestion-failure-forensics.json` is written **only** by `_fail` (L4170) and accumulates `_forensics["parse"|"parsed_plan"|"translation_quality"|"complexity"|"route"|"quality_gate"]` (L4426–4600) — exactly the state Stage 2/4 rethreads. §6 mentions a golden JSON test "if one doesn't exist" but does not gate it as a Stage-2 entry criterion.
- **Assumptions / conditions:** a gate-`_fail` (e.g. quality-gate or a forced `max_cost_usd=0`) is reachable deterministically without LLM spend.
- **Suggested improvements:** See R1-S6.

**Ask 6 — Accidental complexity preserved/introduced.**
- **Summary answer:** `progress`/`forensics` aliasing is safe; but folding `_finalize_success`'s 18 params into the run-bag would be new accidental complexity — results should stay separate from run-context.
- **Rationale:** `nonlocal current_step` → `self.current_step += 1` on a mutable dataclass is fine; `_forensics` mutated in-place at 6 sites is a deliberately shared dict (safe if never defensively copied). But `_finalize_success` (L3812–3834) takes phase **results** (`parsed_plan, complexity, route, emit_result, translation_quality, rounds_completed`) that are *not* cross-phase mutable state — they are outputs. Collapsing them into `_IngestionRun` would make the bag a god-object.
- **Assumptions / conditions:** none.
- **Suggested improvements:** See R1-S2, R1-S8, R1-S9.

##### Executive summary

- The plan's **line numbers are stale post-Stage-1**: §1 says `_execute` = L3812–4987/1,176 lines; live code has `_finalize_success` at L3812–3975 and `_execute` at L3977–5036 (~1,059 lines); the root span is L4191 (§5 cites L4025). Stage 3/4 targets will mislead.
- **Two early-exit shapes** close the phase span differently; Stage 4 cannot pull glue into `_run_<phase>` while leaving span open/close in `_execute` (R1-S3).
- **`_IngestionRun` methods need workflow identity** (`self.metadata`) that the dataclass can't provide — put them on the workflow (R1-S2).
- **Two OTel behavior-preservation traps** in Stage 3: cap-error path emits no root span; `_fail` never sets ERROR status (R1-S4, R1-S5).
- **Safety net gap:** no forced-`_fail`/forensics characterization test; make it a Stage-2 precondition (R1-S6).
- **REFINE kaizen file-write must precede the cost gate** (R1-S7).

##### Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Risks | high | Re-anchor all line references to symbolic anchors. §1 table, §5 stages, and §3 closure `@L` cite pre-Stage-1 numbers: `_finalize_success` now occupies L3812–3975 (Stage 1 done), `_execute` is L3977–5036 (~1,059 lines not 1,176), root span opens L4191 (§5 says L4025), setup block is ~L3983–4196. | An implementer following stale L-numbers for Stage 3 ("extract L3812–3940 setup") would extract *into the already-extracted finalize method* and miss the real setup/span boundary. | §1 region table + §5 Stage 3/4 line refs | Grep the cited anchors (`def _finalize_success`, `_root_span_ctx =`, `# --- PREFLIGHT ---`) resolve to the numbers in the plan. |
| R1-S2 | Architecture | critical | Put `check_cost`/`fail`/`save_state` on the **workflow** (taking `run`), not on `_IngestionRun`; keep the dataclass a pure data bag and add missing fields (`state_dir`; `workflow_id` if any run-method needs it). | `fail()` needs `self.metadata.workflow_id` (L4182) and `save_state()` needs `state_dir` (L4130) + module `_tracer` (L4136); the §4 dataclass carries neither `metadata` nor `state_dir`, so the drafted "closures→dataclass methods" cannot compile as-is. | §4 dataclass + the "closures → methods" bullets | Unit test: constructing `_IngestionRun` requires no workflow handle; `self._fail_via_run(run, msg)` produces a `WorkflowResult` with the correct `workflow_id`. |
| R1-S3 | Risks | critical | Add a Stage-4 constraint: each `_run_<phase>(run) -> WorkflowResult \| None` must **own its phase-span lifecycle** (context manager / its own `finally`). Do not leave phase-span open/close in `_execute` while pulling the glue block into a method. | Today direct `return _fail(...)` sites (L4254/4362/4463/4564/4615/4654/4710) leave the phase span open and rely on the single outer `finally` (L5034); the 4 deferred cost sites close it first (L4489–4502…4912–4922). A method that does `return _fail` mid-body would leak the span unless it closes its own. | §5 Stage 4 (add a "span lifecycle" sub-bullet) | Characterization test asserting exactly one `ingestion.<phase>` span is closed per phase on both the success and the mid-phase `_fail` paths. |
| R1-S4 | Ops | high | Preserve that `_fail` early-exit closes the root span with **unset** status (only the `except` handler sets ERROR). Forbid Stage 3 from setting error status on the `_fail` path. | Root ERROR status is set only at L5028–5030 (exception path); cost-cap/gate `_fail` closes via `finally __exit__(None,None,None)` (L5036). A context-manager "cleanup" that records error on `_fail` changes emitted telemetry, violating behavior-preservation. | §5 Stage 3 ("trickiest bit" bullet) | Characterization: force a gate `_fail`, assert exported root span status == UNSET/OK (not ERROR) before and after Stage 3. |
| R1-S5 | Ops | high | Note that the capability-validation `_fail` (L4187–4188) fires **before** the root span opens (L4191) and outside the `try` — this path emits **no** root span today. Stage 3's `_build_run` must not hoist root-span construction ahead of it. | Moving span-open into setup extraction would make the cap-error path newly emit a root span (a telemetry regression a golden-artifact test would not catch, since it writes no forensics file either). | §5 Stage 3 | Test: run with a contract that trips `_cap_validation_error`; assert zero `workflow.plan-ingestion` spans exported. |
| R1-S6 | Validation | critical | Make a **forced-`_fail` forensics characterization test** an explicit Stage-2 **precondition** (not just a §6 "if one doesn't exist" aside). | The golden covers only the zero-LLM success path (`test_plan_ingestion_golden.py`); `plan-ingestion-failure-forensics.json` (written only by `_fail`, accumulating `_forensics` L4426–4600) is exactly what Stage 2/4 rethread and is currently unexercised. | §5 Stage 0/2 (add as Stage-2 entry gate) + §6 | Add a test that trips a quality gate (or `max_cost_usd=0`) and byte-compares the forensics JSON before/after each stage. |
| R1-S7 | Risks | high | Document the required REFINE ordering as a Stage-4 note: `total_cost += refine_cost` → zero-round guard clears `review_output` → **kaizen `persist_prompt_response` (file writes)** → `design_snapshot` → `check_cost("refine")` → span close → deferred return. | The kaizen persist (L4888–4898) has a filesystem side effect that today runs even when the refine cost-cap trips (return is deferred to L4921). A naive `_run_refine` checking cost first would drop those artifacts (Mottainai loss + non-byte-identical output). | §5 Stage 4 (REFINE bullet) | Test: refine cost exceeds `max_cost_usd`; assert `refine_round*` kaizen files still written before the early return. |
| R1-S8 | Architecture | medium | State explicitly in §3/§4 that `state` and `forensics` are **shared-mutable by design** and must be passed by reference (never defensively copied) into `_run_<phase>`; and that `_forensics` is mutated in-place at 6 sites (L4426–4600). | Prevents a well-meaning implementer from `copy.deepcopy`-ing the run bag per phase (breaking cross-phase forensics accumulation) while chasing the "aliasing" worry ask 6 raises. | §3 closures table / §4 note | Test: after a mid-pipeline `_fail`, forensics JSON contains keys from *all* phases that ran (parse+assess+…), proving the shared dict accumulated. |
| R1-S9 | Data | medium | Add a non-goal / design note: `_IngestionRun` carries only cross-phase **mutable run-state**; phase **results** (`parsed_plan, complexity, route, emit_result, translation_quality, rounds_completed`) stay as explicit returns / a separate results shape — do **not** collapse `_finalize_success`'s 18 params into the run bag. | `_finalize_success` (L3812–3834) takes outputs, not shared state; folding them into the context object recreates the god-object the refactor is dissolving (answers ask 6). | §4 (add a "results vs run-context" bullet) + §8 non-goals | Review check: `_IngestionRun` field list contains no phase-output-only fields; `_finalize_success` keeps taking results as params. |

