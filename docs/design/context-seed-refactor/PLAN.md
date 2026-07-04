# Context Seed Extraction & Decomposition — Implementation Plan

**Version:** 2.0 (dependency-inversion elimination — supersedes v1.0's pure-move)
**Date:** 2026-07-04
**Tracks:** REQUIREMENTS.md v0.4
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
only external deps + `shared` + `tracing`. Repoint `phases/design.py`'s `from core import (…)` →
`from handler_support import (…)` in the same step and confirm the design tests stay green — this
proves the leaf module works before we pile the other four handlers onto it.

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

Planning found **20 mock-patch sites** against `context_seed_handlers.*` / `context_seed.core.*`.
Two patterns matter:

- **Correct model (already in tree):** `patch("…context_seed.phases.plan._load_enriched_seed")`
  — patches the symbol *in the phase module that looks it up*. This is the target shape after a move.
- **At-risk sites:** e.g. `test_integrate_phase.py` patches `context_seed_handlers._ensure_context_loaded`
  (11×), and `test_implement_auto_commit.py` patches `context_seed_handlers.subprocess` (5×). These
  patch the *wrapper's* re-exported binding, not the binding the handler actually calls. Today the
  handler is in `core.py`; after the move it's in `phases/<mod>.py`. **The lookup namespace changes.**

**Protocol per handler:**
1. Before moving, run the handler's test file and confirm each relevant patch actually takes effect
   (the mock is asserted-called, not vacuously green). Any patch that is *already* a no-op is flagged.
2. After moving, repoint each patch to `…context_seed.phases.<mod>.<symbol>`.
3. Re-run; confirm the mock is exercised (add an `assert mock.called` if none exists, to prove the
   patch binds — prevents preserving a pre-existing vacuous patch).

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
   `__init__.py` design `__getattr__`; repoint the compat wrapper's import lines; assert `__all__`
   unchanged on wrapper + package `__init__`. `core.py` is now the pure aggregator.

## Part B — Method decomposition (per handler, after it lands)

Once handler `H` is in its own file, decompose its >200-line methods into named private steps.
Behavior-preserving: pure extraction, no control-flow change. Confirmed targets:
- `implement.py`: `execute` (~1,137), `_execute_with_inner_loop` (~706), `_tasks_to_chunks` (~733).
- `review.py`: largest methods (~384 `execute` + others).
Decompose only after the handler's test file is green post-move (so a decomposition regression is
isolated from a move regression).

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

- `core.py` reduced to the pure aggregator (~200 LOC); `handler_support.py` + 5 `phases/*.py` added.
- **No `__getattr__` shim** anywhere in `context_seed` (grep proves 0 hits); no phase imports `core`.
- Compat wrapper + `context_seed/__init__.py` public `__all__` **unchanged** (assert via `__all__` equality test).
- Every migrated patch proven to bind (mock asserted-called); 0 patches target `context_seed.core.*`
  or `context_seed_handlers.*` for a symbol a handler *calls* (grep proves).
- Full `tests/unit/contractors` green with `PYTHONPATH=src`.

---

*Plan v2.0 — dependency-inversion elimination. Supersedes v1.0 (pure move). Tracks REQUIREMENTS v0.4.*
