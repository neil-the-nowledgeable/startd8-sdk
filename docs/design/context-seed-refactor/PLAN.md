# Context Seed Extraction & Decomposition — Implementation Plan

**Version:** 2.1 (Post-CRP R1 triage — supersedes v2.0)
**Date:** 2026-07-04
**Tracks:** REQUIREMENTS.md v0.5
**Branch:** `refactor/context-seed-phases-extraction`

---

## Why v2.0 replaces v1.0

v1.0 mirrored the `design.py` "core-dependent phase" flavor — phases importing shared symbols
*back from* `core`, surfaced through a lazy `__getattr__` shim. That flavor **is** the accidental
complexity (a dependency inversion), so v1.0 relocated the mess and grew the shim. v2.0 eliminates it.

## Target architecture (acyclic, one-way dependency arrows)

```
handler_support.py  (leaf: config, listeners, telemetry/hash/provenance helpers)
shared.py           (leaf: seed-task parsing — already clean, imports no core)
        ▲
        │  import
phases/{plan,scaffold,design,implement,integrate,test_phase,review,finalize}.py
        ▲
        │  import (eager, no shim)
core.py  →  pure aggregator: class ContextSeedHandlers  (~200 LOC)
        ▲
        │  re-export (public __all__ unchanged)
context_seed_handlers.py (compat wrapper, kept working — NR-7)
```

No arrow points *back* into `core`. The `__getattr__` shim and `TYPE_CHECKING` design guard are
**deleted** because nothing needs them once phases depend on leaves instead of the aggregator.

## Step 0 — Extract the stranded substrate (enables everything else)

Move the ~15 leaf helpers/classes (FR-6 list) from `core.py` → new `handler_support.py`.
Verified leaf: their bodies reference no `*PhaseHandler`/aggregator (the only such refs in that
region are in `__all__` and the shim, which are being deleted anyway). `handler_support.py` imports
only external deps + `shared` + `tracing`. **Split into two commits (per CRP R1-S5)** so a design-test
regression is unambiguously attributable:
- **Step 0a** — create `handler_support.py`; move the ~15 helpers/classes **plus their transitive
  constant closure** (`_CACHE_SCHEMA_VERSION`, `_PHASE_RESULT_KEYS`, `_MAX_GEN_FILE_HASH_BYTES`,
  `_SIZE_REGRESSION_THRESHOLD`, `_SIZE_REGRESSION_MIN_LINES` — per CRP R1-S3/F2). `core` temporarily
  re-imports them (so `design.py` still works); assert `handler_support.py` has 0 `import …core`.
- **Step 0b** — repoint `phases/design.py`'s `from core import (…)` → `from handler_support import (…)`;
  green the design tests. This proves the leaf before the other four handlers pile onto it.

## Per-handler extraction recipe (mechanical, repeatable)

For handler `H` → `phases/<mod>.py` (after Step 0 lands `handler_support.py`):

1. **Create `phases/<mod>.py`.** Copy `design.py`'s header import block; keep only what `H` uses.
2. **Import shared symbols from `handler_support`/`shared`** — NOT `core` — exactly the symbols `H`
   consumes (per-handler list below; same symbol sets, new home).
3. **Cut `H`'s class body verbatim** from `core.py` into the new module.
4. **Aggregator:** add `H` to `core.py`'s eager top-level phase imports (acyclic now — no local
   import, no shim entry).
5. **`phases/__init__.py.__all__`:** add `"<mod>"`.
6. **Migrate that handler's mock-patch targets** (see Patch-Migration Protocol) — patch at
   `phases.<mod>.<symbol>`, the point of lookup.
7. **Run the handler's dedicated test file(s)** with `PYTHONPATH=src` — green before commit.

Once all five are out, **delete** `core.__getattr__`, the `TYPE_CHECKING` design guard, and the
`__init__.py` design `__getattr__`. Repoint the compat wrapper's import lines (handlers from
`phases`/aggregator, helpers from `handler_support`/`shared`); assert its `__all__` is unchanged.

### Shared-symbol import contract (same sets, sourced from `handler_support`/`shared`)

| Handler → module | Imports (from `handler_support` unless noted) |
|---|---|
| `implement.py` | `EditModeClassification, HandlerConfig, PerFileMode, SeedTaskUnit, _coerce_optional_float, _compute_design_results_hash, _dict_to_gen_result, _log_task_boundary_complete, _log_task_boundary_start` |
| `integrate.py` | `HandlerConfig, SeedTaskUnit, ArtisanIntegrationListener, OTelIntegrationListener, _build_provenance_links, _capture_task_span_context, _log_task_boundary_complete, _log_task_boundary_start`; `_ensure_context_loaded` from `shared` |
| `test_phase.py` | `HandlerConfig, _build_provenance_links, _capture_task_span_context, _compute_design_results_hash, _compute_gen_file_hash, _format_review_prompt, _log_task_boundary_complete, _log_task_boundary_start, _log_task_timing` |
| `review.py` | `HandlerConfig, _build_provenance_links, _capture_task_span_context, _coerce_optional_float, _compute_design_results_hash, _compute_gen_file_hash, _format_review_prompt, _get_review_template, _log_task_boundary_complete, _log_task_boundary_start, _log_task_timing` |
| `finalize.py` | `HandlerConfig` |

## Patch-Migration Protocol (the highest-risk step — FR-15)

Planning found **21 mock-patch sites** against `context_seed_handlers.*` / `context_seed.core.*`
(recount per CRP R1-S4: `subprocess` cluster is **6**, not 5). Two patterns matter:

- **Correct model (already in tree):** `patch("…context_seed.phases.plan._load_enriched_seed")`
  — patches the symbol *in the phase module that looks it up*. This is the target shape after a move.
- **At-risk sites:** e.g. `test_integrate_phase.py` patches `context_seed_handlers._ensure_context_loaded`
  (11×), and `test_implement_auto_commit.py` (5) + `test_context_seed_review_finalize.py` (1) patch
  `context_seed_handlers.subprocess` (**6×** total). These patch the *wrapper's* re-exported binding,
  not the binding the handler actually calls. Today the handler is in `core.py`; after the move it's
  in `phases/<mod>.py`. **The lookup namespace changes.**

**Protocol per handler (per CRP R1-F5/S4 — `assert called` is not enough):**
1. Before moving, install a **raising sentinel** at each relevant patch target: replace it with a
   callable that raises if the *real* callee is reached while patched. Run the test file — a green
   result now proves the patch *fully intercepts*; a still-green result where the sentinel never
   fires flags an *already-vacuous* patch (the mock and the real function both no-op).
2. After moving, repoint each patch to `…context_seed.phases.<mod>.<symbol>`.
3. Re-run with the sentinel; confirm it fires iff expected. `assert mock.called` alone catches
   "never invoked" but not "real function also ran" — the sentinel catches both.

## Ordering (each step = one commit)

0. **`handler_support.py`** — extract the stranded substrate; repoint `phases/design.py` to it;
   green design tests. *This is the keystone: it proves the leaf module before any handler moves.*
1. **`finalize.py`** — needs only `HandlerConfig`; ~840 LOC; validates the handler recipe. Tests:
   `test_finalize_partial_manifest.py`, `test_finalize_status_rollup.py`, `test_context_seed_review_finalize.py`.
2. **`integrate.py`** — ~380 LOC; listener/`SeedTaskUnit` imports **and** the `_ensure_context_loaded`
   patch cluster (11 sites, repointed to `phases.integrate`). Tests: `test_integrate_*` (5 files).
3. **`test_phase.py`** — ~850 LOC; review-template shared helpers.
4. **`review.py`** — ~2,180 LOC; large but self-contained. Tests: `test_review_*` (4 files).
5. **`implement.py`** — ~4,650 LOC flagship, last, recipe fully de-risked. Tests: `test_implement_*` (7 files).
6. **Delete the shims** — remove `core.__getattr__`, the `TYPE_CHECKING` design guard, and the
   `__init__.py` design `__getattr__`; repoint the compat wrapper's import lines. Wrapper repoint homes:
   handlers ← `phases`; helpers ← `handler_support`/`shared`; **and the ~8 `design_support`-owned
   symbols ← `design_support` directly** (per CRP R1-S1 — the pure-aggregator `core` no longer
   re-imports them, so the wrapper must). **Precondition (per CRP R1-S2, do BEFORE deleting the shim):**
   run an acyclicity gate — (a) `python -c "import …context_seed.core"` in a *fresh* subprocess
   interpreter, (b) import-linter/grep contract "`phases/*` must not import `core`". Note: eager import
   only stays acyclic because `artisan_contractor` imports the wrapper *lazily* (L60) — a fragile,
   undocumented invariant; the gate makes it explicit. Then assert `__all__` unchanged + single-
   definition identity on wrapper + package `__init__`. `core.py` is now the pure aggregator.

## Part B — Method decomposition (per handler, after it lands)

Once handler `H` is in its own file, decompose its >200-line methods into named private steps.
Behavior-preserving: pure extraction, no control-flow change. Confirmed targets:
- `implement.py`: `execute` (~1,137), `_execute_with_inner_loop` (~706), `_tasks_to_chunks` (~733).
- `review.py`: largest methods (~384 `execute` + others).
Decompose only after the handler's test file is green post-move (so a decomposition regression is
isolated from a move regression).

**Intentionally deferred (per CRP R1-S5, do NOT re-propose):** hoisting the shared boilerplate
(`_log_task_boundary_start`/`_complete`, provenance, span-capture — called ~28× across handlers)
into an `AbstractPhaseHandler` *template method* is a **Tier-2, behavior-changing** refactor (it
alters control flow) and violates the behavior-preserving boundary (NR-3). The boilerplate is already
centralized as free functions in `handler_support`; template-method consolidation is out of scope.

## Part C — `IntegrationEngine.integrate` (resolves OQ-1: it is NOT a context_seed handler)

The ~947-line `integrate` lives in `IntegrationEngine` in `integration_engine.py` — a **different
class in a different file**, unrelated to `IntegratePhaseHandler`. It should be a **separate,
independently-sequenced refactor** (its own branch/PR), not conflated with the phase extraction.
The helpers it needs already exist (`_attempt_repair`, `_run_anzen_gate`, `_run_semantic_checks`),
so decomposition is an orchestration-extraction. Deferred out of this plan's Parts A/B.

## Verification (every step)

```bash
PYTHONPATH=src python3 -c "from startd8.contractors.context_seed_handlers import (
  ImplementPhaseHandler, IntegratePhaseHandler, TestPhaseHandler,
  ReviewPhaseHandler, FinalizePhaseHandler, ContextSeedHandlers); print('OK')"
PYTHONPATH=src pytest tests/unit/contractors/<handler-test-files> -q   # per-step
PYTHONPATH=src pytest tests/unit/contractors -q                        # full package before merge
```

## Definition of done

- `core.py` reduced to the pure aggregator (~200 LOC); `handler_support.py` (+ constant closure) + 5 `phases/*.py` added.
- **Acyclicity gate passes** (FR-16): fresh-interpreter `import …context_seed.core` succeeds; import-linter
  contract "`phases/* ↛ core`" holds; grep proves **0** `__getattr__` in the package. `handler_support.py`
  and every `phases/*.py` have **0** `import …context_seed.core`.
- Compat wrapper + `context_seed/__init__.py` public `__all__` **unchanged AND single-definition identity**
  (each `__all__` entry resolves to one source file / one object — pure move, not a copy).
- Every migrated patch proven to *fully intercept* via the raising sentinel (not merely `assert called`);
  0 patches target `context_seed.core.*`/`context_seed_handlers.*` for a symbol a handler *calls*.
- Full `tests/unit/contractors` green with `PYTHONPATH=src`.

---

*Plan v2.1 — Post-CRP R1 triage (all 5 S-suggestions applied; see Appendix A). Adds the transitive
dependency-closure rule (constants + design_support), the fresh-interpreter acyclicity gate, the
raising-sentinel patch protocol, Step-0 0a/0b split, and the AbstractPhaseHandler deferral note.
Supersedes v2.0 (which claimed cycle-elimination without proving the closure was complete).*

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
| R1-S1 | Wrapper repoint omits `design_support` home | CRP R1 | ACCEPTED — Step 6 now lists `design_support` as a repoint home (~8 symbols core stops re-importing). | 2026-07-04 |
| R1-S2 | Eager-import acyclicity asserted, not proven | CRP R1 | ACCEPTED — Step 6 precondition: fresh-interpreter import + import-linter gate; documented the lazy-`artisan_contractor`-import invariant. | 2026-07-04 |
| R1-S3 | Step 0 must move constant closure | CRP R1 | ACCEPTED — Step 0a moves constants in same commit; DoD asserts 0 `phases/handler_support → core` imports. | 2026-07-04 |
| R1-S4 | Patch protocol lacks mechanism; 6 vs 5 count | CRP R1 | ACCEPTED — sentinel technique specified; count corrected to 21 total / subprocess 6. | 2026-07-04 |
| R1-S5 | Split Step 0 (0a/0b); note template-method deferral | CRP R1 | ACCEPTED — Step 0a/0b split; AbstractPhaseHandler deferral note added to Part B. | 2026-07-04 |
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8[1m] — 2026-07-04

- **Reviewer**: claude-opus-4-8[1m]
- **Date**: 2026-07-04 18:20:00 UTC
- **Scope**: Essential/accidental complexity boundary + import-order/blast-radius risk; code-grounded against `core.py`, `phases/design.py`, `context_seed_handlers.py`. Companion F-suggestions + ask answers live in REQUIREMENTS.md R1.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Step 6's wrapper-repoint "real homes" enumeration (handlers from `phases`, helpers from `handler_support`/`shared`) is incomplete: `context_seed_handlers.py` today re-exports ~8 `design_support`-owned symbols *via* `core` (`_detect_cross_file_edges`, `_extract_complexity_signals`, `_compute_ccd_task_metadata`, `_normalize_target_path`, `_infer_path_prefix`, `_set_default_complexity_metadata`, `build_shared_file_manifest`, `compute_critical_path_tasks`, `compute_lane_to_file_mapping`, `_extract_design_target_files`, `_extract_referenced_elements`, `_extract_structural_delta`). Add `design_support` as an explicit repoint home. | When `core` becomes a ~200-LOC pure aggregator it stops re-importing these (currently core.py L107–121), so the wrapper must import them directly from `design_support` to keep `__all__` intact. The plan's home list omits `design_support`, so a mechanical repoint would either break `__all__` or force `core` to keep re-importing design_support just for the wrapper (defeating "pure aggregator"). | Step 6 / "Repoint the compat wrapper's import lines" | `__all__` equality test on wrapper passes AND grep shows core no longer imports design_support |
| R1-S2 | Risks | high | Make eager-import safety a Step-6 *precondition*, not an assumption: add a gate that (a) imports `context_seed.core` in a clean subprocess interpreter and (b) runs an import-linter/acyclicity check over the package, executed BEFORE deleting the shim. | The plan asserts "acyclic now — no shim" by construction. Verified the likely cycle (`artisan_contractor` → wrapper → `core` → `phases/*` → `artisan_contractor`) does not fire only because `artisan_contractor` imports the wrapper lazily (L60, function/TYPE_CHECKING-indented). That is a fragile, undocumented dependency — a future module-top import of the wrapper would deadlock eager `core`. Prove acyclicity; don't assume it. | Ordering step 6 / DoD | CI: fresh-interpreter import + import-linter contract "phases must not import core" |
| R1-S3 | Data | high | Step 0's "move the ~15 leaf helpers/classes" must also move the module-level constants those helpers depend on (`_CACHE_SCHEMA_VERSION`, `_PHASE_RESULT_KEYS`, `_MAX_GEN_FILE_HASH_BYTES`, `_SIZE_REGRESSION_THRESHOLD`, `_SIZE_REGRESSION_MIN_LINES`) in the SAME commit — otherwise the "design tests green" proof at end of Step 0 is misleading (design.py doesn't exercise them, but Implement/Test/Review do). | `_PHASE_RESULT_KEYS` is read inside the moved `_build_provenance_links` (core.py L223) and `_MAX_GEN_FILE_HASH_BYTES` is the default of the moved `_compute_gen_file_hash` (L328); leaving them in `core` means `handler_support` imports back from `core` — the cycle Step 0 claims to break is still present, just hidden until a later handler lands. | Step 0 body + Shared-symbol import contract table | grep: `handler_support.py` has no `import …context_seed.core` |
| R1-S4 | Validation | medium | Patch-Migration Protocol step 1 ("confirm each relevant patch actually takes effect") gives no mechanism — specify the raising-sentinel technique, and reconcile the site count: grep finds 6 `context_seed_handlers.subprocess` patch sites, the plan says 5. | Without a concrete detection method the protocol is aspirational; a sentinel that raises when the real callee runs under an active patch is the only reliable "is this patch vacuous?" probe. The off-by-one count (6 vs 5) suggests the enumeration wasn't fully re-run for the subprocess cluster and may miss a migration target. | "Patch-Migration Protocol" steps 1 & 3; "Ordering" step 2 | Re-run `grep -rn "context_seed_handlers.subprocess" tests/`; sentinel test passes on all enumerated sites |
| R1-S5 | Ops | medium | Split Step 0 into 0a (create `handler_support.py`, move helpers+constants, keep `design.py` importing from `core` temporarily) and 0b (repoint `design.py` → `handler_support`), each its own commit; and add an explicit note that the `AbstractPhaseHandler` template-method consolidation of `_log_task_boundary_*`/provenance is intentionally deferred (Tier-2, behavior-changing). | Step 0 currently bundles the substrate move AND the design.py repoint in one commit; if a design test regresses, the cause (move vs repoint) is ambiguous — exactly the isolation discipline the plan applies elsewhere (interleave extract/decompose). The deferral note prevents a later reviewer re-proposing the template-method (it violates the behavior-preserving boundary). | Step 0 / Part B | Each of 0a/0b independently green; deferral note present in Part B |

**Endorsements:** none — first round (Appendix C empty).

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each REQUIREMENTS.md v0.4 requirement → plan coverage.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 (move ImplementPhaseHandler) | Ordering step 5 + Per-handler recipe | Full | — |
| FR-2 (move IntegratePhaseHandler) | Ordering step 2 + recipe | Full | — |
| FR-3 (move TestPhaseHandler → test_phase.py) | Ordering step 3 + recipe | Full | — |
| FR-4 (move ReviewPhaseHandler) | Ordering step 4 + recipe | Full | — |
| FR-5 (move FinalizePhaseHandler) | Ordering step 1 + recipe | Full | — |
| FR-6 (create handler_support.py leaf) | Step 0 | Partial | Omits consumed constants (`_CACHE_SCHEMA_VERSION`, `_PHASE_RESULT_KEYS`, `_MAX_GEN_FILE_HASH_BYTES`, `_SIZE_REGRESSION_*`) — R1-S3/R1-F2; OQ-3 vs FR-6 contradiction on review helpers — R1-F1 |
| FR-7 (phases import leaf, not core; repoint design.py) | Step 0 + recipe step 2 | Full | — |
| FR-8 (core = pure aggregator, delete shim, eager import) | Ordering step 6 | Partial | Eager-import acyclicity asserted, not proven — R1-S2 |
| FR-9 (wrapper repoint, `__all__` unchanged) | Ordering step 6 | Partial | design_support repoint home omitted — R1-S1; `__all__` equality ≠ single-definition identity — R1-F4 |
| FR-10 (`__init__.py` shim delete) | Ordering step 6 | Full | — |
| FR-11 (phases/`__init__`.`__all__` += 5 names) | Recipe step 5 | Full | — |
| FR-12 (decompose >200-line methods) | Part B | Full | — |
| FR-13 (behavior-preserving decomposition) | Part B | Full | — |
| FR-14 (no behavior change; pytest green) | Verification + DoD | Partial | No automatable no-cycle/clean-import acceptance gate — R1-F3/R1-S2 |
| FR-15 (Patch-Migration Protocol) | Patch-Migration Protocol | Partial | "Takes effect" lacks a mechanism (raising sentinel); subprocess site count 6 vs 5 — R1-S4/R1-F5 |
| NR-6 (IntegrationEngine.integrate out of scope) | Part C | Full | — |
| NR-7 (wrapper kept, not retired) | Target arch + Step 6 | Full | — |
