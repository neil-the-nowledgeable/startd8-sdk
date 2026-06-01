# Tier 3 Refactoring Requirements — God-Class Decomposition (high-level, for a future effort)

**Status:** Draft requirements — NOT scheduled. Captures intent so a future pass can start cold.
**Author:** generated 2026-06-01
**Predecessors:** Passes A–E (TUI, code_manifest, cli) + Tier 2 (artifact_generator, templates), all merged.
**Companion:** `docs/design/TIER2_REFACTORING_PLAN.md` (the executed lower-risk tier).

---

## 1. Why Tier 3 is a different problem

Tiers 1–2 split **collections** — files that were bundles of independent units (dataclasses,
per-language functions, command groups). The fix was *relocation + re-export*, and moved code was
byte-identical.

Tier 3 targets **god-classes**: a single large class whose methods share mutable `self` state. You
cannot relocate methods to a new module as free functions — they are coupled through the instance.
The proven tool here is the **Pass-B mixin decomposition** (see `tui/mixin_*.py`): carve the methods
into topical mixin classes, keep a thin shell class that inherits from them, and rely on the MRO so
every method still resolves on the original class. Moved methods stay byte-identical; only the class
header and import wiring change.

**This is inherently higher-risk than Tiers 1–2** and must not be attempted as a single mechanical
sweep. It requires per-class call-graph analysis to find genuine seams (state clusters), and in some
cases genuine redesign (extract collaborator objects), not just mixins.

## 2. Scope

### In scope (active code, by descending value)
| File | Lines | God-class | Methods | Notes |
|------|------:|-----------|--------:|-------|
| `contractors/prime_contractor.py` | 5,419 | `PrimeContractorWorkflow` (5,077) | 86 | **Highest priority** — the only active construction path (per CLAUDE.md). |
| `micro_prime/engine.py` | 5,043 | `MicroPrimeEngine` (3,144) | 43 | Plus ~41 module-level functions around it — some may extract collection-style first. |
| `workflows/builtin/plan_ingestion_workflow.py` | 4,682 | `PlanIngestionWorkflow` (3,592) | 28 | Few methods but very large ones — may need method-level decomposition, not just mixins. |
| `contractors/integration_engine.py` | 3,032 | `IntegrationEngine` (2,898) | 25 | Repair/merge orchestration; check coupling to `repair/`. |
| `workflows/builtin/primary_contractor_workflow.py` | 1,827 | `PrimaryContractorWorkflow` (1,673) | 23 | Smallest; good warm-up candidate. Note the `Lead`/`Primary` alias history. |

### Explicitly OUT of scope
- **All Artisan code** — `contractors/artisan_contractor.py` (3,923), `contractors/context_seed/**`
  (incl. `phases/design.py`, 2,331). CLAUDE.md: Artisan is **ON HOLD (2026-03-12)**; "don't invest."
  Large, but refactoring effort here has near-zero return. Leave alone.

## 3. Functional requirements

- **FR-1 (no behavior change).** Public API and runtime behavior identical. Every method/attribute
  resolvable on the original class name and import path after the split (verify via MRO + `hasattr`).
- **FR-2 (byte-faithful moves).** Method bodies moved verbatim. The only permitted edits are
  relative-import re-leveling (only if the new module sits at a different package depth) and the
  class-header/`__init__`-wiring changes. Verify with an AST block-diff (zero mismatches), as in B/D/E.
- **FR-3 (seam-driven, not prefix-driven).** Mixin/collaborator boundaries must follow a real
  call-graph/state-cluster analysis per class — which methods touch which `self.*` attributes — not
  just name prefixes. Document the chosen seams before moving code.
- **FR-4 (shell stays the entry point).** `__init__`, the top-level public entry method(s), and any
  lifecycle/`run` method stay in the shell class; topical method clusters become mixins it inherits.
- **FR-5 (incremental + independently verifiable).** One class at a time; within a class, land
  mixins in small groups, each gated by the full verification harness. Never one big sweep.
- **FR-6 (consider collaborators where mixins fit poorly).** Where a method cluster owns a coherent
  slice of state (e.g. checkpoint/cache, postmortem, repair dispatch), prefer extracting a
  **collaborator object** the shell holds (composition) over a mixin. Mixins are for behavior that
  legitimately shares the whole instance; composition is cleaner for self-contained sub-state.

## 4. Non-functional requirements / constraints

- **NFR-1 (verification harness — mandatory each step).** Reuse the B–E gate: compile → AST
  byte-faithful diff → public-surface `hasattr` parity → functional smoke (instantiate + exercise an
  entry method) → targeted test suite → logger-acquisition policy → **collection-error parity**
  (baseline is **16** as of 2026-06-01; zero new).
- **NFR-2 (baseline before blame).** The repo carries 16 pre-existing collection errors and known
  pre-existing test failures (e.g. micro_prime `test_seven_templates`, `test_flag_is_true`,
  `cross_language_elements`; `test_symtable_overhead`; `forward_manifest_validator_disk`). Always
  diff a failure against a clean checkout before attributing it to the refactor.
- **NFR-3 (logger policy).** New modules must use `get_logger(__name__)` (or the existing
  try/`get_logger`-else-`logging.getLogger(__name__)` idiom). Any new file using a *string* logger
  name must be added to the allowlist in `tests/unit/contractors/test_logger_acquisition_policy.py`.
- **NFR-4 (context_seed compat wrapper).** If any work touches `contractors/context_seed/` (it
  shouldn't, given §2 OUT-of-scope), honor the `context_seed_handlers.py` re-export rule and patch
  targets per CLAUDE.md. Listed only as a tripwire.
- **NFR-5 (worktree isolation).** Each class on its own git worktree + branch; commit per class;
  merge only on explicit approval. `main` advances continuously under parallel run-0xx work — rebase
  before merge; these files are generally untouched there but confirm.
- **NFR-6 (checkpoint/resume & OTel surfaces).** `prime_contractor.py` and `integration_engine.py`
  interact with checkpointing (`.startd8/state/`), Kaizen post-mortem artifacts, and OTel spans.
  Decomposition must not change emitted artifact shapes or span attributes. Add functional smokes
  that assert artifact/span structure, not just import success.

## 5. Per-class starting notes (to be confirmed by analysis, not taken as final)

- **`PrimaryContractorWorkflow` (1,673 / 23) — recommended first.** Smallest active god-class; good
  proof-of-approach. Watch the `Lead`/`Primary` alias relationship (CLAUDE.md): the class is exported
  under both names — preserve both.
- **`PrimeContractorWorkflow` (5,077 / 86) — highest value, do after the warm-up.** Likely seams:
  feature/seed orchestration, the listener protocol, checkpoint/resume, Kaizen post-mortem hooks,
  queue/cycle handling, integration hand-off. Several of these are candidates for *collaborators*
  (FR-6), not mixins. Expect to also peel module-level helpers/models collection-style first.
- **`MicroPrimeEngine` (3,144 / 43) + ~41 module funcs.** Two-phase: (a) collection-extract the
  surrounding module-level functions (Tier-2 style, low risk) to shrink the file, then (b) mixin/
  collaborator the engine class. Mind the Keiyaku A2A typed-contract boundaries (REQ-MP-* in
  CLAUDE.md) — don't blur them.
- **`PlanIngestionWorkflow` (3,592 / 28).** Only 28 methods but enormous ones → the win may be
  *method-level* decomposition (extracting helpers within the class) as much as mixin grouping.
  Heavy emitter/enrichment surface; check the `plan_ingestion_*.py` sibling modules for natural homes.
- **`IntegrationEngine` (2,898 / 25).** Pre-merge vs post-merge repair, semantic validation, staging.
  Strong collaborator candidate: a repair-dispatch object vs a merge/staging object. Verify coupling
  to `repair/orchestrator.py` before drawing lines.

## 6. Acceptance criteria

A Tier-3 class is "done" when:
1. The shell class is a small composition root (entry method(s) + `__init__` + mixin/collaborator wiring).
2. No resulting module exceeds ~1,000 lines (soft target; the entry shell should be far smaller).
3. FR-1/FR-2 verified (MRO parity + byte-faithful diff = zero mismatches).
4. NFR-1 harness green; collection errors unchanged at the then-current baseline.
5. NFR-6 artifact/span-shape smokes pass (for prime_contractor / integration_engine).

## 7. Sequencing recommendation

`PrimaryContractorWorkflow` (warm-up) → `IntegrationEngine` → `MicroPrimeEngine` (module funcs, then
class) → `PrimeContractorWorkflow` (largest, highest value) → `PlanIngestionWorkflow`. Reassess after
each: Tier-3 is exploratory, and a class may turn out to want composition/redesign rather than a pure
mixin split — that judgment is part of the work, not a failure of the plan.

## 8. Explicit non-goals
- No functional/behavioral changes, performance tuning, or API redesign beyond what decomposition
  strictly requires.
- No touching Artisan/context_seed (§2).
- No attempt to fix the pre-existing failing tests as part of this work (track separately).
