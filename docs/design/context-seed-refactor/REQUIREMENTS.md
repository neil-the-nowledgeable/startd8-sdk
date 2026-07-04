# Context Seed Phase-Handler Extraction & Method Decomposition — Requirements

**Version:** 0.3 (Post lessons-learned hardening — ready for CRP)
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
- **FR-6.** Each extracted module imports its required shared symbols back from `core.py`,
  mirroring `design.py`'s existing `from …context_seed.core import (…)` contract.
- **FR-7.** Extend `core.py`'s module-level `__getattr__` (L404) to lazily resolve all five
  moved handler names, so existing `from …context_seed.core import <Handler>` sites keep working.
- **FR-8.** Update `ContextSeedHandlers.create_handlers` (the aggregator, L9769) to local-import
  each moved handler, mirroring the existing `DesignPhaseHandler as _DesignPhaseHandler` local import.
- **FR-9.** `context_seed_handlers.py` compat wrapper is byte-unchanged (assert via `git diff --exit-code`).
- **FR-10.** `context_seed/__init__.py` is byte-unchanged (assert via `git diff --exit-code`).
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

- **NR-1.** Does NOT extract shared helpers (`HandlerConfig`, listeners, `_log_task_*`, etc.)
  out of `core.py` into a separate support module — they remain in `core.py` as the shared
  substrate. (Deferred; would fully sever the residual cycle but is a larger diff.)
- **NR-2.** Does NOT touch the ON-HOLD Artisan handlers (`artisan_phases/`).
- **NR-3.** Does NOT change any handler's algorithm, prompts, or scoring.
- **NR-4.** Does NOT rename `core.py` or the compat wrapper.
- **NR-5.** Does NOT decompose methods in files other than the five extracted handlers.
- **NR-6.** Does NOT refactor `IntegrationEngine.integrate` (~947 LOC) — it is a different class
  in a different file (`integration_engine.py`), unrelated to `IntegratePhaseHandler`. Tracked
  separately as PLAN.md Part C (its own branch/PR). *(Was OQ-1; resolved during planning.)*

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

*v0.3 — Post lessons-learned hardening. Applied 3 lessons (Import-Path Duplication,
Phantom-Reference Audit, CRP Steering Memory). v0.1→v0.2: 6 corrections, 5 OQs resolved,
1 requirement descoped (NR-6). Ready for CRP review.*
