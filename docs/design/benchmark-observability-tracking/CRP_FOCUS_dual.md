# CRP Focus — Where we need reviewer input most

This is a **requirements-only** review of a tracking capability that layers ContextCore's two
observability paradigms onto the Summer 2026 Model Benchmark project. The machinery mostly exists
in the SDK + ContextCore; the requirements are about *wiring and linkage*. Weight these:

1. **Feasibility vs. §0 Planning Insights.** §0 records code-level findings (hardcoded `todo`
   status, 3-of-9 insight types, missing `evidence/audience/supersedes`, no cost→task OTel label,
   `STARTD8_EMIT_MODE`, prose-only redaction, latent `emit_question` bug). Are any of these
   findings load-bearing in a way the requirements still under- or over-specify? Is FR-27/FR-28
   the right minimal change, or does it invite scope creep into the bridge?

2. **Business vs AI Agent Observability separation.** Sections A/B (tasks-as-spans) vs Section C
   (insights-as-spans) are kept distinct, joined only on `project_id`/`run_id`. Is the boundary
   clean, or are there places where a "task" is really an "insight" (or vice versa)? Is the
   execution-cell-as-task model (FR-7/8) sound, or does mapping a 9-state cell machine onto a
   7-value `task.status` enum lose information that matters?

3. **Cost→task linkage (FR-17/18).** FR-17 threads identity via `tags`/`metadata` (no schema
   change); FR-18 makes token/cost visible on the agent view only by explicit wiring. Is "no
   schema change" actually safe at ~450 cells (tag cardinality, label explosion)? Is FR-18
   correctly scoped as optional enrichment rather than core?

4. **Redaction (FR-19).** Reuse `redact()` and wire it into span-attribute / insight-evidence
   serialization. Is "wire the existing util in" sufficient, or does emission have paths that
   bypass it (e.g. raw exception messages in `fail_task(reason=...)`, evidence refs with absolute
   paths)? Should redaction be a fail-closed gate or best-effort?

5. **Non-blocking guarantee (FR-25).** Tracking must never fail or slow a benchmark cell. Does the
   live-update model (Section B) risk coupling to the run loop? Should OQ-7 (live vs post-hoc) be
   *decided* in the requirements rather than left open, given FR-25?

6. **Open questions OQ-2 (cell granularity), OQ-4 (backfill), OQ-7 (live vs post-hoc).** Each has
   a "Lean:" default. Are the leans right? Flag any that should be promoted to a firm requirement.
