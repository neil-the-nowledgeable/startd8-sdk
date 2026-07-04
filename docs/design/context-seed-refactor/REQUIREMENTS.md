# Context Seed Phase-Handler Extraction & Method Decomposition — Requirements

**Version:** 0.4 (Essential/accidental-complexity hardening — ready for CRP)
**Date:** 2026-07-04
**Status:** Ready for review
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
- **OQ-3 → No.** Wrapper-re-exported helpers (`_format_review_prompt`, `_get_review_template`) are col-0 module-level in `core`, not handler-internal; they stay in `core`.
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
  `_get_review_template`). It imports only external deps + `shared.py` + `tracing.py` — never `core`.
  It is a distinct concern from `shared.py` (which owns seed-task parsing), so it is its own module.
- **FR-7.** Each extracted phase module imports its shared symbols from `handler_support`/`shared` —
  **never from `core`**. This severs the cycle. `phases/design.py`'s existing
  `from …context_seed.core import (…)` is **repointed** to `handler_support` in the same pass
  (opportunistic elimination of the pre-existing inversion).
- **FR-8.** With phases no longer importing `core`, `core.py` becomes a **pure aggregator**
  (the `ContextSeedHandlers` class) that imports all handlers **eagerly at module top** — no local
  imports, no lazy resolution. `core.py.__getattr__` shim and the `TYPE_CHECKING` design-handler
  guard are **deleted** (they existed only to break the self-inflicted cycle).
- **FR-9.** `context_seed_handlers.py` compat wrapper keeps its public `__all__` **unchanged**, but
  its *import lines* are repointed to the symbols' real homes (handlers from `phases`, helpers from
  `handler_support`/`shared`). Assert public surface via an `__all__` equality test, not a byte diff.
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

- **FR-14.** No public behavior change. Full `pytest` suite passes with `PYTHONPATH=src` pin.
- **FR-15.** Migrate every `mock.patch` target referencing a symbol a moved handler *calls*
  to the handler's new module path (patch where looked up, not where re-exported), per the
  **Patch-Migration Protocol** (PLAN.md). Each migrated patch must be proven to bind (mock
  asserted-called), because some current wrapper-targeted patches may already be vacuous and a
  naive path-swap would silently preserve the vacuity. 20 sites enumerated; the exposure is the
  `_ensure_context_loaded` (11) and `subprocess` (5) clusters.

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
Prior: v0.3 lessons hardening (3 lessons); v0.1→v0.2: 6 corrections, 5 OQs resolved. Ready for CRP.*

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
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)
