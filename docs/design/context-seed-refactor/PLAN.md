# Context Seed Extraction & Decomposition — Implementation Plan

**Version:** 1.0
**Date:** 2026-07-04
**Tracks:** REQUIREMENTS.md v0.1 → (this plan feeds v0.2)
**Branch:** `refactor/context-seed-phases-extraction`

---

## Approach summary

Finish the module split that `plan.py`/`scaffold.py`/`design.py` started. Each of the five
implementation-half handlers moves to its own `phases/*.py` module and imports its shared
substrate back from `core.py` — the **exact** contract `design.py` already uses. `core.py`
retains the shared helpers, shared classes, the `__getattr__` shim, and the aggregator.

**Two flavors of extracted phase already exist in the tree, and we follow the second:**
- *Clean* (`plan.py`, `scaffold.py`): no dependency on `core` → imported eagerly at top of `core`.
- *Core-dependent* (`design.py`): imports shared symbols from `core` → **not** imported by `core`;
  instead surfaced via `core.__getattr__` + `__init__.__getattr__`. All five of our handlers are
  core-dependent, so they follow the `design.py` flavor exactly.

## Per-handler extraction recipe (mechanical, repeatable)

For handler `H` → `phases/<mod>.py`:

1. **Create `phases/<mod>.py`.** Copy `design.py`'s header import block; keep only what `H` uses.
2. **Add `from …context_seed.core import (…)`** with exactly the shared symbols `H` consumes
   (computed per-handler below).
3. **Cut `H`'s class body verbatim** from `core.py` into the new module.
4. **Extend `core.__getattr__`** (L404) to map `"H"` → its phase module (table form, see FR-7).
5. **Aggregator:** add a local import of `H` inside `ContextSeedHandlers.create_handlers`
   (mirrors the existing `DesignPhaseHandler as _DesignPhaseHandler` local import at L163).
6. **`phases/__init__.py.__all__`:** add `"<mod>"`.
7. **Migrate that handler's mock-patch targets** (see Patch-Migration Protocol).
8. **Run the handler's dedicated test file(s)** with `PYTHONPATH=src` — green before commit.

The compat wrapper (`context_seed_handlers.py`) and `context_seed/__init__.py` need **no edit**:
both resolve `H` through `core`, which now serves it via `__getattr__`.

### Shared-symbol import contract (verified by grep)

| Handler → module | Imports from `core` |
|---|---|
| `implement.py` | `EditModeClassification, HandlerConfig, PerFileMode, SeedTaskUnit, _coerce_optional_float, _compute_design_results_hash, _dict_to_gen_result, _log_task_boundary_complete, _log_task_boundary_start` |
| `integrate.py` | `HandlerConfig, SeedTaskUnit, ArtisanIntegrationListener, OTelIntegrationListener, _build_provenance_links, _capture_task_span_context, _log_task_boundary_complete, _log_task_boundary_start` |
| `test_phase.py` | `HandlerConfig, _build_provenance_links, _capture_task_span_context, _compute_design_results_hash, _compute_gen_file_hash, _format_review_prompt, _log_task_boundary_complete, _log_task_boundary_start, _log_task_timing` |
| `review.py` | `HandlerConfig, _build_provenance_links, _capture_task_span_context, _coerce_optional_float, _compute_design_results_hash, _compute_gen_file_hash, _format_review_prompt, _get_review_template, _log_task_boundary_complete, _log_task_boundary_start, _log_task_timing` |
| `finalize.py` | `HandlerConfig` |

## `core.__getattr__` shim (FR-7)

```python
_LAZY_PHASE_HANDLERS = {
    "DesignPhaseHandler": ".phases.design",     # already extracted
    "ImplementPhaseHandler": ".phases.implement",
    "IntegratePhaseHandler": ".phases.integrate",
    "TestPhaseHandler": ".phases.test_phase",
    "ReviewPhaseHandler": ".phases.review",
    "FinalizePhaseHandler": ".phases.finalize",
}
def __getattr__(name: str):
    mod = _LAZY_PHASE_HANDLERS.get(name)
    if mod is not None:
        import importlib
        return getattr(importlib.import_module(mod, __package__), name)
    raise AttributeError(name)
```

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

## Ordering (ascending risk; each step = one commit)

1. **`finalize.py`** — needs only `HandlerConfig`; ~840 LOC; validates the whole recipe. Tests:
   `test_finalize_partial_manifest.py`, `test_finalize_status_rollup.py`, `test_context_seed_review_finalize.py`.
2. **`integrate.py`** — ~380 LOC; introduces listener/`SeedTaskUnit` imports **and** the
   `_ensure_context_loaded` patch cluster (11 sites). Tests: `test_integrate_*` (5 files).
3. **`test_phase.py`** — ~850 LOC; introduces review-template shared helpers.
4. **`review.py`** — ~2,180 LOC; large but self-contained. Tests: `test_review_*` (4 files).
5. **`implement.py`** — ~4,650 LOC flagship, last, recipe fully de-risked. Tests: `test_implement_*` (7 files).

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

- `core.py` ≤ ~1,100 lines; 5 `phases/*.py` added; `phases/__init__.py.__all__` updated.
- Compat wrapper + `context_seed/__init__.py` `__all__` **unchanged** (assert via diff).
- Every migrated patch proven to bind (mock asserted-called).
- Full `tests/unit/contractors` green with `PYTHONPATH=src`.

---

*Plan v1.0 — feeds REQUIREMENTS v0.2 reflection.*
