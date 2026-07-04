## Focus: behavior-preservation traps in the `_execute` decomposition plan

This is a **plan-only** CRP for `PLAN.md` (decomposing `PlanIngestionWorkflow._execute`, a 1,176-line
god-method on a hot, LLM-cost-incurring path). Stage 0 (golden-artifact safety net) and Stage 1
(`_finalize_success` extraction) are **already implemented and green** — do NOT relitigate them. The
review must pressure-test the *remaining* plan (Stages 2–4), grounded in the actual code at
`src/startd8/workflows/builtin/plan_ingestion_workflow.py`.

**Primary asks (answer each: Summary / Rationale / Assumptions / Suggested improvements):**

1. **Is the run-context object (`_IngestionRun`, §4) the right design, and is the staging order
   correct?** Stage 1 revealed `_finalize_success` needed an 18-param signature — evidence the pipeline
   accumulates heavy shared state. Should Stage 2 (context object) come *before* any more extraction? Is
   there a simpler shape than a mutable dataclass carrying the 4 closures-as-methods?

2. **The early-exit semantics are the core risk.** `_check_cost` and `_fail` return a `WorkflowResult`
   that short-circuits the pipeline; the plan converts them to `run.check_cost()/fail()` methods.
   Verify against the code: are there call sites where the early-exit return value is used inconsistently
   (ignored, re-wrapped, or where a `None` vs `WorkflowResult` sentinel could be mis-handled after the
   conversion)? What is the exact contract that must be preserved?

3. **The OTel root-span manual lifecycle (the plan calls it "the trickiest bit").** `_execute` manages
   `root_span` / `_root_span_ctx` / `_active_phase_ctx` with a manual `try/except/finally` (the finally
   at the end calls `__exit__`). Stage 3 extracts setup. Does moving span construction out of `_execute`
   risk breaking the finally-cleanup or the exception→`record_exception`→`_fail` path? How should the
   span lifecycle cross the extraction boundary safely?

4. **REFINE guards (the plan's other named trap).** The REFINE block has a spend gate, a zero-round
   guard, kaizen capture, and a design snapshot. When REFINE becomes `_run_refine(run, …)` (Stage 4),
   which of these guards have subtle ordering/state dependencies (e.g. the "0 rounds but cost $0.05"
   warning that clears review_output) that a naive extraction could reorder or drop?

5. **Is the safety net actually sufficient for Stages 2–4?** Stage 0's golden covers the deterministic
   *success* path (zero-LLM v0.1 plan). But Stages 2–4 touch the cost-cap early-exit and `_fail`
   forensics paths, which the golden does NOT exercise. Does the plan need additional characterization
   tests (cost-cap trip, forced `_fail`) as an explicit Stage-2 precondition?

6. **Any accidental complexity the plan preserves or introduces?** e.g. does threading a mutable
   context object risk hidden aliasing bugs; are the 4 nested closures actually all needed as methods,
   or could some become pure functions; is `_finalize_success`'s 18-param signature the right thing to
   collapse or a sign the results should be a separate object from the run-context?

**Settled / do NOT relitigate:**
- Behavior-preserving boundary: no change to phase *logic* (`_phase_*` methods), routing, cost
  accounting, or emitted artifacts. Pure structural decomposition.
- Stage 0 (golden test) and Stage 1 (`_finalize_success`) are done and verified — review the *plan* for
  2–4, not those.
- The coverage-tooling segfault under Python 3.14 is an environment issue, not in scope.
- Landing via worktree-off-`origin/main` + FF-push is the merge method (not under review).
