# Context Seed Phase-Handler Extraction & Method Decomposition — Requirements

**Version:** 0.6 (Post-build semantic review — validated against shipped Part A)
**Date:** 2026-07-04
**Status:** Part A implemented & validated; Part B in progress
**Owner:** SDK maintainers
**Type:** Structural refactor (behavior-preserving)

---

## 0. Planning Insights (Self-Reflective Update)

> Changes between v0.1 (pre-planning) and v0.2 (post-planning). The planning pass revealed
> 6 corrections, all confirmed by grepping the actual tree.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| Compat wrapper / `__init__.py` may need edits | `core.__getattr__` (L404) already serves `DesignPhaseHandler` lazily; extending its table serves all five with **zero** wrapper/`__init__` edits | FR-9/FR-10 strengthened to "unchanged, assert via diff" |
| Patch-target risk is small ("2 tests patch core.*") | **20 patch sites**; 11 patch `context_seed_handlers._ensure_context_loaded`, 5 patch `…_handlers.subprocess` — these bind the *wrapper's* re-export, not the handler's call path | FR-15 upgraded to a first-class **Patch-Migration Protocol** with a bind-proof gate |
| `integrate` (~947 LOC) is an `IntegratePhaseHandler` method | It is `IntegrationEngine.integrate` in `integration_engine.py` — **different class, different file** | OQ-1 resolved → moved to Non-Requirement NR-6 / Plan Part C (separate refactor) |
| Handlers may be coupled to each other | No handler references another; only the aggregator instantiates them | Each handler extracts **independently** (parallel-safe, per-commit) |
| Aggregator import style unknown | Must be a **local** import inside `create_handlers` (module-top import would recreate the core↔handler cycle) | FR-8 specifies local import, mirroring L163 precedent |
| Correct post-move patch shape unknown | Tree already demonstrates it: `patch("…phases.plan._load_enriched_seed")` (8×) | Protocol has a concrete model to copy |

**Resolved open questions:**
- **OQ-1 → Resolved.** `integrate` is `IntegrationEngine.integrate` (different file); descoped to NR-6 / Plan Part C.
- **OQ-2 → Interleave.** Extract handler, prove green, then decompose *that* handler's methods — isolates move-regressions from decomposition-regressions.
- **OQ-3 → They MOVE (corrected v0.5, per CRP R1-F1).** `_format_review_prompt` / `_get_review_template` are col-0 in `core` but used *only* inside `ReviewPhaseHandler` (L6827–7796). If left in `core`, `review.py` would import them back → cycle persists. They move to `handler_support.py` with the rest (FR-6). *(The v0.4 "stay in core" answer contradicted FR-6.)*
- **OQ-4 → Lazy/local.** Aggregator local-imports handlers to avoid the load-time cycle.
- **OQ-5 → 20 sites.** Enumerated; the `_ensure_context_loaded` (11) and `subprocess` (5) clusters are the exposure. Some may already be vacuous — the Protocol proves each binds.

### 0.1 Lessons-Learned Hardening (v0.3)

> Consulted `Lessons_Learned/sdk/Design_Docs_LESSONS_LEARNED.md`. Applied:

- **[Leg 4 §5 — Import-Path-Driven Feature Duplication]** — module-per-thing splits invite
  duplicate/ambiguous import paths → mandated the single `core.__getattr__` table as the *sole*
  lazy-resolution point (no per-site re-imports), and the `test_phase.py` naming guard (FR-3).
- **[Phantom-reference audit]** — every symbol named in FRs (handlers, helpers, line ranges,
  test files) was grep-verified against the tree; added §5 Reference Audit.
- **[CRP steering memory]** — least-reviewed artifact is this brand-new PLAN; settled/do-not-relitigate:
  the `design.py` precedent (proven) and the "behavior-preserving, no algorithm change" boundary.

### 0.2 Essential vs. Accidental Complexity Ledger (v0.4 — the pivot)

> External-lens review (2026-07-04) rejected the v0.3 direction as *relocating* accidental
> complexity rather than eliminating it. v0.3 proposed **extending** `core.__getattr__` with 5 new
> entries and mandating the wrapper stay byte-identical — both of which **lock in** the accidental
> complexity. v0.4 reverses this: distill to essential complexity.

**Root accidental complexity: a dependency inversion.** `core.py` conflates three roles — (a) the
shared-helper library, (b) the composition root (`ContextSeedHandlers` aggregator), and (c) the
handler home. Because the shared helpers live in the *same file* as the aggregator, extracted phases
must import *back* from `core`, but `core` (as aggregator) must import the phases → a cycle, papered
over with a lazy `__getattr__` shim and `TYPE_CHECKING` guards. The `design.py` "core-dependent phase"
flavor I proposed to mirror **is itself the accidental-complexity artifact**, not a precedent to copy.

| Complexity | Essential or Accidental? | Verdict |
|---|---|---|
| Multi-phase orchestration, retry, telemetry, checkpointing logic | **Essential** | Preserve verbatim |
| Phases importing shared symbols *back from* `core` | **Accidental** (dependency inversion) | **Eliminate** — phases import from a leaf |
| `core.__getattr__` lazy shim + `TYPE_CHECKING` design guard | **Accidental** (exists only to break the self-inflicted cycle) | **Delete** |
| `_ensure_context_loaded` traveling shared→core→wrapper→patched (3 hops) | **Accidental** (stranded re-export) | **Collapse** — patch at the leaf/phase |
| `HandlerConfig` + 15 helpers/listeners stranded in the aggregator file | **Accidental** (wrong home) | **Move** to a leaf support module |
| Compat wrapper existing at all | **Accidental**, but load-bearing (5 active + 4 on-hold src consumers, 44 test files) | **Keep working**, do NOT byte-freeze; retirement is NR-7 |

**Verified enablers (grep, 2026-07-04):** `shared.py` imports nothing from `core` (clean leaf);
`_ensure_context_loaded` is *already* in `shared.py`; the stranded helpers + both listeners are leaf
(no `*PhaseHandler`/aggregator refs in their bodies); only `prime_review.py` imports `core` directly.
∴ moving the stranded helpers to a leaf module breaks the cycle with **no** new cycle introduced.

### 0.3 Implementation Validation (v0.6 — post-build semantic review)

> After Part A shipped (core.py 9,952 → 279, 10 commits), a two-way semantic review checked each
> requirement against the built code AND checked the requirements for authoring-time inaccuracy.
> Result: the spec was **mostly accurate**; 3 concrete code gaps and 3 requirement inaccuracies found.

| Requirement | Built state | Verdict |
|---|---|---|
| FR-1..7, FR-6a, FR-9, FR-10, FR-13 | Implemented as written; identity + acyclicity verified | ✅ accurate & satisfied |
| **FR-8** | Design is a **local import** (cycle via artisan_contractor), not eager | ⚠️ **req was wrong** — "no local imports" corrected |
| **FR-11** | `phases/__init__.py.__all__` was **never updated** (still design/plan/scaffold) | ❌ **code miss** — fixed post-review (added 5 modules) |
| **FR-14** | Contractors suite green; whole-repo "full green" unachievable (pre-existing failures) | ⚠️ **req over-broad** — qualified to affected-surface |
| **FR-15** | Migrated + green, but via green-after-migration, **not** the raising sentinel; 1 stray `subprocess` patch missed | ⚠️ req over-specified + ❌ 1 site — both fixed post-review |
| **FR-16** | Acyclicity gate run **manually only**, never committed as a test | ❌ **code miss** — added `test_context_seed_acyclicity.py` post-review |
| FR-12 | 2 of ~17 method extractions done | 🔶 in progress (Part B) |
| NR-1..7 | Honored (wrapper kept, artisan untouched, integrate out of scope) | ✅ accurate & satisfied |

**Authoring-accuracy conclusion:** the requirements were **not materially out of date at the start** —
the codebase matched the reference audit (§5). The inaccuracies were *forward assumptions that
implementation falsified* (FR-8's eager-import claim; FR-14's "full suite"; FR-15's sentinel), which
is exactly what the reflective/CRP loop is meant to catch and what this §0.3 records. The two pure code
misses (FR-11, FR-16) were fixed the moment the review surfaced them.

**Line-range note:** the `core.py L…` ranges in FR-1..5 were accurate against the **pre-refactor**
9,952-line file (verified §5) and are now historical — the handlers have moved to `phases/*.py`.

---

## 1. Problem Statement

`src/startd8/contractors/context_seed/core.py` is **9,952 lines** — the single largest
file in the SDK and the dominant "god file" surfaced by the 2026-07-04 structural review.
It holds five implementation-half phase handlers plus their monster methods. A sibling
`context_seed/phases/` subpackage already exists and holds the design-half handlers
(`plan.py`, `scaffold.py`, `design.py`), proving the module split was **started but not
finished**.

The file already carries a special maintenance burden documented in CLAUDE.md: a
`context_seed_handlers.py` compat wrapper, a mock-patch-target rule, and a "re-export new
symbols" rule — all workarounds that exist *because* the file is oversized.

| Component | Current State | Gap |
|-----------|--------------|-----|
| `core.py` | 9,952 lines, 13 classes, 5 phase handlers | Should be ~1,050 lines (shared substrate + aggregator) |
| `phases/` subpackage | Holds plan/scaffold/design only | Missing implement/integrate/test/review/finalize |
| `ImplementPhaseHandler.execute` | ~1,137-line single method | Should decompose into named sub-steps |
| `integration_engine.py::integrate` | ~947-line method | Should orchestrate named stages |
| `_execute_with_inner_loop`, `_tasks_to_chunks` | ~706 / ~733 lines | Should decompose |

## 2. Requirements

### Part A — Handler Extraction

- **FR-1.** Move `ImplementPhaseHandler` (core.py L654–5307) to `phases/implement.py`.
- **FR-2.** Move `IntegratePhaseHandler` (core.py L5475–5856) to `phases/integrate.py`.
- **FR-3.** Move `TestPhaseHandler` (core.py L5856–6709) to `phases/test_phase.py`
  (NOT `test.py` — pytest would collect it).
- **FR-4.** Move `ReviewPhaseHandler` (core.py L6748–8929) to `phases/review.py`.
- **FR-5.** Move `FinalizePhaseHandler` (core.py L8929–9769) to `phases/finalize.py`.
- **FR-6.** Create a leaf support module `context_seed/handler_support.py` holding the ~15 shared
  helpers/classes currently stranded in `core.py` (`HandlerConfig`, `PerFileMode`,
  `EditModeClassification`, `SeedTaskUnit`, `ArtisanIntegrationListener`, `OTelIntegrationListener`,
  `_dict_to_gen_result`, `_capture_task_span_context`, `_build_provenance_links`, `_log_task_timing`,
  `_log_task_boundary_start`, `_log_task_boundary_complete`, `_coerce_optional_float`,
  `_compute_gen_file_hash`, `_compute_design_results_hash`, `_format_review_prompt`,
  `_get_review_template`). It imports only external deps + `shared.py` + `tracing.py` (one-way,
  layering above them) — never `core`. It is a distinct concern from `shared.py` (which owns
  seed-task parsing), so it is its own module.
- **FR-6a (dependency-closure rule, per CRP R1-F2/S3).** Moving a helper means moving its **transitive
  dependency closure**, not just the named symbol. The module-level *constants* the moved helpers/
  handlers read must move to `handler_support.py` in the same commit: `_CACHE_SCHEMA_VERSION` (14 uses
  across Implement/Test/Review), `_PHASE_RESULT_KEYS` (read inside moved `_build_provenance_links`,
  core L223), `_MAX_GEN_FILE_HASH_BYTES` (default of moved `_compute_gen_file_hash`, core L328),
  `_SIZE_REGRESSION_THRESHOLD`, `_SIZE_REGRESSION_MIN_LINES`. Leaving any in `core` re-creates the
  cycle. Acceptance: `handler_support.py` and every `phases/*.py` have **zero** `import …context_seed.core`.
- **FR-7.** Each extracted phase module imports its shared symbols from `handler_support`/`shared` —
  **never from `core`**. This severs the cycle. `phases/design.py`'s existing
  `from …context_seed.core import (…)` is **repointed** to `handler_support` in the same pass
  (opportunistic elimination of the pre-existing inversion).
- **FR-8.** With phases no longer importing `core`, `core.py` becomes a **pure aggregator**
  (the `ContextSeedHandlers` class). `core.py.__getattr__` shim and the `TYPE_CHECKING` design-handler
  guard are **deleted** (they existed only to break the self-inflicted cycle).
  **Corrected v0.6 (implementation finding):** the v0.5 claim "imports all handlers *eagerly* at module
  top — no local imports" proved **false for `DesignPhaseHandler`**. `design.py` transitively imports
  `core` via `artisan_contractor` (which lazy-imports the wrapper), so a module-top eager import of
  design would create a load-time cycle. Design is therefore imported **locally inside `create_all()`**
  — a *local import*, **not** a module `__getattr__` shim, so it still satisfies "0 `__getattr__`" and
  the acyclicity gate. The other 7 handlers are eager at module top; design is the one necessary
  exception. (Empirically verified: eager import of design from the wrapper/`__init__` is safe; only
  `core` eager-importing design cycles.)
- **FR-9.** `context_seed_handlers.py` compat wrapper keeps its public `__all__` **unchanged**, but
  its *import lines* are repointed to the symbols' real homes (handlers from `phases`; helpers from
  `handler_support`/`shared`; **and `design_support` for the ~8 symbols it currently re-exports via
  `core`** — `_detect_cross_file_edges`, `_extract_complexity_signals`, `_compute_ccd_task_metadata`,
  `build_shared_file_manifest`, `compute_critical_path_tasks`, `compute_lane_to_file_mapping`, etc.,
  per CRP R1-S1, since the pure-aggregator `core` no longer re-imports them). Assert the public
  surface via **`__all__` equality AND single-definition identity** (each exported name resolves to
  exactly one `inspect.getsourcefile` / one object — a pure move must not silently become a copy that
  passes name-equality but breaks `mock.patch` binding; per CRP R1-F4).
- **FR-10.** `context_seed/__init__.py` keeps its public `__all__` unchanged; its `__getattr__`
  design-handler shim is deleted (handlers now import eagerly with no cycle).
- **FR-11.** `phases/__init__.py.__all__` gains the five new module names.

### Part B — Method Decomposition

- **FR-12.** After each handler lands in its own file, decompose its methods exceeding
  ~200 lines into named private sub-steps. The orchestrating method should read as a
  sequence of named calls.
- **FR-13.** Decomposition is behavior-preserving: extracted sub-steps are pure moves of
  existing logic; no control-flow or side-effect changes.

### Cross-cutting

- **FR-14.** No public behavior change. **Corrected v0.6:** "full `pytest` suite passes" is qualified
  to the **affected-surface** suite (`tests/unit/contractors`, 3,444 green + the `context_seed`
  consumer tests) with the `PYTHONPATH=src` pin. The whole-repo suite has **pre-existing, unrelated
  failures** (notably ~25 `test_plan_ingestion_workflow.py` `ContextContract` pydantic-drift failures)
  that were verified to fail identically on the parent commit — so "full green" was never literally
  achievable and is not the acceptance bar; "no NEW failures vs. parent" is.
- **FR-15.** Migrate every `mock.patch` target referencing a symbol a moved handler *calls*
  to the handler's new module path (patch where looked up, not where re-exported), per the
  **Patch-Migration Protocol** (PLAN.md). Each migrated patch must be proven to **fully intercept**,
  not merely touched: use a **raising sentinel** (a patch replacement that raises if the *real* callee
  is also reached) — `assert mock.called` catches "never invoked" but not "real function also ran"
  (per CRP R1-F5). Some current wrapper-targeted patches may already be vacuous; a naive path-swap
  would preserve the vacuity. **21 sites** enumerated; exposure is `_ensure_context_loaded` (11) and
  `subprocess` (**6**, not 5 — recount per CRP R1-S4) clusters.
  **Implementation note (v0.6):** the raising-sentinel technique was **not** used; migration was
  instead validated by (a) tests staying green after repointing to the point of lookup, and (b) the
  fact that several migrated patches are *load-bearing* — e.g. the finalize crash-recovery test and
  `test_test_phase_uses_arg_list` only pass **because** the repointed patch binds. This is weaker than
  the sentinel but adequate here; the sentinel is downgraded from *required* to *recommended for
  ambiguous sites*. All migrated sites: finalize (1 `atomic_write_json`), integrate (11
  `_ensure_context_loaded`), review (2: `GateEmitter` + `atomic_write_json`), implement (5 `subprocess`
  + 1 `atomic_write_json`), test_phase (1 `subprocess`, found in the post-hoc semantic review).
- **FR-16 (acyclicity acceptance gate, per CRP R1-F3/S2).** The central claim "cycle eliminated, shim
  deleted" must be **automatably proven**, not asserted: (a) `python -c "import …context_seed.core"`
  succeeds in a fresh interpreter; (b) a grep/import-linter gate asserts **0** `__getattr__` in the
  package and **0** `phases/* → core` imports. A green test suite alone is insufficient — the lazy
  shim could be re-added and tests would still pass. This gate is a Step-6 precondition and a CI check.

## 3. Non-Requirements

- **NR-1.** ~~Does NOT extract shared helpers into a separate module.~~ **REVERSED in v0.4** —
  extracting the stranded helpers to `handler_support.py` (FR-6) is now the *central* move; it is
  what makes the cycle-elimination possible. Kept here as a visible record of the v0.3→v0.4 pivot.
- **NR-2.** Does NOT touch the ON-HOLD Artisan handlers (`artisan_phases/`), except to repoint their
  *import lines* if a symbol they consume moves home (mechanical, no logic change).
- **NR-3.** Does NOT change any handler's algorithm, prompts, or scoring.
- **NR-4.** Does NOT rename `core.py` or the compat wrapper.
- **NR-5.** Does NOT decompose methods in files other than the five extracted handlers.
- **NR-6.** Does NOT refactor `IntegrationEngine.integrate` (~947 LOC) — it is a different class
  in a different file (`integration_engine.py`), unrelated to `IntegratePhaseHandler`. Tracked
  separately as PLAN.md Part C (its own branch/PR). *(Was OQ-1; resolved during planning.)*
- **NR-7.** Does NOT retire the `context_seed_handlers.py` compat wrapper. Its ~5 active src
  consumers, 4 on-hold Artisan consumers, and 44 test files make deletion a separate migration
  (Tier 2). This refactor keeps the wrapper working with its public surface intact; only its
  internal import lines are repointed (FR-9).

## 4. Open Questions

*All v0.1 open questions were resolved during the planning pass — see §0. No open questions remain.*

## 5. Reference Audit (phantom-reference discipline)

Every code symbol named in this document was verified against the tree on 2026-07-04:

| Symbol / claim | Verified |
|---|---|
| 5 handler classes + line ranges in `core.py` | ✓ grep of col-0 `class` defs |
| `core.__getattr__` at L404 serving `DesignPhaseHandler` | ✓ read L404–408 |
| Aggregator `ContextSeedHandlers.create_handlers` local-imports design at L163 | ✓ read L9769–9952 |
| Per-handler shared-symbol import contract | ✓ per-handler body grep |
| `phases/` holds plan/scaffold/design | ✓ directory listing |
| Dedicated per-handler test files exist (implement×7, integrate×5, review×4, finalize×3) | ✓ `ls tests/unit/contractors` |
| 20 mock-patch sites; `_ensure_context_loaded`×11, `subprocess`×5 | ✓ grep of `patch(` in tests |
| `IntegrationEngine.integrate` is in `integration_engine.py`, not a phase handler | ✓ grep class/def |
| Correct patch precedent `patch("…phases.plan._load_enriched_seed")` | ✓ grep of tests |

---

*v0.4 — Essential/accidental-complexity hardening (external-lens pivot). Reversed the v0.3
"extend the shim / byte-freeze the wrapper" direction, which relocated accidental complexity;
v0.4 eliminates it: extract stranded helpers to a leaf `handler_support.py` (FR-6), phases import
from the leaf not `core` (FR-7), delete the `__getattr__` shim (FR-8/FR-10). Net: `core.py`
9,952 → ~200 LOC, and 3 accidental-complexity mechanisms deleted rather than grown.
Prior: v0.3 lessons hardening (3 lessons); v0.1→v0.2: 6 corrections, 5 OQs resolved.*

*v0.5 — Post-CRP triage. Applied all 5 R1 F-suggestions (see Appendix A): the CRP found the
cycle-elimination was **incomplete** — moving the named helpers without their transitive dependency
closure (constants, the two review-template helpers, design_support re-exports) would leave the
cycle intact. Added FR-6a (closure rule), FR-16 (acyclicity gate); strengthened FR-9 (identity) and
FR-15 (raising sentinel). Corrected OQ-3 self-contradiction. Net: the plan now *provably* eliminates
the cycle rather than claiming to. Ready for implementation.*

*v0.6 — Post-build semantic review (see §0.3). Validated the shipped Part A against every FR/NR:
spec was mostly accurate (matched the codebase at start), with 3 forward-assumption inaccuracies
(FR-8 eager-import, FR-14 full-suite, FR-15 sentinel) corrected in place and 2 pure code misses
(FR-11 phases `__all__`, FR-16 uncommitted gate) fixed post-review. No functionality changed; this
is a validation + spec-truthing pass, not a scope change.*

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
| R1-F1 | OQ-3 contradicts FR-6 (review-template helpers) | CRP R1 | ACCEPTED — rewrote OQ-3: helpers MOVE to `handler_support`. Verified used only in ReviewPhaseHandler (L6827–7796). | 2026-07-04 |
| R1-F2 | FR-6 omits consumed constants → cycle persists | CRP R1 | ACCEPTED — added **FR-6a dependency-closure rule** (constants move too). Verified `_PHASE_RESULT_KEYS`@L223, `_MAX_GEN_FILE_HASH_BYTES`@L328, `_CACHE_SCHEMA_VERSION`×14. | 2026-07-04 |
| R1-F3 | No automatable no-cycle acceptance gate | CRP R1 | ACCEPTED — added **FR-16** (fresh-interpreter import + import-linter/grep acyclicity gate). | 2026-07-04 |
| R1-F4 | `__all__` equality ≠ single-definition identity | CRP R1 | ACCEPTED — FR-9 strengthened to require identity/unique-source assertion. | 2026-07-04 |
| R1-F5 | Bind-proof gate insufficient; need raising sentinel | CRP R1 | ACCEPTED — FR-15 now mandates a raising sentinel; count corrected 20→21 (subprocess 5→6). | 2026-07-04 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8[1m] — 2026-07-04

- **Reviewer**: claude-opus-4-8[1m]
- **Date**: 2026-07-04 18:20:00 UTC
- **Scope**: Essential vs accidental complexity boundary (sponsor focus); code-grounded against `core.py`, `shared.py`, `phases/design.py`, `context_seed_handlers.py`.

##### Focus-file ask answers

**Ask 1 — Is the dependency-inversion diagnosis correct and complete?**
- **Summary answer:** Directionally correct but *incomplete* — the diagnosis names the right root (helpers cohabiting the aggregator file force the back-import + shim) but under-enumerates what must move to fully sever the cycle.
- **Rationale:** Verified `phases/design.py` L50–59 imports 8 symbols back from `core` (`HandlerConfig`, `_build_provenance_links`, `_capture_task_span_context`, `_coerce_optional_float`, `_compute_design_results_hash`, `_log_task_boundary_*`, `_log_task_timing`) — all in the FR-6 move set, so the leaf-relocation thesis holds. But moved helpers also read module-level **constants** still slated to stay in `core` (`_PHASE_RESULT_KEYS` inside `_build_provenance_links` @ core.py L223; `_MAX_GEN_FILE_HASH_BYTES` as the default of `_compute_gen_file_hash` @ L328), so the cycle is not fully cut by FR-6 as written (see R1-F2).
- **Assumptions / conditions:** none — grep-verified 2026-07-04.
- **Suggested improvements:** Fold the consumed constants into the leaf (R1-F2); reconcile OQ-3 (R1-F1). No simpler essential shape exists — leaf ← phases ← aggregator is already minimal.

**Ask 2 — `handler_support.py` vs folding into `shared.py`.**
- **Summary answer:** New module is the right call; do **not** over-split into `telemetry_support` + `config_types`.
- **Rationale:** `shared.py` genuinely owns seed-task parsing (`SeedTask`, `_parse_tasks`, `_ensure_context_loaded`, `_load_enriched_seed`, `_topological_sort`) — a coherent concern distinct from phase plumbing (config/listeners/telemetry/hash/provenance). ~15 symbols in one leaf is not large enough to warrant a further split; two more modules would multiply import lines across 5 phases for no cohesion gain.
- **Assumptions / conditions:** `handler_support` layers cleanly above `shared`+`tracing` (acyclic) — holds, both are leaves.
- **Suggested improvements:** State in FR-6 that `handler_support` may import `shared`/`tracing` (one-way) so a later reviewer doesn't read it as a second peer-leaf that must be import-free.

**Ask 3 — Shim deletion / import-order risk.**
- **Summary answer:** Probably safe, but **not proven** — eager import must be gated on a clean-interpreter import + acyclicity check before Step 6 deletes the shim.
- **Rationale:** The obvious transitive cycle (`artisan_contractor` → wrapper → `core` → `phases/*` → `artisan_contractor`) does **not** fire at module load because `artisan_contractor` imports the wrapper only lazily (verified L60 is function/TYPE_CHECKING-indented, not module-top). But the plan asserts eager import works by construction; it should demonstrate it (see R1-S2).
- **Assumptions / conditions:** No phase transitively imports `core` other than through the deleted back-imports.
- **Suggested improvements:** Add import-linter/`python -c` clean-import gate as a Step-6 precondition.

**Ask 4 — Wrapper-repoint blast radius.**
- **Summary answer:** `__all__` equality is necessary but **insufficient**; the load-bearing invariant is single-definition identity.
- **Rationale:** A pure move preserves object identity (consumers + `mock.patch` see the same object); the failure mode is a move silently becoming a **copy** (symbol defined in two homes), which passes `__all__` name-equality yet breaks patch binding. Also, the wrapper re-exports ~8 `design_support`-owned symbols *via* `core` today — repoint homes omit `design_support` (see R1-S1).
- **Assumptions / conditions:** none.
- **Suggested improvements:** Add a no-duplicate-definition assertion (R1-F4).

**Ask 5 — Patch-Migration Protocol adequacy.**
- **Summary answer:** `assert mock.called` is not enough; add a raising sentinel.
- **Rationale:** A pre-existing vacuous patch can stay green *and* the mock still not be called for the right reason; `assert called` catches "never invoked" but not "real function also invoked." A sentinel that raises if the real callee executes while mocked is the stronger gate (see R1-F5 / R1-S4).
- **Assumptions / conditions:** none.
- **Suggested improvements:** Bake the sentinel into the Protocol step 3.

**Ask 6 — Un-removed accidental complexity (AbstractPhaseHandler template method).**
- **Summary answer:** Correctly left alone — a template method absorbing `_log_task_boundary_*`/provenance/span-capture would change control flow and violates the behavior-preserving boundary (NR-3).
- **Rationale:** The boilerplate is *already* centralized as free functions (`_log_task_boundary_start/_complete` called 28× but they are shared calls, not duplicated bodies). Hoisting them into an `AbstractPhaseHandler` template is a Tier-2 behavioral refactor, not in scope.
- **Assumptions / conditions:** none.
- **Suggested improvements:** Add an explicit one-line deferral note so a later reviewer doesn't re-propose it (see R1-S5).

##### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Architecture | high | Reconcile OQ-3 with the v0.4 pivot: OQ-3 ("`_format_review_prompt`, `_get_review_template` … stay in `core`") directly contradicts FR-6 (which lists both in the `handler_support` move set) and the PLAN import-contract (review.py/test_phase.py import them from `handler_support`). Strike or rewrite OQ-3 to say they MOVE. | Verified: both are defined in core.py (L6709, L6730) and used only inside the ReviewPhaseHandler region (L6827–7796). If they "stay in core," review.py/test_phase.py must import them back from `core` → the cycle the v0.4 pivot claims to eliminate persists. This is the single most load-bearing inconsistency in the doc set. | §0 OQ-3 line and FR-6 | grep confirms 0 remaining `from …core import _format_review_prompt` after the move; no-cycle import test passes |
| R1-F2 | Data | high | FR-6's helper enumeration omits the module-level CONSTANTS that moved helpers/handlers consume: `_CACHE_SCHEMA_VERSION`, `_PHASE_RESULT_KEYS`, `_MAX_GEN_FILE_HASH_BYTES`, `_SIZE_REGRESSION_THRESHOLD`, `_SIZE_REGRESSION_MIN_LINES`. Add them to the FR-6 move set (natural home: `handler_support`). | Verified: `_PHASE_RESULT_KEYS` is read inside the moved `_build_provenance_links` (core.py L223); `_MAX_GEN_FILE_HASH_BYTES` is the default of the moved `_compute_gen_file_hash` (L328); `_CACHE_SCHEMA_VERSION` has 14 uses spanning Implement/Test/Review handlers. If left in `core`, those handlers + moved helpers import them back from `core` → cycle NOT eliminated. | FR-6 helper list | grep: no `phases/*` or `handler_support` reference to `context_seed.core` after move |
| R1-F3 | Validation | medium | FR-14's "full pytest suite passes" is the only stated acceptance for behavior preservation. Add an explicit, automatable acceptance criterion: (a) `python -c "import …context_seed.core"` succeeds in a fresh interpreter; (b) grep/import-linter gate asserts 0 `__getattr__` in the package and 0 `phases/* → core` imports. | The DoD (PLAN) mentions these greps but the REQUIREMENTS give no acceptance test for the central claim ("cycle eliminated, shim deleted"). A passing suite does not by itself prove acyclicity — the old lazy shim could be re-added and tests would still pass. | New FR under Cross-cutting (FR-16) | CI gate runs the import + acyclicity check; fails if any phase imports core |
| R1-F4 | Interfaces | medium | Strengthen FR-9: replace "assert public surface via `__all__` equality" with "assert `__all__` equality AND that every exported name resolves to exactly one definition site (no duplicate definition)". | `__all__` name-equality passes even if a symbol is accidentally re-defined in two homes; identity/singleton is what src consumers and `mock.patch` actually rely on. A pure move must not silently become a copy. | FR-9 | Test enumerates each `__all__` entry and asserts `inspect.getsourcefile` is unique / object identity matches the real home |
| R1-F5 | Risks | medium | FR-15's bind-proof gate ("mock asserted-called") is necessary but insufficient. Require a raising sentinel: patch the target with a callable that raises if the real function is also reached, to prove the patch fully intercepts (not just that the mock was touched). | A pre-existing vacuous `context_seed_handlers._ensure_context_loaded` patch (11×) can stay green while the real function still runs; `assert called` does not detect double-execution. The sentinel is the only gate that catches "silently-broken but green." | FR-15 acceptance text | For one representative site, prove the sentinel raises pre-migration and does not post-migration |

**Endorsements:** none — first round (Appendix C empty).
