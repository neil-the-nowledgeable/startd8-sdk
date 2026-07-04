# Decompose `PlanIngestionWorkflow._execute` — Implementation Plan

**Version:** 1.0
**Date:** 2026-07-04
**Branch:** `refactor/plan-ingestion-execute` (off `origin/main` `faef9d1f`)
**Type:** Behavior-preserving decomposition of a god-method
**Precedent:** the `context_seed` phases/ refactor (`docs/design/context-seed-refactor/`) — same
family of work, but this one is **higher-coupling** (see §4).

---

## 1. Problem & the reframe from investigation

`workflows/builtin/plan_ingestion_workflow.py` is 4,987 lines; its last method,
`_execute` (**L3812–4987, 1,176 lines**), runs to EOF and is the #1 remaining active god-method.

**But investigation (2026-07-04) reframed the target.** The phase *logic* is **already extracted**
into dedicated methods — `_phase_parse` (115), `_phase_assess` (133), `_phase_transform` (127),
`_phase_refine` (84), `_phase_emit` (64). `_execute` does **not** inline phase logic. Its 1,176 lines
are three things:

| Region | Lines | ~LOC | What it is |
|---|---|---|---|
| **Setup** | 3812–4040 | ~230 | typed config + local aliases, kaizen-config discovery, Mottainai onboarding load, capability propagation (Layer 5), OTel root span, and **4 nested closures** |
| **Phase pipeline** | 4041–4835 | ~795 | orchestration *glue* around each `_phase_*` call: DISCOVER → PREFLIGHT → MANIFEST → PARSE (+acyclicity gate, degenerate-parse handling) → ASSESS (+low-quality handling) → TRANSFORM → REFINE (+spend gate, guards, kaizen capture, snapshot) → EMIT (+traceability) → DONE |
| **Finalization** | 4841–4987 | ~145 | kaizen diagnostic report, quality signals, seed-quality read-back, honest top-level signal, provenance, OTel finalize, build success `WorkflowResult` |

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

## 4. Core design decision — a run-context object

Promote the captured locals + the 4 closures into an explicit **run-context** that phase-orchestration
methods receive, so the closures become methods and the glue becomes callable:

```python
@dataclass
class _IngestionRun:            # one per _execute() invocation
    state: IngestionState
    steps: list
    output_dir: Path
    plan_path: Path
    forensics: dict             # the _forensics ledger
    total_steps: int
    current_step: int = 0
    on_progress: Callable | None = None
    warn_cost_usd: float | None = None
    max_cost_usd: float | None = None
    # closures → methods:
    def progress(self, msg): ...
    def check_cost(self, label) -> WorkflowResult | None: ...   # early-exit signal
    def save_state(self): ...
    def fail(self, msg) -> WorkflowResult: ...
```

Then each pipeline stage becomes `_run_<phase>(self, run: _IngestionRun, …) -> WorkflowResult | None`
(returning a non-None `WorkflowResult` means "early-exit — propagate it"). `_execute` becomes an
orchestrator that constructs the `run`, calls stages in order, and returns on the first non-None.

> This is the **"introduce a parameter object"** refactoring. It is a *real* structural change (unlike
> the `context_seed` byte-moves), so behavior-preservation is not automatic — the early-exit semantics
> of `check_cost`/`fail` and the `nonlocal current_step` increment must be preserved exactly.

## 5. Staged plan (ascending risk — each stage its own commit, tests between)

**Stage 0 — Characterization safety net.** Before touching `_execute`, confirm which of its paths the
suite actually covers (cost-cap early-exit, `_fail` forensics write, degenerate-parse, low-quality
ASSESS, refine spend-gate). Add characterization tests for any uncovered early-exit path. *Rationale:
the suite stayed green through vacuous patches in the last refactor — coverage has gaps, and this
decomposition changes control flow, so the safety net must exist first.*

**Stage 1 — Extract the finalization block (low risk, high value).** L4841–4987 (~145 lines) is a
cohesive end-block after all phases: build kaizen diagnostics, attach quality signals, read seed
quality, compute the honest top-level signal, record provenance, finalize the OTel span, build the
success `WorkflowResult`. It runs only on the success path and needs no early-exit closure. Extract to
`_finalize_success(self, run, parsed_plan, diagnostics, …) -> WorkflowResult`.

**Stage 2 — Introduce `_IngestionRun` + convert the 4 closures to methods (medium).** Define the
dataclass; replace the closures with methods; rewrite the ~30 call sites (`progress(...)` →
`run.progress(...)`, `_check_cost(l)` → `run.check_cost(l)`, `_fail(m)` → `run.fail(m)`). No block
extraction yet — this is the state-threading enablement. Preserve `nonlocal`/early-exit semantics
exactly; this stage is where a regression is most likely, so run the full suite + characterization
tests before committing.

**Stage 3 — Extract the setup block (medium).** L3812–~3940 (config/aliases/kaizen/Mottainai/capability
propagation) → `_build_run(self, …) -> _IngestionRun` (returns the constructed context). The OTel root
span (L4025, "manual lifecycle to avoid re-indenting 400 lines") must stay in `_execute` or be handled
with a context manager — flag this; it's the trickiest bit.

**Stage 4 — Extract per-phase orchestration wrappers (medium, iterative).** One at a time, cut each
`--- PHASE ---` glue block into `_run_<phase>(self, run, …)`, threading `run`. Order by independence:
DISCOVER/PREFLIGHT/MANIFEST first (simpler), then PARSE (has the acyclicity gate + degenerate handling),
ASSESS, TRANSFORM, then REFINE last (most guards: spend gate, zero-round guard, kaizen capture, snapshot).
Test after each. `_execute` shrinks to a readable sequence of `run_x` calls with early-exit checks.

**Target:** `_execute` from 1,176 → ~150–200 lines (a construct-run + ordered stage calls + return).

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
  `plan-ingestion-failure-forensics.json`, traceability report, seed) must be **byte-identical** for a
  fixed input before/after each stage — add a golden-file test if one doesn't exist.

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

---

*Plan v1.0 — grounded in a 2026-07-04 structural investigation of `_execute`. Ready for review, or to
begin at Stage 0.*
