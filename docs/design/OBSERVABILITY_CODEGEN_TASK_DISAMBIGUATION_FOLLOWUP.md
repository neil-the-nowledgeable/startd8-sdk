# Follow-up: codegen `task.*` → `codegen.task.*` attribute disambiguation

**Status:** Deferred (dedicated follow-up; split out of cat-4 Phase 0.1)
**Origin:** cat-4 (Project Observability) PRO-008 / R1-F2 / R2-F6 (reverse-dep I3)
**Why deferred:** Implementation revealed the rename is far larger and subtler than the
cat-4 plan assumed (it framed Phase 0.1 as a contained 3-file rename). The real surface
is **39 distinct `task.*` attributes, 98 occurrences across 9 files**, mostly raw string
literals (the `AttributeKeys.TASK_*` constants are barely used — 5 refs). cat-4 proceeds
with project-span declaration + cede (option 2); this disambiguation is option 1.

## The actual problem

`task.*` is **already a mixed namespace** carrying BOTH codegen-chunk and work-item
concepts, so a blind `task.* → codegen.task.*` sweep would mislabel work-item attributes
as codegen. Each of the 39 must be classified:

### Classify → `codegen.task.*` (genuine code-generation chunk telemetry)
`task.complexity_tier`, `task.blast_radius`, `task.caller_count`,
`task.has_dynamic_dispatch`, `task.lane_index`, `task.lane_peer_count`,
`task.lane_prior_designs_count`, `task.lane_prior_designs_truncated`,
`task.shared_file_count`, `task.truncation_blocked`, `task.attempts`,
`task.estimated_loc`, `task.target_files`, `task.prompt`, `task.prompt_version`,
`task.framework`, `task.language`, `task.integration_status`, `task.success`,
`task.context`, `task.file`, `task.phase`, `task.cost`

### Keep `task.*` (ContextCore/SpanState work-item canonical — DO NOT rename)
`task.story_points`, `task.assignee`, `task.labels`, `task.depends_on`,
`task.parent_id`, `task.created`, `task.priority`, `task.type`, `task.status`,
`task.url`, `task.description`, `task.description_preview`, `task.feature_id`,
`task.title`, `task.id`, `task.domain`

> The split above is a **first-pass proposal** — each attribute MUST be verified against
> its actual emission context before renaming (some `task.id`/`task.title`/`task.status`
> sites are codegen-chunk spans, others are work-item; the classification may be
> per-**site**, not per-**attribute name**). This is the real work.

## Files in scope (9)
`contractors/edit_first_gate.py`, `contractors/forensic_log.py`,
`contractors/context_seed/design_support.py`, `contractors/context_seed/phases/design.py`,
`contractors/development.py`, `contractors/artisan_phases/runner.py`,
`contractors/artisan_contractor.py`, `otel_conventions.py` (`AttributeKeys.TASK_*`), and
one more surfaced by `grep -rlnE '"task\.[a-z_]+"' src/startd8`.

## Approach when picked up
1. Per-site audit: for each `task.*` emission, decide codegen-chunk vs work-item by the
   span it's on (codegen orchestration span → `codegen.task.*`; ContextCore/state-file
   work-item → keep `task.*`).
2. Prefer routing renamed attrs through `AttributeKeys.CODEGEN_TASK_*` constants (kill the
   raw-string sprawl while we're here).
3. Update the declared span descriptors (cat-4) to use the renamed attrs.
4. Re-enroll project spans in SHARED-002 parity with the disambiguated attribute sets so
   the subset check no longer encodes the `task.status` polysemy (R2-F6 / I3 satisfied).
5. Verify no ContextCore work-item consumer reads a now-renamed codegen attr.

## Until then (cat-4 option 2 state)
Project spans are declared with their **current** `task.*` attributes; SHARED-002 parity
checks span name-patterns (tolerant of the un-disambiguated attribute sets). The reverse-
dependency I3 ("rename before parity enrollment") is **explicitly relaxed** for this pass
and re-asserted when this follow-up lands.
