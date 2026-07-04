# Forward-Looking Analysis — Structural Refactoring

**Date:** 2026-07-04
**Author:** post `context_seed` phases/ extraction (merged to `origin/main` `262e908e`)
**Purpose:** capture what's next after the first god-file elimination — the reusable playbook it
produced, the remaining work, the prioritized backlog, and the risks. Written to be picked up cold.

---

## 1. Where we are

The `context_seed` refactor is **merged to main**. `core.py` went **9,952 → ~279 lines** (pure
aggregator); it is no longer in the SDK's top-20 largest files. The dependency inversion is gone,
the `__getattr__` shims are deleted, and an automated acyclicity gate now guards the invariant.

**Top god files remaining (post-refactor, `grep -c` lines):**

| Rank | File | Lines | Status / note |
|---|---|--:|---|
| 1 | `contractors/prime_contractor.py` | 6,094 | **Active** construction path. Breadth (124 methods), not depth. |
| 2 | `contractors/artisan_phases/development.py` | 5,678 | ON HOLD orchestrator, but **actively reused** — the live IMPLEMENT path delegates to its `DevelopmentPhase`/`DevelopmentChunk`/`ChunkStatus` at runtime. Not quarantinable without extraction (§4.1). |
| 3 | `micro_prime/engine.py` | 5,087 | **Active**. Per-language branching → strategy-pattern candidate. |
| 4 | `workflows/builtin/plan_ingestion_workflow.py` | 4,987 | **Active**. Has a 1,176-line `_execute`. |
| 5 | `contractors/context_seed/phases/implement.py` | 4,722 | **Just isolated** (this refactor). Part B target. |
| 6 | `contractors/artisan_contractor.py` | 3,922 | **ON HOLD** but **entangled** — houses shared primitives (`AbstractPhaseHandler`, `WorkflowPhase`, …) the active path imports. Extract those first, *then* quarantine (see §4.1). |
| 7 | `contractors/prime_postmortem.py` | 3,744 | Active. Watch-list. |
| 8 | `contractors/integration_engine.py` | 3,557 | Active. Has the 947-line `integrate` (NR-6 / Part C). |
| — | `forward_manifest_validator.py` | 3,023 | 56 flat module-level validators → per-layer package. |

Still **~60 files over 1,000 lines**; `contractors/` remains the largest package, inflated by
~16K LOC of ON-HOLD Artisan code intermixed with active Prime code.

---

## 2. The reusable playbook this refactor produced (the real asset)

The most valuable output isn't just a smaller `core.py` — it's a **proven, low-risk recipe** for
eliminating a god file, ready to apply to the next one. It was validated across 8 commits with
3,444 tests green at every step.

### 2a. The extraction recipe (per handler / cohesive unit)
1. **AST-extract** the class/unit into its own module (byte-exact — copies bytes, so behavior is
   structurally guaranteed; no transcription risk).
2. **`ruff --select F401,F821`** to converge the import header: F821 = add, F401 = drop. Import-smoke
   passes ≠ correct — runtime-only names (`fields`, `time`) only surface in tests.
3. **Move the transitive dependency closure**, not just the named symbol — constants and helper
   functions a moved unit reads must move too, or the cycle/breakage returns (CRP R1-F2 lesson).
4. **Eager-import in the composition root** iff the unit is a leaf (imports no root); otherwise keep a
   **local import inside the factory method** (not a module `__getattr__` shim). Design proved one
   unit can *require* the local-import form (transitive cycle via `artisan_contractor`).
5. **Migrate `mock.patch` targets to the point of lookup.** Wrapper/aggregator-targeted patches are
   frequently **vacuous** (the code resolves the name in its own module); repointing makes them bind.
   Some tests only pass *because* the repointed patch binds — that's the bind-proof.
6. **Update the logger-acquisition-policy allowlist** for any new module using a string logger name.
7. **Commit self-check discipline:** the two misses this refactor made (`phases/__init__.__all__`,
   the uncommitted acyclicity gate) were both "recipe said to, momentum skipped it." Add them to the
   per-unit checklist.

### 2b. The acyclicity-gate pattern (generalizable)
`tests/unit/contractors/test_context_seed_acyclicity.py` is a template for making a layering invariant
**self-enforcing**: AST-parse (not substring) to assert (a) fresh-interpreter import succeeds,
(b) 0 module-level `__getattr__`, (c) leaf modules never import the root. Any future package split
should ship its equivalent so the invariant can't silently regress.

### 2c. The safe-merge procedure (contended `main`)
Verified end-to-end this session: on a diverged/contended `main`, merge in a **worktree off
`origin/main`**, prove disjointness (`comm -12` on changed files) + `merge-tree` clean + tests on the
*merged* tree, distinguish pre-existing failures from new ones on the parent, then **FF-push** —
never touching the shared local working tree. This avoids the clobbering hazard.

---

## 3. Remaining Part B — `context_seed` method decomposition (in-flight)

Part A isolated the handlers; the monster *methods* inside them remain. 9 methods still exceed 200
lines. This is a **different risk class** than Part A — decomposition threads dense shared local state,
so a missed variable is a silent regression the tests may not catch.

| Method | Lines | Decomposition risk | Notes |
|---|--:|---|---|
| `implement.py::execute` | 1,040 | Medium | 2 clean blocks already extracted (dry-run, existing-file-sizes). Remaining seams: gate cluster (Gate 5 has retry coupling), chunk-build cluster, resume/scoped-retry. |
| `implement.py::_tasks_to_chunks` | 732 | Medium | A "build" method; likely cleaner internal seams. |
| `implement.py::_execute_with_inner_loop` | 705 | Medium-High | Opt-in inner-loop path; verify branch coverage before cutting. |
| `review.py::execute` | 725 | Medium | Clean bookends: resume-check (~L1541), persist-results (~L2150). Per-task loop ~458 lines is the hard core. |
| `implement.py::_execute_inner_loop_tasks` | 372 | Medium | — |
| `test_phase.py::execute` | 382 | Low-Medium | — |
| `integrate.py::execute` | 364 | Low-Medium | — |
| `implement.py::_validate_truncation` | 251 | Low | — |
| `finalize.py::execute` | 248 | Low | — |

**Recommended cadence:** one extraction → ruff → run the handler's dedicated test file → commit.
Only extract blocks with a clear input/output boundary (early-return branches, pure computations,
cache load/save bookends). **Flag, don't force**, any block whose local-state web makes a safe
signature intractable — a 400-line method with 30 interdependent locals is better left whole than
split wrong. Start with the low-risk tail (finalize/integrate/test_phase `execute`) to keep momentum
cheap, then the review bookends, then the implement gate cluster last.

**Effort estimate:** ~12–15 more extractions to bring the two big `execute`s and the two `_execute_*`
methods under ~200 lines. This is polish inside now-isolated files — **lower priority** than starting
the next god file, and safely deferrable/incremental.

---

## 4. Prioritized god-file backlog (apply the §2 recipe)

Ordered by value × tractability. The recipe transfers directly to any of these.

1. **Quarantine ON-HOLD Artisan code — SMALLER & harder than earlier drafts claimed.** Quarantine =
   *relocate* frozen Artisan code into a marked `contractors/_artisan_onhold/` subpackage (import-path
   update, **no** deletion/behavior change) so it stops dominating audits. **But an import-reachability
   check (2026-07-04) largely invalidated the "clean bucket ~11K LOC" framing** — most of `artisan_phases/`
   is *reused by the active Prime path*, not frozen. Actual reality:
   - **Genuinely quarantinable — only `final_testing.py` (1,313).** No module imports it (import-unreachable;
     only a docstring in `artisan_phases/__init__.py` mentions it). Effectively dead. Safe to relocate.
   - **Test-only — `test_construction.py` (2,309).** No active-src importer; referenced by `artisan_phases/
     __init__.py` + 4 test files. Movable with those import updates.
   - **Entangled / active-runtime-reused (do NOT move without extraction):**
     `development.py` (5,678 — active `implement.py`/`design_support.py`/`plan_ingestion_mottainai.py`
     delegate to `DevelopmentPhase`/`DevelopmentChunk`/`ChunkStatus` at runtime), `preflight.py` (active
     `gate_contracts.py`), `retrospective.py` (active `postmortem.py`/`prime_postmortem.py`), and
     `artisan_contractor.py` (3,922 — base primitives `AbstractPhaseHandler`/`WorkflowPhase`/`compute_lanes`/
     `HAS_OTEL`/… used by ~15 active files). These are load-bearing; quarantining requires extracting the
     reused pieces into a neutral module first (same sever-the-inversion pattern this refactor used).

   **The deeper finding:** `artisan_phases/` is a *mix* of frozen and actively-reused modules — "ON HOLD"
   applies to the Artisan **orchestrator** (`artisan_contractor`'s 8-phase driver), NOT to the phase
   **libraries** the active Prime path reuses. So there is no clean "move the phases as a block" win.
   Moving only the 2 clean files would *splinter* `artisan_phases/` across two dirs while the reused phases
   stay put. **Options:** (a) minimal — isolate/annotate just `final_testing.py` (the dead one); (b) proper —
   a real reused-library vs. frozen-orchestrator separation (a design project, not a file move); (c) leave
   it and drop "quarantine Artisan" from the cheap-wins list. This is **no longer the recommended first
   move** — see §4.2 for a genuinely cheap win.

2. **`plan_ingestion_workflow.py` (4,987).** Has a **1,176-line `_execute`** with a nested ~1,000-line
   `_fail`. A sibling `plan_ingestion_emitter.py` already exists, so the split pattern is established.
   Extract prompt-building, task-derivation, and the emitter path. High value (active, hot path).

3. **`integration_engine.py::integrate` (947-line method) — the deferred NR-6 / Part C.** Different
   file/class from this refactor. The orchestration helpers already exist (`_attempt_repair`,
   `_run_anzen_gate`, `_run_semantic_checks`); `integrate` should orchestrate, not inline. Well-scoped.

4. **`prime_contractor.py` (6,094).** The #1 file, but it's *breadth* (124 methods), not a single
   monster method — a class-level SRP problem. Lower urgency; when touched, peel off collaborator
   classes (`SeedContextLoader`, `GenerationContextBuilder` — the seams are already named as methods).

5. **`micro_prime/engine.py` (5,087).** Per-language branching (`engine.py branches per language`) →
   a **strategy-per-language** decomposition rather than in-method branching. Structural, medium effort.

6. **`forward_manifest_validator.py` (3,023).** 56 flat module-level validators; CLAUDE.md describes
   "10 validation layers." Group into a `forward_manifest/validators/` package by layer — maps
   structure to the documented mental model. Low risk (functions, not shared state).

7. **`cli.py` watch-item.** Was 1,660 and growing; Typer apps split cleanly into sub-command modules.
   Split before it hits 2K. (Note: `cli.py` is contended — the openapi work touches it — coordinate.)

---

## 5. Follow-on opportunities (from this refactor's Non-Requirements)

- **NR-7 → Tier 2: retire the `context_seed_handlers.py` compat wrapper.** Now that symbols live in
  their real homes, the wrapper is pure indirection. Migrating its ~5 active src consumers + ~44 test
  files off it (to `handler_support`/`phases`/`shared` directly) and deleting it removes a documented
  maintenance burden (the "re-export new symbols" rule in CLAUDE.md). Separate, mechanical, its own PR.
- **Generalize the acyclicity gate.** Promote the §2b pattern to a shared test helper so any package
  can assert its layering in ~5 lines.
- **CLAUDE.md update.** The `context_seed_handlers.py` compat-wrapper caveats and the "patch
  `context_seed.core`" guidance are now partially stale — core no longer holds the handlers. Refresh
  after Part B / wrapper retirement.

---

## 6. Risks & watch-items

- **Pre-existing failing test on `main` (not ours):**
  `backend_codegen/test_cli_backend.py::test_pilot_regen_is_zero_cost_and_gate_green` fails on clean
  `origin/main` (proven), from in-flight openapi/backend_codegen work. Don't misattribute it to the
  refactor; someone should triage it separately.
- **Multi-agent contention is constant.** Concurrent Cursor/Antigravity/Claude agents + ~13 worktrees.
  `main` drifts between turns. Always `git fetch` + re-check before any git op; land contended work via
  worktree-off-`origin/main` + FF-push (§2c). Never `git merge` into the shared working tree.
- **Part B regression surface.** The test suite stayed green even with vacuous patches pre-migration —
  i.e. coverage has gaps. Decomposition regressions may not be caught. Prefer conservative,
  clearly-bounded extractions; consider adding characterization tests before deep cuts.
- **`git worktree remove` deletes gitignored payload.** Check `git -C <wt> status --ignored` before
  removing any worktree with a `.startd8/` store.

---

## 7. Recommended next sequence

1. **`plan_ingestion_workflow._execute`** (§4.2) — the genuinely cheap large win (the Artisan-quarantine
   idea largely collapsed under an import-reachability check; see §4.1 — most of `artisan_phases/` is
   actively reused, so it is *not* a cheap relocation).
2. **Finish Part B incrementally** (§3) — or defer; it's isolated polish.
3. **`plan_ingestion_workflow._execute`** (§4.2) — next real god-method, established split pattern.
4. **Retire the compat wrapper** (§5) — closes out this refactor's Tier-2 tail.

Each is independently valuable, uses the §2 recipe, and lands via the §2c safe-merge procedure.
