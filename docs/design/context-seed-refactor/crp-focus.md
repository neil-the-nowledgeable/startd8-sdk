## Focus: pressure-test the Essential vs Accidental complexity boundary

This refactor pivoted at v0.4 from *relocating* accidental complexity to *eliminating* it. Weight
your review on whether the v0.4/v2.0 shape is truly the minimal essential-complexity form — and
whether it quietly introduces new accidental complexity of its own.

**Primary asks (please answer each with Summary / Rationale / Assumptions / Suggested improvements):**

1. **Is the dependency-inversion diagnosis correct and complete?** §0.2 of REQUIREMENTS claims the
   root accidental complexity is that `core.py` conflates (a) shared-helper library, (b) aggregator,
   (c) handler home, forcing phases to import back from `core` and forcing the `__getattr__` shim.
   Is that the real root, or a symptom? Is there a *simpler* essential shape than the proposed
   `handler_support.py` (leaf) ← `phases/*` ← `core` (aggregator)?

2. **`handler_support.py` vs folding into `shared.py`.** The plan creates a *new* leaf module rather
   than dumping the 15 helpers into the existing `shared.py`, arguing single-responsibility (shared =
   seed-task parsing; handler_support = phase plumbing). Is a new module the right call, or does it
   add a module without earning its keep? Would 2 modules (e.g. `telemetry_support` + `config_types`)
   be clearer, or is that over-splitting?

3. **Shim deletion / import-order risk.** Step 6 deletes `core.__getattr__` + the `TYPE_CHECKING`
   guard + `__init__.__getattr__`, making `core.py` import all handlers eagerly. Does eager import at
   module load risk a *different* cycle or import-order fragility (e.g. a handler that transitively
   imports something that imports `core`)? What must be proven before deleting the shim?

4. **Wrapper-repoint blast radius.** FR-9 repoints `context_seed_handlers.py` import lines (44 test
   files + 5 active src consumers + 4 on-hold Artisan consumers depend on it) while keeping `__all__`
   fixed. Is asserting `__all__` equality sufficient, or can a repoint change *identity/binding*
   semantics that a consumer or a `mock.patch` relies on?

5. **Patch-Migration Protocol adequacy.** The plan flags that some current
   `context_seed_handlers._ensure_context_loaded` patches (11×) may already be vacuous. Is the
   "prove the mock binds (assert called)" gate enough to catch a silently-broken test, or is a
   stronger check needed (e.g. a temporary sentinel that raises if the real function is hit)?

6. **Un-removed accidental complexity.** Does the plan *preserve* any accidental complexity it could
   opportunistically remove within the behavior-preserving boundary (duplicated per-handler boilerplate
   — `_log_task_boundary_*`, provenance, span capture — that an `AbstractPhaseHandler` template method
   could absorb; dead `__all__` entries; unused re-exports)?

**Do NOT relitigate (settled):**
- Behavior-preserving boundary: no algorithm / prompt / scoring / control-flow changes. This is a pure
  structural refactor.
- `IntegrationEngine.integrate` (~947 LOC) is out of scope (NR-6) — different file/class.
- The compat wrapper is kept working, not retired (NR-7) — retirement is a separate Tier-2 migration.
- The five handlers are mutually independent (grep-verified) — don't re-derive.
