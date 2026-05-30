# Lead-Contractor Elimination — Requirements

**Version:** 0.4 (CRP Round R1 triaged & applied — all 9 F-suggestions accepted)
**Date:** 2026-05-30
**Status:** Internal-only scope decision applied (v0.3); CRP Round R1 (dual-document) triaged —
all 9 F-suggestions ACCEPTED and merged. Paired with `LEAD_CONTRACTOR_REMOVAL_AUDIT.md` v1.1.
**Component:** startd8 SDK — `workflows/builtin/`, `contractors/`, `implementation_engine/`,
entry points, installed workflows, dashboards, tests, docs.
**Goal:** Eliminate the "lead contractor" concept entirely. Standardize the single-task
lead/drafter workflow on the name **Primary**; preserve all behavior via the existing
`Prime`/`Primary` contractor paths.

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between the naive v0.1 view ("lead is dead weight — rename the files and delete
> the aliases") and v0.2, after the codebase audit (`LEAD_CONTRACTOR_REMOVAL_AUDIT.md`).

| v0.1 Assumption | Audit Discovery | Impact |
|-----------------|-----------------|--------|
| Lead/Primary rename is unfinished and messy | The **class** rename is **done** — every class is `Primary*`; only a thin *surface* remains (4 file names, 4 aliases, 1 `workflow_id`, 2 entry points, prose) | Scope narrows from "rename" to "remove the residual lead surface" |
| "primary/secondary/tertiary" scheme is half-built | **Only `Primary` exists.** No `Secondary`/`Tertiary` anywhere | Target naming is **just `Primary`**; do NOT introduce secondary/tertiary (FR-NR) |
| `lead` and `prime` are the same thing being renamed | `PrimeContractorWorkflow` (batch) is a **separate, active** workflow from `PrimaryContractorWorkflow` (single-task, ex-Lead) | Both survive; removal must not conflate them (FR-1) |
| `lead-contractor` is internal | It is a **public entry point** + the runtime `workflow_id`, and **ContextCore + wayfinder consume it downstream** | Hard removal is breaking → needs a **deprecation window + downstream migration** before removal (FR-5, FR-6) |
| One file to rename | **Four** module files + **four** aliases + 2 installed YAMLs + 3 dashboards + 21 test files | Phased plan with import shims, not a single sweep |
| Dashboards are cosmetic | Dashboards/state key on `workflow_id="lead-contractor"` | The `workflow_id` migration is a coordinated step, not a string swap (FR-4) |
| External users will need a deprecation window | **startd8-sdk is internal-only today** (maintainer-controlled consumers only) | **Break now**, no external window; remove the lead surface outright + migrate internal consumers in the same effort (OQ-3) |

**Resolved open questions:**
- **OQ-1 → Keep `Primary`; do not add secondary/tertiary.** The scheme was never built.
- **OQ-2 → `Prime` and `Primary` are distinct and both stay.** Only `Lead` is removed.
- **OQ-3 → `lead-contractor` is internal-only today; take the breaking change NOW.** **(Scope
  decision, 2026-05-30.)** startd8-sdk has no external consumers yet — the only consumers are
  internal projects the maintainer controls (ContextCore, wayfinder). Rather than carry a
  multi-version external deprecation window (and let future external users inherit the tech
  debt), remove the lead surface outright, coordinating the internal consumers in the **same
  effort**. This supersedes the v0.2 "deprecate-then-remove over N minor versions" stance:
  there is no external-user window to honor.
- **OQ-4 → `workflow_id` change is breaking for stored state/dashboards.** Migrate it to
  `primary-contractor`; keep a **transient** legacy-id resolution alias only for the lifetime
  of the internal-consumer migration (one coordinated change), not as a long-lived shim.
- **OQ-5 → Pre-1.0 (`0.4.0`), internal-only.** SemVer permits breaking changes freely; with no
  external users, deprecation *warnings* are unnecessary — a coordinated breaking change across
  the internal projects is cleaner than warning scaffolding nobody external will read.

---

## 1. Problem Statement

"Lead contractor" is the **precursor** name for what is now the **Primary** contractor (the
single-task lead/drafter workflow). A prior rename converted the classes to `Primary*` but left
a residual `lead` surface that is a standing source of accidental complexity and regression risk:
dual names for one concept, a `workflow_id` that disagrees with its entry-point name, stale
docstrings that send readers to nonexistent `Lead*` symbols, and 21 test files anchored on the
old name. The goal is to remove the lead surface **completely** while preserving behavior through
the canonical `Primary` (single-task) and `Prime` (batch) paths.

| Surface | Today | Target |
|---------|-------|--------|
| Single-task workflow class | `PrimaryContractorWorkflow` + `LeadContractorWorkflow` alias | `PrimaryContractorWorkflow` only |
| Module files | `lead_contractor_*.py` (×4) | `primary_contractor_*.py` (×4) |
| Backward-compat aliases | `LeadContractor{Workflow,ContextCoreWorkflow,CodeGenerator,ChunkExecutor}` | removed (after deprecation) |
| Runtime id | `workflow_id="lead-contractor"` | `workflow_id="primary-contractor"` (with legacy-id resolution shim) |
| Entry points | `lead-contractor`, `lead-contractor-contextcore` + `primary-*` | `primary-*` only (after deprecation) |
| Installed YAMLs / dashboards | `lead-contractor*` | `primary-contractor*` |
| Prose / tests / docs | ~870 references | zero "lead" references outside a documented deprecation note |

**Non-goal:** changing *what the workflow does*. This is a naming/structure elimination with
**behavior preserved**, verified by the existing test suite passing throughout.

---

## 2. Functional Requirements

- **FR-1 Preserve the two distinct workflows.** `PrimeContractorWorkflow` (batch, the active
  construction path) and `PrimaryContractorWorkflow` (single-task) MUST both remain fully
  functional and clearly distinguished. Nothing in this work merges, renames across, or
  otherwise conflates `Prime` and `Primary`. *Acceptance:* both workflows resolve and execute
  after every phase; their tests pass unchanged in behavior; **and (negative guard, R1-F5)
  `prime_contractor_workflow.py`'s `workflow_id`, its `prime-contractor` entry-point target, and
  the file's behavior are byte-unchanged by this work** — a broad `lead`→`primary` find/replace
  MUST NOT touch `Prime*` symbols (verified by `git diff` scoping the prime file to prose-only or
  no change).

- **FR-2 Rename the four `lead_contractor*` module files to `primary_contractor*`.** Rename via
  `git mv` (preserve history): `lead_contractor_workflow.py` → `primary_contractor_workflow.py`,
  `lead_contractor_models.py` → `primary_contractor_models.py`,
  `lead_contractor_contextcore_workflow.py` → `primary_contractor_contextcore_workflow.py`,
  `contractors/generators/lead_contractor.py` → `contractors/generators/primary_contractor.py`.
  All **internal** imports update to the new paths. **The `pyproject.toml` entry-point dotted
  *targets* MUST be rewritten in the same phase (R1-F1):** `lead-contractor` /
  `lead-contractor-contextcore` (and `primary-contractor*`) currently point at
  `lead_contractor_workflow:…` / `lead_contractor_contextcore_workflow:…`, which `git mv`
  invalidates — repoint the targets to `primary_contractor_workflow:…` even though the entry-point
  *names* `lead-contractor*` are not removed until Phase 5. After renaming, **reinstall (`pip
  install -e .`) so `src/startd8.egg-info/{entry_points,SOURCES}.txt` regenerate** off the new
  paths (R1-F2 / R1-S5) — stale `egg-info` otherwise fails the grep. *Acceptance:*
  `grep -rln "lead_contractor" src/**/*.py` returns nothing (scoped to Python sources, not the
  regenerated `egg-info`); `pip install -e . && pytest` is green and the workflow registry resolves
  both the `lead-contractor` and `primary-contractor` entry points without `ImportError`.

- **FR-3 Purge prose/comment/docstring references (zero behavior).** Every docstring, comment,
  and string that names `LeadContractor*` / "lead contractor" / "lead-contractor path" for
  *descriptive* purposes is updated to the `Primary`/`Prime` name it actually refers to (audit
  §1.4, §1.5 prose). The example agent id in `integrations/contextcore.py:1223` changes to a
  neutral example. *Acceptance:* no `src/` docstring or comment references a `Lead*` symbol that
  no longer exists.

- **FR-4 Migrate the runtime `workflow_id` to `primary-contractor`.** Change
  `workflow_id="lead-contractor"` → `"primary-contractor"`, and re-key **every artifact that keys
  on the id** to match. The migration set is (R1-F3, R1-F7): the installed YAMLs
  (`.startd8/workflows/lead-contractor*.yaml` — including the human-readable
  `name: Lead Contractor Workflow` field, not only `workflow_id:`), dashboards
  (`dashboards/lead-contractor-progress.json`, `startd8-mixin/dashboards/lead_contractor.libsonnet`
  + regenerated `generated/`), any dashboard/metric **labels** using the id or the space form
  `Lead Contractor`, the `.startd8/task_errors/lead-contractor/` directory, and any persisted
  **ContextCore SpanState/state JSON** carrying the id. Because pre-existing state may carry the
  old id, the registry SHOULD provide a **transient** legacy-id alias resolving `"lead-contractor"`
  → primary **for the single coordinated migration only** (not a long-lived shim, not a warning
  emitter); it is removed once internal state is re-emitted. *Acceptance:* (a) a lookup by
  `"primary-contractor"` resolves natively; (b) while the transient alias is live a lookup by
  `"lead-contractor"` resolves to the primary workflow **and emits no `DeprecationWarning`**, and
  after removal that legacy lookup raises/returns `None`; (c) `grep -riE "lead[-_ ]?contractor"`
  over `.startd8/ dashboards/ startd8-mixin/` returns only documented residue (incl. space-form
  `name:`/labels); (d) dashboards render against the new id.

- **FR-5 Remove the public `Lead*` aliases and entry points outright (no external window).** The
  four aliases (`LeadContractorWorkflow`, `LeadContractorContextCoreWorkflow`,
  `LeadContractorCodeGenerator`, `LeadContractorChunkExecutor`) and the two entry points
  (`lead-contractor`, `lead-contractor-contextcore`) are **removed** — not deprecated over a
  window. startd8-sdk is internal-only (OQ-3), so there is no external consumer to warn; the
  internal consumers are migrated in the same effort (FR-6). Removal updates `pyproject.toml`,
  `workflows/builtin/__init__.py` (`__all__` + lazy loader), and `generators/__init__.py`.
  **Non-renamed files that also carry a `Lead*` alias or symbol MUST be edited explicitly (R1-F6
  inventory orphan):** in particular `contractors/artisan_phases/development.py` holds
  `LeadContractorChunkExecutor = PrimaryContractorChunkExecutor` (L2812) — a file FR-2 does NOT
  rename, so its alias removal is owned **here**, not by the rename. *Acceptance:* both
  `grep -rn "LeadContractor"` **and** `grep -rni "lead[-_ ]?contractor" src/**/*.py` return nothing
  (case-insensitive, catches lowercase stragglers); no `lead-contractor*` entry point remains in
  `pyproject.toml`.

- **FR-6 Migrate the internal consumers in the same coordinated effort.** **ContextCore** and
  **wayfinder** (the only consumers — maintainer-controlled) MUST be retargeted from
  `LeadContractor*` / `lead-contractor` to the `Primary` names / `primary-contractor` id as part
  of this effort, not behind a multi-version gate. This requirement is a **coordination gate**
  on FR-5's removal landing (the removal and the consumer updates ship together so nothing is
  ever broken in a shared working state), but it is **not** a long-lived deprecation window.
  *Note:* the downstream-consumer set is taken from `MEMORY.md` and MUST be re-verified live at
  kickoff (the consumers may have changed). **Cross-repo cutover runbook (R1-F8 / R1-S8 — three
  independently-CI'd repos cannot merge atomically):** the documented order is (1) open
  consumer branches that retarget `Lead*`→`Primary*` / `lead-contractor`→`primary-contractor`
  against the *pre-removal* SDK (still green via the surviving aliases); (2) merge the SDK removal
  (FR-5) and immediately bump the SDK pin in each consumer branch; (3) merge the consumer branches.
  The surviving aliases keep every repo green until step 2; the only exposure window is between
  the SDK pin bump and the consumer merge, which is import-time and caught by the consumer's CI on
  its branch. *Acceptance:* a runbook documenting this order exists; a tag/commit is identified
  where all three repos reference `primary-contractor`; each consumer's branch is green against the
  post-removal SDK before its merge.

- **FR-7 Rename and retarget the lead-named tests.** `test_lead_contractor_workflow.py` →
  `test_primary_contractor_workflow.py` and `test_lead_contractor_executor.py` →
  `test_primary_contractor_executor.py` (via `git mv`); update imports/ids in those and the 19
  other test files that reference the old name to the canonical symbols. **No deprecation-shim
  test (R1-F8 — corrected):** v0.3 removed the deprecation window, so there is no warns-and-resolves
  behavior to assert. The **only** `lead`-referencing test permitted is the FR-4(b) test of the
  *transient* `workflow_id` legacy alias (resolves while live, raises after removal, **emits no
  warning**); when FR-4's alias is dropped, that test is dropped too. *Acceptance:* the full suite
  passes; after the transient alias is removed, **zero** tests reference `lead`.

- **FR-8 Update documentation.** `CLAUDE.md`, `src/startd8/contractors/README.md`, and design
  docs that describe the workflow by its old name are updated to `Primary`/`Prime`. Historical
  design docs that *record* the rename keep their text but gain a one-line "superseded — see
  Primary" note rather than being rewritten. *Acceptance:* `CLAUDE.md` and the contractors README
  contain no stale `Lead*` API references.

- **FR-9 Phased, independently-shippable delivery.** The removal ships in ordered phases, each
  green on its own (see §5). No phase leaves the tree in a non-building state. *Acceptance:* the
  test suite passes at the end of every phase.

---

## 3. Non-Functional Requirements

- **NFR-1 Behavior parity.** Zero functional change. The same inputs produce the same generated
  code, costs, and review outcomes before and after. Verified by the existing suite (no behavior
  assertions are weakened to make tests pass).
- **NFR-2 History preservation.** File renames use `git mv` so blame/history survive.
- **NFR-3 No *silent* breakage; intentional coordinated breakage is acceptable; failures are
  reversible.** With no external consumers, a multi-version `DeprecationWarning` window is **not**
  required. Instead, breakage is prevented by *coordination*: FR-5's removal lands together with
  FR-6's internal consumer updates (per the FR-6 runbook), so the shared working set is never left
  broken. The breaking change is recorded in the changelog/release notes with the `lead`→`primary`
  mapping. **Rollback (R1-F9):** if the coordinated FR-5/FR-6 landing fails partway (a consumer
  repo not green at merge), reverting **only** the FR-5 removal commit (re-adding the aliases +
  entry points) MUST restore green **without** reverting the non-breaking Phases 1–3 — i.e. the
  removal is an isolated, independently-revertable commit, not entangled with the rename/prose
  work. *Acceptance:* a tabletop revert of the FR-5 commit leaves Phases 1–3 intact and green.
- **NFR-4 Single source of truth.** After completion there is exactly one name per concept:
  `Prime` (batch), `Primary` (single-task). No alias, no second spelling.
- **NFR-5 Auditable completion (baseline-delta).** Capture a **pre-work baseline** of
  `grep -riE "lead[-_ ]?contractor" <scope>` per scope now, stored as a completion-record artifact
  (R1-S9), so completion is verified as a *delta* (every residual hit is intended), not just an
  absolute. The final grep over `src/ tests/ docs/ scripts/ pyproject.toml .startd8/ dashboards/
  startd8-mixin/` (the full `.startd8/` tree, not just `.startd8/workflows/` — R1-S1) returns only:
  (a) the **transient** `workflow_id` legacy alias + its FR-4(b) test **while live** (zero once
  dropped — there is no other shim, R1-F8); and (b) historical design-doc notes annotated as
  superseded. The grep MUST also be run case-insensitively and against the **space form**
  `Lead Contractor` and `lead_contractor` label/identifier forms (R1-S6). Each residual hit is
  enumerated in the completion record.

---

## 4. Non-Requirements

- Does **not** introduce `Secondary`/`Tertiary` contractor concepts (they were never built; the
  target is `Primary` only).
- Does **not** merge, rename, or alter `PrimeContractorWorkflow` (batch) — it is out of scope
  except where it *references* the lead name in prose (FR-3).
- Does **not** change workflow behavior, prompts' semantics, cost logic, or review logic.
- Does **not** rewrite historical design docs that record the original lead-contractor design
  (they are annotated as superseded, not deleted — institutional memory).
- Does **not** maintain a multi-version external deprecation window or `DeprecationWarning`
  scaffolding — startd8-sdk is internal-only today and the breaking change is taken now (OQ-3).
- Does **not** land FR-5's removal without FR-6's internal-consumer updates in the same effort
  (coordination gate — prevents a broken shared state, not a deprecation window).

---

## 5. Phased Delivery Plan

| Phase | Scope | Behavior risk | Gate |
|-------|-------|---------------|------|
| **Phase 0** | Audit (`LEAD_CONTRACTOR_REMOVAL_AUDIT.md`) — **done** | none | — |
| **Phase 1** | FR-3, FR-8 prose/docstring/comment + doc cleanup (no code paths) | none | suite green |
| **Phase 2** | FR-2 `git mv` file renames + internal import updates + **`pyproject.toml` entry-point target rewrites** (names kept until Phase 5) + FR-7 test renames. Then `pip install -e .` to regenerate `egg-info` (R1-S5) and clear stale `__pycache__/*.pyc` for the renamed modules (R1-S7). No long-lived `lead_contractor_*.py` shim (internal-only). | none (imports + targets updated in-tree) | `pip install -e . && pytest` green; both entry points resolve; `grep -rln lead_contractor src/**/*.py` empty |
| **Phase 3** | FR-4 `workflow_id` → `primary-contractor`; re-key installed YAMLs + dashboards; regenerate mixin. Add the **transient** legacy-id alias only if pre-existing state files require it for the migration window. | dashboards re-point | dashboards render on new id |
| **Phase 4** | FR-6 prepare internal-consumer (ContextCore, wayfinder) `lead`→`primary` edits (verified live at kickoff) | none in this repo | consumer edits staged/green |
| **Phase 5** | FR-5 remove aliases + entry points outright, **landing together with** the Phase-4 consumer updates; drop any transient legacy alias | breaking (coordinated, no external window) | FR-5/NFR-5 grep clean; all internal repos green concurrently |

Each phase is a separate PR/commit set, green independently (FR-9). Phases 1–3 are non-breaking
and can land immediately; Phases 4–5 land together as the single coordinated breaking change.

---

## 6. Open Questions

*All open questions (OQ-1 … OQ-5) are resolved — see §0.* The v0.2 carry-over (deprecation
window length) is **moot** under the internal-only decision: there is no external window. The
one remaining kickoff action is operational, not a design question:

- **OQ-6 → RESOLVED (no window).** Single coordinated breaking change. Land Phases 1–3
  immediately (non-breaking); land Phases 4–5 together (the one breaking change) in the same
  release (target `0.5.0`). The only kickoff step is **re-verifying the live internal-consumer
  set** (FR-6) since it's sourced from `MEMORY.md`.

---

*v0.4 — CRP Round R1 (dual-document, focus-weighted) triaged: all 9 F-suggestions ACCEPTED and
merged. Highest-value fixes: **R1-F1** Phase 2 was not green-independent — `pyproject.toml`
entry-point *targets* break on `git mv`, now rewritten in Phase 2 (names kept until Phase 5);
**R1-F6** `LeadContractorChunkExecutor` in the non-renamed `development.py` was an inventory
orphan, now explicitly owned by FR-5; **R1-F8** reconciled the FR-7/NFR-5 "deprecation-shim"
contradiction (the only shim is FR-4's transient `workflow_id` alias) + added the FR-6 cross-repo
cutover runbook; **R1-F3/F7** FR-4 now enumerates task_errors/SpanState/space-form artifacts;
**R1-F4** FR-4 acceptance now exercises the alias path; **R1-F5** FR-1 guards `Prime` byte-unchanged;
**R1-F9** NFR-3 adds an isolated-revert rollback. Dispositions in Appendix A; round R1 in Appendix
C. Paired with `LEAD_CONTRACTOR_REMOVAL_AUDIT.md` v1.1.*

*v0.3 — Internal-only scope decision applied. The maintainer chose to take the breaking change
now (no external users yet) rather than carry tech debt for future external users. This removes
the multi-version deprecation window and `DeprecationWarning` scaffolding (NFR-3 reframed): FR-5
removes the lead surface outright, and FR-6 becomes a same-effort coordination gate (land removal
+ internal-consumer updates together) rather than a long-lived deprecation gate. FR-4's legacy-id
alias is now transient (migration-window only). Phases 4–5 collapse into one coordinated breaking
change. Paired with `LEAD_CONTRACTOR_REMOVAL_AUDIT.md` v1.0.*

*v0.2 — Post-audit self-reflective update. Scope narrowed from "finish a messy rename" to
"remove a residual public surface"; 5 open questions resolved; discovered `lead-contractor` is a
consumed public API.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-F{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-F1 | Move entry-point *target* rewrites into FR-2/Phase 2 | R1 / opus-4.8-1m | Applied to **FR-2** + **§5 Phase 2**: targets repointed to `primary_contractor_workflow:…` in Phase 2 (names kept to Phase 5); `pip install -e .` regen + reinstall gate added. | 2026-05-30 |
| R1-F2 | Scope FR-2 acceptance grep to `src/**/*.py`; regenerate `egg-info` | R1 / opus-4.8-1m | Applied to **FR-2** acceptance (grep scoped to Python sources; egg-info regenerated, not edited). | 2026-05-30 |
| R1-F3 | FR-4: enumerate task_errors + ContextCore SpanState | R1 / opus-4.8-1m | Applied to **FR-4** migration set + acceptance (c). | 2026-05-30 |
| R1-F4 | FR-4: acceptance must exercise the legacy-alias path | R1 / opus-4.8-1m | Applied to **FR-4** acceptance (b): resolves-while-live, raises-after-removal, no warning. | 2026-05-30 |
| R1-F5 | FR-1: negative assertion that `Prime` is byte-unchanged | R1 / opus-4.8-1m | Applied to **FR-1** acceptance (negative guard on `prime_contractor_workflow.py`). | 2026-05-30 |
| R1-F6 | Give `LeadContractorChunkExecutor` an owning phase | R1 / opus-4.8-1m | Applied to **FR-5**: non-renamed files (esp. `development.py:2812`) explicitly owned by FR-5; acceptance grep made case-insensitive. | 2026-05-30 |
| R1-F7 | FR-4: re-key space-form `name:` + labels | R1 / opus-4.8-1m | Applied to **FR-4** migration set (space form, labels) + acceptance (c). | 2026-05-30 |
| R1-F8 | Reconcile FR-7/NFR-5 "deprecation-shim" with no-shim v0.3; define cross-repo landing | R1 / opus-4.8-1m | Applied to **FR-7** (no deprecation-shim test; only FR-4's transient alias test), **NFR-5** (single transient shim), **FR-6** (cutover runbook). | 2026-05-30 |
| R1-F9 | Add a rollback requirement for partial coordinated landing | R1 / opus-4.8-1m | Applied to **NFR-3**: FR-5 removal is an isolated, independently-revertable commit; tabletop-revert acceptance. | 2026-05-30 |
| R2-F1 | Own `model_catalog.py` constant rename in an FR | R2 / opus-4.8-1m | **ACCEPTED.** Add **FR-3a**: rename `Models.LEAD_CONTRACTOR_LEAD` → `PRIMARY_CONTRACTOR_LEAD` and `LEAD_CONTRACTOR_DRAFTER` → `PRIMARY_CONTRACTOR_DRAFTER` (keep the role suffix) + update call sites (`lead_contractor_workflow.py:160,254,365`, `lead_contractor_models.py:72,82,87`). Blocking for NFR-5; behavior-preserving (internal constants). Lands in Phase 1. Pairs with audit R2-S1. | 2026-05-30 |
| R2-F2 | Decide the fate of the public `lead_agent` field | R2 / opus-4.8-1m | **ACCEPTED (decision recorded): KEEP the names.** `lead_agent`/`drafter_agent` name the lead/drafter *roles* (model_catalog comment: "balanced lead + cheap drafter"), not the lead contractor — renaming them would be scope creep and a gratuitous consumer break. FR-3 fixes only the `description="Lead contractor agent"` string → "Lead agent (reviewing role)". A Non-goal line records that the role field names intentionally stay. | 2026-05-30 |
| R2-F3 | Specify FR-4 alias as a single id-normalization map | R2 / opus-4.8-1m | **ACCEPTED.** FR-4 mechanism clause: implement the transient legacy-id alias as one registry map (`lead-contractor → primary-contractor`); Phase 5 removes the `lead-contractor*` entry points + `__getattr__` branches, leaving one registration. One-line retirement; `list_workflows()` no longer double-advertises. Pairs with audit R2-S3. | 2026-05-30 |
| R2-F4 | Decide accept/defer for adjacent in-file accidental complexity | R2 / opus-4.8-1m | **ACCEPTED (decision recorded): DEFER to a separate follow-up.** The rename PR stays a pure rename (NFR-1 behavior parity verified by unchanged tests); the `fail_on_truncation` dup / unused re-exports / sync-async dup are captured in a new **follow-up issue** (not indefinitely deferred) to be cleaned in a behavior-preserving PR *after* the coordinated removal lands. Recorded as a Non-goal + tracked issue, not folded into the breaking change. | 2026-05-30 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-05-30

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-05-30 18:05:00 UTC
- **Scope**: Requirements quality (F-prefix) for lead-contractor elimination. Weighted toward sponsor focus areas: phase green-independence, `workflow_id` migration mechanism, prime-vs-primary conflation, audit-inventory completeness, coordinated FR-5+FR-6 breaking-change risk. This is the first review round on this document.

##### Sponsor focus-ask responses

**Ask 1 — Phase correctness & green-independence (can Phase 2 land green with no shim?).**
- **Summary answer:** No, not as written — FR-2 + §5 Phase 2 omit two edits that the suite needs to stay green.
- **Rationale:** The `lead-contractor` entry point (`pyproject.toml:101`, audit §1.3) targets `lead_contractor_workflow:LeadContractorWorkflow`. After Phase 2's `git mv` that target *module path* no longer exists, so entry-point discovery breaks before FR-5's Phase 5. Phase 2 must also rewrite the entry-point targets (or temporarily point them at the new module) even though entry-point *names* are not removed until Phase 5. FR-2's acceptance grep (`lead_contractor` over `src/`) would also still hit `pyproject.toml` lines 101–102 because §5 leaves those names until Phase 5.
- **Assumptions / conditions:** Editable install (`pip install -e`) re-resolves entry points from `pyproject.toml`; the test suite imports via entry-point discovery somewhere (workflow registry).
- **Suggested improvements:** See R1-F1, R1-F2.

**Ask 2 — `workflow_id` migration mechanism (transient alias vs alternatives).**
- **Summary answer:** Partial — the transient-alias approach is reasonable, but FR-4 under-enumerates what keys on the id, so the migration scope is undertestable.
- **Rationale:** FR-4 names "installed YAMLs and dashboards" but the sponsor flags `.startd8/task_errors/lead-contractor/` and ContextCore SpanState files, neither of which FR-4 mentions. The acceptance criterion ("lookup by primary-contractor resolves natively") does not test the legacy-alias resolution path it mandates.
- **Assumptions / conditions:** `task_errors` directories are keyed by `workflow_id`; ContextCore state files persist the id.
- **Suggested improvements:** See R1-F3, R1-F4.

**Ask 3 — Prime vs Primary distinction.**
- **Summary answer:** Yes, the spec keeps them separated in prose, but one acceptance grep risks a false-clean that hides Prime/Primary confusion.
- **Rationale:** FR-5 acceptance `grep -r "LeadContractor"` is case- and substring-specific; it will not catch a `lead_contractor` lowercase straggler nor confirm `Prime` was untouched. FR-1 has no negative assertion that `PrimeContractorWorkflow`'s id/entry points were *not* edited. See R1-F5.
- **Assumptions / conditions:** none.
- **Suggested improvements:** See R1-F5.

**Ask 4 — Audit inventory completeness (clean final grep per NFR-5).**
- **Summary answer:** Partial — NFR-5's grep list is good but `LeadContractorChunkExecutor` is an orphan and the space-form `Lead Contractor` is uncovered by FR-2/FR-5.
- **Rationale:** Audit §1.2 lists `LeadContractorChunkExecutor` in `artisan_phases/development.py:2812` — a file FR-2 does **not** rename. FR-5 lists it among the four aliases to remove, but no FR covers editing that non-renamed file, so it is an inventory orphan. The installed YAML `name: Lead Contractor Workflow` (space form, audit §3) is matched by NFR-5's `lead[-_ ]?contractor` regex but no FR explicitly mandates changing the human-readable `name:` field. See R1-F6, R1-F7.
- **Assumptions / conditions:** none.
- **Suggested improvements:** See R1-F6, R1-F7.

**Ask 5 — Coordinated FR-5+FR-6 cross-repo breaking-change risk.**
- **Summary answer:** Depends — the "land together" gate is sound in principle but has no defined mechanism for atomic cross-repo landing with no shared CI; a brief transient alias remains warranted as a safety net.
- **Rationale:** FR-6 says "both repos green concurrently" but three separate repos (startd8-sdk, ContextCore, wayfinder) cannot merge atomically; there is always a window where one repo has the new SDK and another has old call sites. FR-4's transient `workflow_id` alias covers stored state but not the *import-time* `LeadContractor*` symbol break that FR-5 causes. See R1-F8.
- **Assumptions / conditions:** Consumers pin the SDK by editable/path install or a version they bump manually; no monorepo.
- **Suggested improvements:** See R1-F8.

##### Executive summary

- Phase 2 is **not green-independent as specified**: the `lead-contractor` entry point targets a module path that `git mv` destroys, but §5 defers entry-point edits to Phase 5 (blocking gap).
- FR-4 under-scopes `workflow_id` consumers: `.startd8/task_errors/lead-contractor/` and ContextCore SpanState files are unlisted (the sponsor's explicit concern).
- FR-4 mandates a legacy-id alias but its acceptance criterion never exercises that alias path (untestable).
- `LeadContractorChunkExecutor` (audit §1.2, `development.py:2812`) is an **inventory orphan**: FR-5 says remove it, but no FR covers editing the non-renamed file it lives in.
- The installed YAML `name: Lead Contractor Workflow` space-form string has no explicit FR coverage.
- FR-6's "both repos green concurrently" has no atomic cross-repo landing mechanism (3 repos, no shared CI) — a transient `LeadContractor*` import alias would de-risk the cutover window.
- FR-7's "deprecation-shim test" is contradictory with v0.3's no-shim/no-window stance — the artifact it tests may not exist.
- NFR-5's grep allowlist references a "time-boxed deprecation shim" that v0.3 says is only added "if pre-existing state files require it" — completion criteria are conditional on an optional artifact.

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Validation | high | Move entry-point *target* rewrites into FR-2/Phase 2 (not Phase 5). After `git mv`, `pyproject.toml:101-102` targets (`lead_contractor_workflow:...`) point at deleted module paths; update them to `primary_contractor_workflow:...` in Phase 2 while keeping the entry-point *names* until Phase 5. | FR-2 currently says "All internal imports update to the new paths" but entry-point dotted-target strings are not Python imports and will silently break workflow discovery, violating FR-9 phase-green-independence. | FR-2 acceptance + §5 Phase 2 row | After Phase 2: `pip install -e . && pytest` green; assert workflow registry resolves both `lead-contractor` and `primary-contractor` entry points |
| R1-F2 | Validation | medium | Tighten FR-2 acceptance grep to exclude `pyproject.toml` or scope it to `src/**/*.py`. As written, `grep -rl "lead_contractor" src/` will still match `pyproject.toml` is out of src/, but `egg-info/entry_points.txt` (audit §1.5) regenerates with `lead_contractor` paths and lives under `src/`. | The acceptance criterion will fail spuriously on regenerated packaging artifacts unless they are regenerated *after* the rename and explicitly excluded or refreshed. | FR-2 *Acceptance:* clause | Run the exact acceptance grep in CI post-Phase-2; confirm only intended residue remains |
| R1-F3 | Data | high | Expand FR-4 to enumerate every artifact keyed on `workflow_id="lead-contractor"`: add `.startd8/task_errors/lead-contractor/` directories and ContextCore SpanState/state JSON files to the explicit migration list alongside YAMLs and dashboards. | FR-4 only names "installed YAMLs and dashboards"; the sponsor flags task_errors dirs and stored SpanState. Unmigrated state silently orphans error history and breaks dashboard joins on the new id. | FR-4 body, after "re-key the installed YAMLs and dashboards" | Inventory `.startd8/` for `lead-contractor`-keyed dirs/files pre-migration; assert post-migration none remain except the time-boxed alias |
| R1-F4 | Validation | medium | Add an acceptance criterion to FR-4 that exercises the legacy-id alias: a lookup by `"lead-contractor"` MUST resolve to the primary workflow while the alias is live, and MUST fail (KeyError/None) after the alias is removed. | FR-4 mandates a transient alias but its acceptance only tests the *native* `primary-contractor` lookup, so the alias mechanism it requires is never validated. | FR-4 *Acceptance:* clause | Unit test: assert alias resolves during window; assert removal makes legacy lookup raise; assert no `DeprecationWarning` is emitted (per OQ-4 "not a warning emitter") |
| R1-F5 | Validation | medium | Add a negative acceptance assertion to FR-1 that `PrimeContractorWorkflow`'s `workflow_id`, entry points, and module file (`prime_contractor_workflow.py`) are byte-unchanged by this work. | FR-1 asserts both survive but provides no guard against accidental Prime/Primary conflation during the sweep (the sponsor's explicit concern); a broad find-replace could touch `prime_contractor_workflow.py:7,152` prose and overshoot. | FR-1 *Acceptance:* clause | `git diff --stat` shows no changes to `prime_contractor_workflow.py` behavior; entry point `prime-contractor` target unchanged |
| R1-F6 | Architecture | high | Give `LeadContractorChunkExecutor` an explicit owner. FR-5 lists it for removal but it lives in `contractors/artisan_phases/development.py:2812` — a file FR-2 does NOT rename. State which FR/phase edits that file so the alias removal does not become an orphan. | Audit §1.2 + §1.4 show `development.py` carries both the alias and prose refs but is not in FR-2's rename set; without explicit ownership FR-5's grep-clean acceptance is unachievable. | FR-5 body (enumerate non-renamed files needing alias removal) | After Phase 5: `grep -rn "LeadContractorChunkExecutor" src/` returns nothing |
| R1-F7 | Data | low | Make FR-4 explicit that the installed YAML human-readable `name: Lead Contractor Workflow` (space form, audit §3) and any metrics/dashboard *labels* using the space form are re-keyed, not just the `workflow_id`. | NFR-5's `lead[-_ ]?contractor` regex matches the space form, so a leftover `name:`/label string fails the completion grep even though no FR explicitly targets it. | FR-4 body | NFR-5 grep over `.startd8/` + `dashboards/` + `startd8-mixin/` returns clean including space-form matches |
| R1-F8 | Risks | high | Reconcile FR-7's "deprecation-shim test" and NFR-5's "time-boxed deprecation shim" with v0.3's no-shim stance, and define the cross-repo landing mechanism for FR-6. v0.3 removes the deprecation window but FR-7/NFR-5 still assume a shim artifact exists; clarify whether the transient `workflow_id` alias is the only shim (no `LeadContractor*` import alias) and how 3 repos land "concurrently green" with no shared CI. | Internal contradiction: FR-5/OQ-5 say no warning scaffolding, but FR-7 mandates a test that "warns-and-resolves during the window." With no import-level alias, FR-6's atomic-landing claim is unachievable across separate repos. | FR-6, FR-7, NFR-5; §5 Phase 5 gate | Define a documented cutover runbook (order: bump SDK in consumer branches → merge SDK removal → merge consumer branches); assert a tag/commit where all three repos reference `primary-contractor` |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F9 | Risks | medium | Add a rollback requirement: if FR-5/FR-6 coordinated landing fails partway (one consumer repo not green), define how to revert the SDK removal without losing the Phase 1-3 non-breaking work. | The "land together" gate has no documented failure path; a partial cross-repo landing leaves a broken shared state with no specified recovery, contradicting NFR-3's "never left broken" goal. | New FR or NFR-3 extension | Tabletop: simulate wayfinder not green at merge time; confirm documented revert restores green without reverting Phases 1-3 |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — this is the first review round (R1); no prior untriaged suggestions exist.

#### Review Round R2 — claude-opus-4-8-1m — 2026-05-30

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-05-30 18:12:00 UTC
- **Scope**: Requirements quality, second pass — **code-grounded**. R1 (now triaged into Appendix A) reviewed the requirements against the audit; it never opened the `src/` modules. R2 reads the real code and finds two NFR-5 stragglers owned by no FR (`model_catalog.py` constants; the `lead_agent` public field) plus a cleaner shape for FR-4's alias and a needed scope decision on adjacent accidental complexity. No applied R1-F item is re-proposed.

##### Sponsor focus-ask supplement (R2 — only asks with new code evidence)

**Ask 2 — `workflow_id` migration mechanism (new code evidence).**
- **Summary answer:** The transient alias is right (R1 settled this), but the code shows it should be **one registry-level id-normalization map**, not the current dual registration.
- **Rationale:** `lead-contractor` and `primary-contractor` are *two* entry points (`pyproject.toml:101-102`) backed by *two* `__getattr__` branches (`workflows/builtin/__init__.py:76-81`) resolving the **same** class — two registry IDs for one workflow. FR-4's transient alias belongs in a single normalization map keyed `lead-contractor → primary-contractor`; then Phase-5 retirement is a one-line deletion and `list_workflows()` stops advertising one workflow twice.
- **Assumptions / conditions:** the workflow registry resolves by id; entry points are discovered at install time.
- **Suggested improvements:** See R2-F3.

**Ask 4 — Audit inventory completeness (new stragglers R1 missed by not reading code).**
- **Summary answer:** Partial — two regex-matched surfaces remain uninventoried: the `model_catalog.py` constants and the `lead_agent` public config field.
- **Rationale:** `Models.LEAD_CONTRACTOR_LEAD` / `LEAD_CONTRACTOR_DRAFTER` (`src/startd8/model_catalog.py:132-133`) are matched by NFR-5's `lead[-_ ]?contractor` regex (lowercased) yet named in no audit section and no FR; they are referenced from `lead_contractor_workflow.py:160,254,365` and `lead_contractor_models.py:72,82,87`. Separately, `WorkflowInput(name="lead_agent", description="Lead contractor agent …")` (`lead_contractor_workflow.py:251,255`) is a public field whose description string also trips the regex, and whose name disagrees with its own docstring ("Primary agent spec", `models.py:72`).
- **Assumptions / conditions:** none.
- **Suggested improvements:** See R2-F1, R2-F2.

*Asks 1, 3, 5 are addressed by applied R1 items (R1-F1/F2, R1-F5, R1-F8); R2 adds no new material there.*

##### Executive summary

- **NFR-5 is unachievable as written:** `model_catalog.py:132-133` (`LEAD_CONTRACTOR_LEAD` / `LEAD_CONTRACTOR_DRAFTER`) match the completion regex but are owned by no FR — the requirements never mention `model_catalog.py` (blocking gap, R2-F1).
- **The `lead_agent` public config field is unscoped:** FR-3 covers descriptive prose only, not a user-facing input/field **name** on the canonical `Primary` workflow whose description string also matches the regex (R2-F2).
- **FR-4's alias should be specified as a single id-normalization map**, collapsing the dual entry-point/dual-`__getattr__` registration the code currently carries (R2-F3) — simpler and one-line to retire.
- **Adjacent in-file accidental complexity** in the four `git mv` files (duplicated `fail_on_truncation` handling, 11 unused re-exports, sync/async config-parse duplication) will be visually churned by the rename diff; NFR-1 implies "no refactor," so the spec should record an explicit accept/defer decision to prevent silent scope drift (R2-F4).
- The FR-7/NFR-5 shim contradiction (R1-F8) and the alias-test gap (R1-F4) are already resolved in Appendix A — R2 does not re-raise them.

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Data | high | Extend FR-3 (or add FR-3a) to own `src/startd8/model_catalog.py`: rename `LEAD_CONTRACTOR_LEAD` → `PRIMARY_CONTRACTOR_LEAD` and `LEAD_CONTRACTOR_DRAFTER` → `PRIMARY_CONTRACTOR_DRAFTER` (L132-133) and update all referencing call sites (`lead_contractor_workflow.py:160,254,365`, `lead_contractor_models.py:72,82,87`). | These constants match NFR-5's regex but no FR names `model_catalog.py`; without an owning FR the "clean `src/` grep" acceptance cannot pass. This is the single largest gap R1 missed by reviewing docs without reading code. | New FR-3a, or FR-3 body | `grep -riE "lead[-_ ]?contractor" src/startd8/model_catalog.py` empty; suite green (constants are internal, so behavior parity holds per NFR-1) |
| R2-F2 | Interfaces | medium | Decide the fate of the public `lead_agent` config field on `PrimaryContractorWorkflow` (`WorkflowInput name="lead_agent"`, `PrimaryContractorConfig.lead_agent`): either rename to `primary_agent` accepting both names for one transient window, **or** explicitly keep it and document it as a known residual. State which in an FR. | FR-3 covers docstrings/comments, not field **names**; leaving `lead_agent` undecided lets a user-facing API name silently contradict the `Primary` rename (and its own docstring says "Primary agent spec"). The description string trips NFR-5's regex regardless. | FR-3 or a new FR; Non-goals if intentionally kept | If renamed: config accepts `primary_agent` (and legacy `lead_agent` during the window); description string regex-clean. If kept: a Non-goal line records the decision so NFR-5's allowlist can include it |
| R2-F3 | Architecture | medium | Specify FR-4's transient alias as a **single registry id-normalization map** (`{"lead-contractor": "primary-contractor", …}`) rather than retaining the second entry point; remove the `lead-contractor*` entry points and the `__getattr__` legacy branches (`workflows/builtin/__init__.py:76-81`) in Phase 5, leaving one canonical registration. *(Scope note: structural simplification adjacent to the rename — flag for explicit accept; behavior is unchanged.)* | The code carries two registry IDs for one class; folding the alias into one map makes Phase-5 retirement a one-line deletion, stops `list_workflows()` double-advertising, and removes a standing source of "which id do I use?" confusion for downstream consumers (FR-6). | FR-4 mechanism clause + §5 Phase 5 | `list_workflows()` shows `primary-contractor` once; legacy-id lookup resolves via the map while live and raises after the single map entry is deleted |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F4 | Validation | medium | Add an explicit accept/defer decision (in §4 Non-Requirements or an NFR-1 note) for the **adjacent in-file accidental complexity** in the four `git mv` files: duplicated `fail_on_truncation` legacy-flag handling (`lead_contractor_workflow.py:376-385` and `1048-1054`), 11 unused implementation_engine re-exports (`133-147`), and sync/async config-parse duplication (`433-787` vs `1025-1318`). State whether the rename PR removes these or explicitly leaves them. | NFR-1 ("behavior parity, no refactor") implies *leave them*, but the rename diff physically touches those exact lines, so an implementer faces an unspecified judgment call mid-PR. An explicit decision prevents both silent scope creep and silent NFR-1 violation, and — if accepted — captures ~90 lines of Mottainai waste while the files are already open. | §4 Non-Requirements (defer) **or** a new optional FR-10 (accept, behavior-preserving cleanup) | If deferred: a Non-goal line + a follow-up issue link. If accepted: the cleanup ships behind unchanged tests proving NFR-1 behavior parity (same inputs → same outputs) |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none remain — all R1 requirements suggestions (R1-F1…R1-F9) were triaged into Appendix A before this round. R2-F1/F2 extend the now-applied inventory work (R1-F6/F7) to the two code surfaces — `model_catalog.py` constants and the `lead_agent` field — that doc-only review could not see.

**Disagreements** (untriaged prior items this reviewer would weigh against): none.

#### Review Round R3 — composer-2.5-fast — 2026-05-30

- **Reviewer**: composer-2.5-fast
- **Date**: 2026-05-30 20:00:00 UTC
- **Scope**: Requirements quality, third pass — robustness, end-user value, accidental-complexity reduction. Endorses untriaged R2-F1–F4; adds extended alias inventory, ContextCore workflow id, capability-index scope, migration cookbook, and narrow FR-10 cleanup. Does not re-propose R1 Appendix A items.

##### Sponsor focus-ask supplement (R3 — new code evidence only)

**Ask 2 — `workflow_id` migration (ContextCore sibling id).**
- **Summary answer:** Partial — FR-4 must also migrate `lead-contractor-contextcore` → `primary-contractor-contextcore`.
- **Rationale:** `PrimaryContractorContextCoreWorkflow.metadata.workflow_id` is `"lead-contractor-contextcore"` (`lead_contractor_contextcore_workflow.py:306`), a separate registered workflow from the base primary workflow; FR-4 body names only `lead-contractor`.
- **Assumptions / conditions:** ContextCore integration uses the contextcore entry point and its distinct id.
- **Suggested improvements:** See R3-F2.

**Ask 4 — Audit inventory completeness (extended aliases + capability-index).**
- **Summary answer:** Partial — six importable `Lead*` surfaces, not four; capability-index is user-facing.
- **Rationale:** Beyond FR-5's four named aliases, `LeadContractorConfig`/`LeadContractorResult` (`lead_contractor_models.py:358-359`) and `contractors/__init__.py` export remain; `docs/capability-index/` exposes dead workflow ids to MCP consumers.
- **Assumptions / conditions:** none.
- **Suggested improvements:** See R3-F1, R3-F3.

**Ask 5 — Coordinated FR-5+FR-6 (config-key migration).**
- **Summary answer:** Endorses R2-F2 — transient dual-key accept for `lead_agent`/`primary_agent` de-risks saved configs without import aliases.
- **Rationale:** R1-F8 runbook covers Python import breaks; YAML/config dicts with `lead_agent` need a one-release parser fallback in a shared helper (both sync/async paths).
- **Assumptions / conditions:** Consumers persist workflow config with `lead_agent` key.
- **Suggested improvements:** See R3-F4 (endorses R2-F2).

*Asks 1 and 3 addressed by applied R1 items and R2 code read; Ask 4 partially extended above.*

##### Executive summary

- **Endorse R2-F1–F3 as blocking** — triage before implementation; R3 adds companion items only.
- FR-5 **four-alias list is incomplete** — add Config/Result type aliases + `contractors/__init__.py` export (R3-F1).
- FR-4 must cover **`lead-contractor-contextcore`** id, not only `lead-contractor` (R3-F2).
- FR-8 must include **`docs/capability-index/`** — primary MCP/agent discovery surface (R3-F3).
- **Endorse R2-F2/R3-F4:** rename `lead_agent` → `primary_agent` with transient dual-key accept — highest end-user value per effort.
- **Endorse R2-F4 narrowly as optional FR-10:** remove 11 IE re-exports + shared config parser; defer full sync/async merge (R3-F6).
- Add **user migration cookbook** to FR-8 for ContextCore/wayfinder kickoff (R3-F7).

##### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Data | high | Extend **FR-5** alias inventory to include `LeadContractorConfig`, `LeadContractorResult` (`lead_contractor_models.py:358-359`, `__all__:22,29`) and the lazy `LeadContractorCodeGenerator` export in `contractors/__init__.py:71-75,119` — removed in Phase 5 alongside the four named workflow aliases. | FR-5 lists four aliases; grep-clean acceptance is unachievable if Config/Result type aliases and the contractors package export survive. These files are outside FR-2's rename set. | FR-5 body (extend alias list) + acceptance | `grep -rn "LeadContractor" src/` returns nothing after Phase 5 |
| R3-F2 | Data | high | Extend **FR-4** migration set to include **`workflow_id="lead-contractor-contextcore"`** → `"primary-contractor-contextcore"` (metadata, installed YAML, dashboards/state keyed on that id). Include both ids in the transient legacy-id normalization map (R2-F3). | FR-4 names `lead-contractor` only; the ContextCore variant is a separate registered workflow (`lead_contractor_contextcore_workflow.py:306`) with its own entry point and YAML. | FR-4 migration set bullet list | Lookup by new id resolves; legacy `-contextcore` id resolves via map while live |
| R3-F3 | Interfaces | medium | Extend **FR-8** to require updating **`docs/capability-index/`** manifests (`startd8.agent.yaml`, `agent-card.json`, `mcp-tools.json`, workflow capability entries): capability_id `startd8.workflow.builtin.lead_contractor` → `…primary_contractor`, example `workflow_id`, and config field names. | These are the primary agent/MCP discovery surface; FR-8 acceptance names only CLAUDE.md + contractors README but NFR-5 grep includes all of `docs/`. | FR-8 body + acceptance | `grep -riE "lead[-_ ]?contractor" docs/capability-index/` clean; MCP schema shows `primary-contractor` |
| R3-F4 | Interfaces | high | **Endorse R2-F2:** rename public config key **`lead_agent` → `primary_agent`** on `WorkflowInput` and `PrimaryContractorConfig`; implement transient dual-key accept via a **single shared parser** (`config.get("primary_agent") or config.get("lead_agent", DEFAULT)`) used by both sync and async execution paths. Update description string to remove "Lead contractor agent" (NFR-5). | Highest end-user value: saved YAML/config dicts match the Primary rename; shared parser also reduces sync/async duplication (partial R2-F4 win). | FR-3 or new FR-3b; §5 Phase 3 or coordinated Phase 4–5 | Config with either key produces identical agent resolution one release; description regex-clean |
| R3-F6 | Validation | medium | **Endorse R2-F4 with narrow accept:** add optional **FR-10** (behavior-preserving, NFR-1 safe): (1) remove 11 unused implementation_engine re-exports (`lead_contractor_workflow.py:133-147`); (2) extract shared `_parse_primary_config(config)` replacing duplicated blocks in sync (`433-787`) and async (`1025-1318`) paths. **Defer** full sync/async path merge beyond config parse to a follow-up issue. | Explicit accept/defer prevents scope drift mid-rename-PR; the two narrow items are ~90 lines removed with zero behavior change if tests pass. | §4 Non-Requirements (defer full merge) + optional FR-10 | Same test inputs/outputs; line count drops; follow-up issue linked if deferred |
| R3-F7 | Ops | low | Add a **user migration cookbook** (half page) to FR-8: mapping table for `lead-contractor` → `primary-contractor`, `lead-contractor-contextcore` → `primary-contractor-contextcore`, `lead_agent` → `primary_agent`, import paths, and entry points — for ContextCore/wayfinder kickoff and future external users. | FR-6 requires consumer migration but provides no artifact consumers can grep against; reduces coordination friction across three repos. | FR-8 body (new subsection) | Cookbook checked against live consumer grep at kickoff; each mapping row verified |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F8 | Ops | low | Optional: rename per-run instance id prefix **`lc-` → `pc-`** (`lead_contractor_workflow.py:360,1033`) in Phase 3 — observability-only, outside NFR-5 regex scope. Document accept/defer in FR-4 or Non-Requirements. | Post-rename trace search for `lc-` returns stale lead-contractor-era runs; `pc-` aligns with Primary naming at negligible cost. | FR-4 note or §4 Non-Requirements if deferred | New runs emit `pc-*` ids; no behavior assertion change |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-F1: blocking — `model_catalog.py` constants need an owning FR before NFR-5 can pass.
- R2-F2: blocking for end-user value — `lead_agent` rename + transient dual-key accept (R3-F4 extends with shared parser).
- R2-F3: high-value — single registry id-normalization map; include both workflow ids per R3-F2.
- R2-F4: accept narrowly as FR-10 (re-exports + config parser); defer full sync/async merge.

**Disagreements** (untriaged prior items this reviewer would weigh against): none.
