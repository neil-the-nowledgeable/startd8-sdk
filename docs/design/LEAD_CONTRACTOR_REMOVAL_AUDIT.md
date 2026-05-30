# Lead-Contractor Usage Audit (Deliverable 1)

**Version:** 1.1 (CRP Round R1 triaged & applied — all 9 S-suggestions accepted)
**Date:** 2026-05-30
**Scope:** Every `lead-contractor` / `lead_contractor` / `LeadContractor` reference across the
startd8 SDK repository (code, tests, docs, workflows, entry points, dashboards, identifiers).
**Companion:** `LEAD_CONTRACTOR_REMOVAL_REQUIREMENTS.md` (the phased-removal spec built on this).
**Method:** `grep -riE "lead[-_ ]?contractor|leadcontractor"` over `src/ tests/ docs/ scripts/`
plus `pyproject.toml`, **the full `.startd8/` tree** (not just `.startd8/workflows/` — R1-S1:
also `.startd8/task_errors/`, `.startd8/prompts/`), `dashboards/`, `startd8-mixin/`. Throwaway
`.claude/worktrees/*` copies are **excluded** (auto-cleaned agent worktrees, not source).
**Baseline (R1-S9):** capture this grep's per-scope output as a completion-record artifact *before*
work begins, so NFR-5 completion is verified as a delta (every residual hit intended), not just an
absolute count.

---

## 0. Executive summary

The Lead→Primary rename is **half-complete**. A prior "Phase 4 rename" renamed every **class**
to `Primary*` and added **4 backward-compat aliases**, but left the entire `lead` *surface*
intact: 4 module **file names**, the 4 aliases, the runtime `workflow_id="lead-contractor"`,
2 public **entry points**, installed workflow **YAMLs**, **dashboards**, and ~870 prose/comment
references across code, tests, and docs.

| Area | Files | Match lines | Nature |
|------|-------|-------------|--------|
| `src/` | 31 | 116 | 4 file names, 4 aliases, 1 `workflow_id`, rest = docstrings/comments |
| `tests/` | 21 | 268 | 2 lead-named test files; rest reference imports/ids |
| `docs/` | 73 | 415 | design docs, READMEs, lessons references |
| `scripts/` | 18 | 71 | runner scripts, dashboards provisioning |
| entry points | `pyproject.toml` | 2 (+2 ctx) | **public API** (`lead-contractor`, `lead-contractor-contextcore`) |
| installed workflows | `.startd8/workflows/` | 2 files | `lead-contractor.yaml`, `lead-contractor-contextcore.yaml` |
| dashboards | 3 | — | `dashboards/lead-contractor-progress.json`, `startd8-mixin/dashboards/lead_contractor.libsonnet`, `startd8-mixin/generated/dashboards/lead-contractor.json` |

**Key facts that shape removal (see Requirements §0):**

1. **`prime` ≠ `primary`.** `PrimeContractorWorkflow` (batch / multi-feature,
   `prime_contractor_workflow.py`) is a **separate** workflow from `PrimaryContractorWorkflow`
   (single-task lead/drafter pattern, in `lead_contractor_workflow.py`). Both survive; only
   "lead" is eliminated. The single-task workflow's canonical name is **Primary**.
2. **`Secondary`/`Tertiary` do not exist.** The "primary/secondary/tertiary" scheme was only
   *partially conceived* — only `Primary` was implemented. Removal standardizes on `Primary`;
   it does **not** introduce secondary/tertiary.
3. **`lead-contractor` is a public, downstream-consumed API.** It is a registered entry point
   and the runtime `workflow_id`; `MEMORY.md` records **ContextCore** and **wayfinder** as
   downstream consumers of "LeadContractor scripts." Hard removal is a **breaking change**.

---

## 1. Source code (`src/`) — the load-bearing surface

### 1.1 Module files named `lead_contractor*` (must be renamed)

| File | Defines (canonical) | Lead remnant |
|------|---------------------|--------------|
| `src/startd8/workflows/builtin/lead_contractor_workflow.py` | `class PrimaryContractorWorkflow` | filename; `LeadContractorWorkflow = PrimaryContractorWorkflow` (L1821); `workflow_id="lead-contractor"` (L221) |
| `src/startd8/workflows/builtin/lead_contractor_models.py` | `PrimaryContractorConfig`, `PrimaryContractorResult` | filename; module docstring |
| `src/startd8/workflows/builtin/lead_contractor_contextcore_workflow.py` | `class PrimaryContractorContextCoreWorkflow(PrimaryContractorWorkflow)` | filename; `LeadContractorContextCoreWorkflow = ...` (L539) |
| `src/startd8/contractors/generators/lead_contractor.py` | `class PrimaryContractorCodeGenerator` | filename; `LeadContractorCodeGenerator = PrimaryContractorCodeGenerator` (L669) |

### 1.2 Backward-compat aliases (the actual `Lead*` symbols still importable)

| Alias (= canonical) | Location |
|---------------------|----------|
| `LeadContractorWorkflow = PrimaryContractorWorkflow` | `lead_contractor_workflow.py:1821` |
| `LeadContractorContextCoreWorkflow = PrimaryContractorContextCoreWorkflow` | `lead_contractor_contextcore_workflow.py:539` |
| `LeadContractorCodeGenerator = PrimaryContractorCodeGenerator` | `generators/lead_contractor.py:669`; re-exported `generators/__init__.py:8,12` |
| `LeadContractorChunkExecutor = PrimaryContractorChunkExecutor` | `contractors/artisan_phases/development.py:2812` |

### 1.3 Public-surface registrations (workflow discovery)

| Item | Location | Notes |
|------|----------|-------|
| `workflow_id="lead-contractor"` | `lead_contractor_workflow.py:221` | **runtime ID** — self-reported even when loaded via the `primary-contractor` entry point. Referenced by stored state, dashboards, downstream lookups. |
| entry point `lead-contractor` | `pyproject.toml:101` | → `lead_contractor_workflow:LeadContractorWorkflow`. **⚠ Target-string hazard (R1-S4):** the dotted *module target* is invalidated by the Phase 2 `git mv` even though the entry-point *name* stays until Phase 5 — the target MUST be repointed to `primary_contractor_workflow:…` **in Phase 2** or workflow discovery breaks mid-plan (FR-9). |
| entry point `lead-contractor-contextcore` | `pyproject.toml:102` | → `...:LeadContractorContextCoreWorkflow` (same Phase-2 target-repoint hazard) |
| entry point `primary-contractor` | `pyproject.toml:99` | → `PrimaryContractorWorkflow` (the canonical replacement, already present) |
| entry point `primary-contractor-contextcore` | `pyproject.toml:100` | canonical replacement, already present |
| `__init__.py` lazy loader + `__all__` | `workflows/builtin/__init__.py:13,15,35,37,70-78` | exports BOTH `PrimaryContractorWorkflow` and `LeadContractorWorkflow` |

### 1.4 Prose / comment / docstring references (no behavior; cleanup only)

`implementation_engine/`: `models.py:5,54`, `spec_builder.py:1433`, `engine.py:5,37`,
`drafter.py:1128`, `reviewer.py:4,497`, `__init__.py:5` — all describe code as "extracted from
`LeadContractorWorkflow`."
`contractors/`: `queue.py:30,201`, `context_seed/core.py:659,1413,2428`,
`artisan_phases/development.py:1171,1220,1255`, `generators/__init__.py`, `README.md`.
Cross-refs: `forward_manifest.py:583` ("mirrors the lead-contractor path"),
`integrations/contextcore.py:1223` (example agent id `"lead-contractor"`),
`prompts/contractor_prompts.yaml:4` ("replaces the former lead_contractor.yaml"),
`prime_contractor_workflow.py:7,152`, `plan_ingestion_workflow.py:2520`,
`domain_preflight_workflow.py:427`.

### 1.5 Generated/packaging artifacts (regenerated, not hand-edited)

`src/startd8.egg-info/entry_points.txt` (L39-40,45-47) and `SOURCES.txt` — regenerate from
`pyproject.toml` + file renames; not edited directly.

---

## 2. Tests (`tests/`)

**Lead-named test files (rename + retarget):**
- `tests/unit/test_lead_contractor_workflow.py`
- `tests/unit/contractors/test_lead_contractor_executor.py`

**Other test files referencing lead-contractor imports/ids (19):** `test_edit_mode_regression.py`,
`test_truncation_detection.py`, `test_prime_task_enrichment.py`, `test_async_workflows.py`,
`test_prime_contractor_workflow_adapter.py`, `workflows/conftest.py`,
`workflows/test_prime_prompt_externalization.py`, and `contractors/`:
`test_kaizen_response_capture.py`, `test_implement_manifest.py`, `test_design_implement_handoff.py`,
`test_path_resolution.py`, `test_multi_file_edit_fixes.py`, `test_handoff_improvements.py`,
`test_artisan_prompt_improvements.py`, `test_call_graph_pipeline.py`,
`test_development_importable_modules.py`, `test_walkthrough_mode.py`, `test_pca_p0.py`,
`test_implement_prompt_externalization.py`.

---

## 3. Installed workflows, dashboards, scripts

| Artifact | Path |
|----------|------|
| Installed workflow YAML | `.startd8/workflows/lead-contractor.yaml` (`workflow_id: lead-contractor`, `name: Lead Contractor Workflow`) |
| Installed workflow YAML | `.startd8/workflows/lead-contractor-contextcore.yaml` |
| Grafana dashboard | `dashboards/lead-contractor-progress.json` |
| Mixin source | `startd8-mixin/dashboards/lead_contractor.libsonnet` |
| Generated dashboard | `startd8-mixin/generated/dashboards/lead-contractor.json` |
| Scripts | 18 files under `scripts/` (runner/provisioning) reference the id/name |
| **State keyed on `workflow_id` (R1-S1)** | `.startd8/task_errors/lead-contractor/` (+ `.cap-dev-pipe/.startd8/task_errors/lead-contractor/`); any persisted **ContextCore SpanState/state JSON** carrying `workflow_id: lead-contractor` — re-keyed in Phase 3 (Requirements FR-4) |
| **Non-obvious string forms (R1-S6)** | space form `Lead Contractor` (YAML `name:`, L120) + any `lead_contractor`/`lead-contractor` metric labels or jsonnet identifiers in the mixin — these match the NFR-5 regex and are the most likely stragglers; covered by FR-4 + FR-3 |

> **Packaging regeneration (R1-S5) + bytecode (R1-S7):** `src/startd8.egg-info/{entry_points,SOURCES}.txt`
> (§1.5) and any `__pycache__/*lead_contractor*.pyc` regenerate/clear on `pip install -e .` **after**
> the Phase 2 renames; this MUST run before the NFR-5 grep so stale artifacts don't fail it.

---

## 4. Out-of-repo (downstream) consumers — coordination required

Per `MEMORY.md`:
- **ContextCore** — LeadContractor scripts (TUI, phase3, runner).
- **wayfinder** — LeadContractor + integration backlog pipeline.

These import `LeadContractor*` symbols and/or invoke the `lead-contractor` workflow id/entry
point. **Hard removal breaks them** unless migrated first. Because startd8-sdk is **internal-only
today**, the requirements (v0.3) take the breaking change *now* and migrate these consumers in the
**same coordinated effort** (land removal + consumer updates together) rather than carrying a
multi-version deprecation window. This set is from `MEMORY.md` and MUST be re-verified live at
kickoff. See Requirements FR-6 / §0 (OQ-3).

**Cross-repo cutover (R1-S8).** Three independently-CI'd repos (startd8-sdk, ContextCore,
wayfinder) cannot merge atomically. The merge order (Requirements FR-6 runbook): (1) open consumer
branches retargeting `Lead*`→`Primary*` against the *pre-removal* SDK (green via surviving
aliases); (2) merge the SDK removal + bump each consumer's SDK pin; (3) merge the consumer
branches. Only exposure window is between the pin bump and consumer merge (import-time, caught by
the consumer branch CI). Rollback: reverting only the FR-5 removal commit restores green without
touching Phases 1–3 (Requirements NFR-3 / R1-F9).

---

## 5. Reference classification (drives phase ordering)

> **Phase numbers below match Requirements §5 v0.4 (R1-S3).** v0.3 collapsed the
> deprecate-then-remove steps; the single coordinated breaking change is Phases 4–5 together.

| Class | Examples | Behavior risk | Removal phase (Requirements v0.4) |
|-------|----------|---------------|---------------|
| **A. Prose/comments/docstrings** | §1.4 | none | **Phase 1** (safe, immediate) |
| **B. Internal file names + internal imports + entry-point *targets*** | §1.1, §1.3 (target strings) | none if done together | **Phase 2** (rename + repoint targets + regen egg-info; **no shim** — internal-only) |
| **B′. Non-renamed files carrying a `Lead*` alias/prose** | `artisan_phases/development.py:2812` (`LeadContractorChunkExecutor`) + §1.4 prose | none | **Phase 1** (prose) / **Phase 5** (alias removal) — owned by Requirements FR-5, NOT FR-2 (R1-S2) |
| **C. `workflow_id` + state/dashboards keyed on it** | §1.3 `workflow_id`, §3, task_errors, SpanState | dashboards/state re-key | **Phase 3** (id → `primary-contractor` + transient legacy alias) |
| **D. Tests** | §2 | none (retarget to canonical) | tracks Phases 1–2 |
| **E. Entry-point + alias *names* (public surface)** | §1.2 aliases, §1.3 `lead-contractor*` names | breaking | **Phase 5** (remove outright, with FR-6 consumers) |
| **F. Downstream (out of repo)** | §4 | breaks consumers | **Phase 4** (prepare) → **Phase 5** (land together; cutover runbook) |

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Extend Method/§3 to cover `.startd8/task_errors/` + ContextCore SpanState | R1 / opus-4.8-1m | Applied to **§Method** (full `.startd8/` scope) + **§3** (state-keyed row). Pairs with Req FR-4. | 2026-05-30 |
| R1-S2 | Add `development.py` as "edited-not-renamed" (holds `LeadContractorChunkExecutor`) | R1 / opus-4.8-1m | Applied as **§5 class B′**; owned by Req FR-5. | 2026-05-30 |
| R1-S3 | Reconcile §5 phase numbers with Requirements §5 | R1 / opus-4.8-1m | Applied: **§5** table re-numbered to match Req v0.4 (Phase 1 prose / 2 rename+targets / 3 id+artifacts / 4 consumer prep / 5 removal). | 2026-05-30 |
| R1-S4 | Document the entry-point target-string hazard | R1 / opus-4.8-1m | Applied to **§1.3** Notes (Phase-2 target repoint). Pairs with Req FR-2. | 2026-05-30 |
| R1-S5 | Add packaging-regeneration step + timing | R1 / opus-4.8-1m | Applied as **§3 note** (egg-info regen on `pip install -e .` post-rename). Pairs with Req FR-2/§5 Phase 2. | 2026-05-30 |
| R1-S6 | Inventory non-obvious string forms (space form, labels) | R1 / opus-4.8-1m | Applied as **§3** string-forms row. Pairs with Req FR-4/FR-3. | 2026-05-30 |
| R1-S7 | Note `__pycache__`/`.pyc` cleanup as a Phase-2 step | R1 / opus-4.8-1m | Applied as **§3 note** + Req §5 Phase 2. | 2026-05-30 |
| R1-S8 | Add cross-repo cutover runbook reference | R1 / opus-4.8-1m | Applied to **§4** (merge order + rollback). Pairs with Req FR-6/NFR-3. | 2026-05-30 |
| R1-S9 | Record a pre-work baseline grep for delta verification | R1 / opus-4.8-1m | Applied to **§Method** (baseline artifact). Pairs with Req NFR-5. | 2026-05-30 |
| R2-S1 | Inventory `model_catalog.py` (`LEAD_CONTRACTOR_LEAD`/`_DRAFTER`, L132-133) | R2 / opus-4.8-1m | **ACCEPTED.** New §1.6 "centralized constants" to add: constants match NFR-5's regex, owned by no FR. Rename target is `PRIMARY_CONTRACTOR_LEAD`/`PRIMARY_CONTRACTOR_DRAFTER` (keep `_LEAD`/`_DRAFTER` *role* suffix — these name the lead/drafter dyad, not "lead contractor"). Refs to update: `lead_contractor_workflow.py:160,254,365`, `lead_contractor_models.py:72,82,87`. Pairs with Req R2-F1. | 2026-05-30 |
| R2-S2 | Inventory the public `lead_agent` config field | R2 / opus-4.8-1m | **ACCEPTED (reframed).** Add to §1.3 public surface. Resolution (see Req R2-F2): the field **names** `lead_agent`/`drafter_agent` denote the lead/drafter roles and **stay**; only the `description="Lead contractor agent"` string (`lead_contractor_workflow.py:255`) is a prose fix (FR-3). The constant *default* it references is covered by R2-S1. | 2026-05-30 |
| R2-S3 | Note removal should collapse the dual registration | R2 / opus-4.8-1m | **ACCEPTED.** §5 class E gains a note: fold FR-4's transient alias into a single registry id-normalization map; remove the `lead-contractor*` entry points + `__getattr__` legacy branches (`__init__.py:76-81`) in Phase 5, leaving one canonical registration. Pairs with Req R2-F3. | 2026-05-30 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R2-S4 | Make NFR-5 grep explicitly assert the underscore SCREAMING_SNAKE form | R2 / opus-4.8-1m | **REJECTED — subsumed.** NFR-5's completion check is the literal `grep -riE "lead[-_ ]?contractor"`, which already matches the underscore form; R1-S9 mandates capturing that exact command's per-scope output as the baseline/completion artifact, and R2-S1 now inventories the only constant-form straggler (`model_catalog.py`). No separate acceptance clause adds coverage. | 2026-05-30 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-05-30

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-05-30 18:05:00 UTC
- **Scope**: Audit/plan completeness (S-prefix) for lead-contractor elimination. Weighted toward sponsor focus areas: audit-inventory completeness (stragglers for the NFR-5 clean grep), `workflow_id` keyed artifacts, prime-vs-primary separation, phase ordering hazards. First review round on this document.

##### Executive summary

- The audit's grep method (§Method) scans `src/ tests/ docs/ scripts/ pyproject.toml .startd8/workflows/ dashboards/ startd8-mixin/` but NFR-5 also requires a clean `.startd8/` sweep — `.startd8/task_errors/lead-contractor/` and `.startd8/prompts/` are unscanned (straggler risk).
- `LeadContractorChunkExecutor` (§1.2) lives in `artisan_phases/development.py:2812`, a file §1.1 does NOT mark for rename — the audit shows the alias but the phase table (§5) gives it no home.
- §5-E maps dashboards/YAML re-key to "Phase 4," but Requirements §5 puts the `workflow_id` migration in Phase 3 — the audit's phase numbers disagree with the requirements' phase numbers.
- The entry-point target strings (`pyproject.toml:101-102` → `lead_contractor_workflow:...`) break on the Phase 2 `git mv` but §5 class-B/C puts entry-point work in Phase 2/Phase 5 only — the *target path* edit has no explicit phase.
- §1.5 packaging artifacts (`entry_points.txt`, `SOURCES.txt`) must be regenerated post-rename; the audit notes "not edited directly" but the plan never says *when* they are regenerated.
- The audit does not inventory non-obvious string forms the NFR-5 regex will catch: `Lead Contractor` (space form in YAML `name:`), and any `lead_contractor` keys in metrics labels or mixin jsonnet.
- `__pycache__`/stale `.pyc` for renamed modules can shadow the new modules in editable installs — not noted as a cleanup step.

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Data | high | Extend the audit §Method/§3 inventory to cover `.startd8/task_errors/lead-contractor/` and any `.startd8/`-stored ContextCore SpanState JSON keyed on `workflow_id`, not just `.startd8/workflows/`. | The Method line scans only `.startd8/workflows/` but NFR-5's completion grep covers all of `.startd8/`; task_errors dirs and state files keyed on the old id are stragglers that fail NFR-5. | §Method line + new row in §3 table | Run `grep -riE "lead[-_ ]?contractor" .startd8/` and confirm every hit maps to a documented inventory row |
| R1-S2 | Architecture | high | Add `contractors/artisan_phases/development.py` to a "files needing alias/prose edits but NOT renamed" sub-list, since it holds `LeadContractorChunkExecutor` (§1.2) + prose (§1.4) but is absent from §1.1's rename set. | §5 class B (Phase 2) covers renamed files; this file is not renamed, so its alias removal has no phase assignment — a gap that defeats the NFR-5 clean grep. | New subsection under §1.2 or §5 | After removal: `grep -rn "LeadContractorChunkExecutor" src/` empty; `development.py` still builds |
| R1-S3 | Ops | high | Reconcile the audit §5 phase numbers with Requirements §5. §5-C says aliases/`workflow_id` go "Phase 3 (deprecate) → Phase 5 (remove)" and §5-E says YAML/dashboards "Phase 4," but Requirements §5 puts `workflow_id` in Phase 3 and consumer prep in Phase 4. | Divergent phase numbering between the two companion docs will mis-route work during execution; an implementer following the audit's phase column lands edits in the wrong PR. | §5 table phase column | Cross-check: every §5 phase label equals the matching Requirements §5 phase; add a note that v0.3 collapsed the deprecate-then-remove steps |
| R1-S4 | Interfaces | high | Document the entry-point *target-string* hazard: `pyproject.toml:101-102` dotted targets point at `lead_contractor_workflow:LeadContractorWorkflow`, which the Phase 2 `git mv` invalidates even though the entry-point *names* are not removed until Phase 5. | §1.3 lists the entry points but does not flag that their target module paths must change in lockstep with the rename or discovery breaks mid-plan (FR-9 violation). | §1.3 Notes column for the two `lead-contractor*` entry points | After Phase 2: `pip install -e .` then resolve both entry points without ImportError |
| R1-S5 | Ops | medium | Add a packaging-regeneration step to the plan: after the Phase 2 renames, regenerate `entry_points.txt`/`SOURCES.txt` (§1.5) via reinstall so they no longer carry `lead_contractor` paths before the NFR-5 grep runs. | §1.5 says these "regenerate … not edited directly" but no phase/gate triggers the regeneration; a stale `egg-info` fails NFR-5's `src/` grep. | §1.5 + §5 Phase 2 gate | `pip install -e .` post-rename; `grep -n lead_contractor src/startd8.egg-info/*` empty |
| R1-S6 | Validation | medium | Add a "non-obvious string forms" inventory row enumerating the space form `Lead Contractor` (YAML `name:`, §3) and any `lead_contractor` metric labels / mixin jsonnet identifiers that the NFR-5 regex will catch. | The audit counts ~870 refs but does not call out the space and label forms separately; these are the most likely NFR-5 stragglers because no class A–F bucket names them. | New row in §0 table or §3 | `grep -riE "lead[ ]contractor" .startd8/ dashboards/ startd8-mixin/` returns only documented hits |
| R1-S7 | Ops | low | Note `__pycache__`/`.pyc` cleanup for the four renamed modules as a Phase 2 step, since stale bytecode can shadow renamed modules in editable installs and produce confusing green/red flips. | Editable installs may import a cached `lead_contractor_workflow.pyc` after the source is renamed, masking import errors until cache clear. | §5 Phase 2 row or §1.5 | `find src -name '*.pyc' -path '*lead_contractor*'` empty after Phase 2 |
| R1-S8 | Risks | medium | Add a cross-repo cutover runbook reference (consumers: ContextCore, wayfinder) describing the merge order for the FR-5/FR-6 "land together" step, given no shared CI across the three repos. | §4 states hard removal breaks consumers and they must migrate "in the same coordinated effort," but provides no ordering mechanism for 3 independently-CI'd repos — the highest operational risk in the plan. | §4 (Downstream consumers) | Tabletop the merge sequence; confirm no window where a consumer references a removed symbol against the new SDK |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S9 | Validation | low | Record a baseline `grep -riE` count per scope now (pre-work) so NFR-5's "returns only the allowlist" can be verified as a delta, not just an absolute. | The audit gives aggregate counts (~870, 116, 268…) but not a reproducible per-scope baseline command output; without it, "clean grep" completion cannot distinguish intended residue from a missed straggler. | §0 executive summary | Store the baseline grep output as a completion-record artifact; diff at the end |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — this is the first review round (R1); no prior untriaged suggestions exist.

#### Review Round R2 — claude-opus-4-8-1m — 2026-05-30

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-05-30 18:12:00 UTC
- **Scope**: Code-grounded second pass. R1 (now triaged into Appendix A) reviewed the two docs against *each other* — inventory completeness, phase ordering, `workflow_id` artifacts — but never opened the actual lead-contractor `src/` modules. R2 reads the real code to find (a) inventory stragglers the audit's grep buckets miss and (b) *adjacent accidental complexity* the rename PR will physically touch and could opportunistically simplify. Going deeper, not wider — no applied R1 item is re-proposed.

##### Executive summary

- **`model_catalog.py` is uninventoried (blocking gap for NFR-5).** `Models.LEAD_CONTRACTOR_LEAD` / `LEAD_CONTRACTOR_DRAFTER` (`src/startd8/model_catalog.py:132-133`) are matched by NFR-5's `lead[-_ ]?contractor` regex (lowercased → `lead_contractor`) yet appear in **no** audit section (§1.1–§1.5); the file is named nowhere in either doc. Referenced by `lead_contractor_workflow.py:160,254,365` and `lead_contractor_models.py:72,82,87`. No FR owns it, so NFR-5's clean `src/` grep is unachievable as specified.
- **`lead_agent` is a public, user-facing config field, not just prose.** `WorkflowInput(name="lead_agent", …, description="Lead contractor agent …")` (`lead_contractor_workflow.py:251,255`) and `PrimaryContractorConfig.lead_agent` (`lead_contractor_models.py:87`). The *description string* trips NFR-5's regex; the field name already disagrees with its own docstring (`models.py:72` calls it "Primary agent spec"). The new §3 string-forms row (R1-S6) covers YAML/labels — config field **names** still fall through.
- **The dual entry-point + dual-`__getattr__` + dual-registry-id pattern is itself accidental complexity** (`workflows/builtin/__init__.py:37,76-81`; `pyproject.toml:101-102`): two registry IDs for one class. The removal is the moment to collapse it to one registry-level id-normalization — also the cleanest home for the FR-4 transient legacy-id alias (one map entry; one-line deletion to retire).
- **Adjacent in-file complexity in the four `git mv` targets**, surfaced by reading the code: duplicated `fail_on_truncation` legacy-flag handling (`lead_contractor_workflow.py:376-385` and `1048-1054`), 11 unused back-compat re-exports (`133-147`), sync/async config-parse duplication (`433-787` vs `1025-1318`). NFR-1 ("behavior parity, no refactor") implies out-of-scope, but the rename diff will visually churn these exact lines — the plan should record an explicit accept/defer decision to stop scope drift mid-PR (see requirements R2-F4).
- **Good news for the Prime-vs-Primary concern:** the workflow module carries **no vestigial Prime/Artisan routing branch** — the conflation risk is purely textual find-replace overshoot, already guarded by R1-F5. No new suggestion needed there.

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Data | high | Add `src/startd8/model_catalog.py` as a new audit inventory entry (e.g. §1.6 "centralized constants"): `Models.LEAD_CONTRACTOR_LEAD` / `LEAD_CONTRACTOR_DRAFTER` (L132-133), referenced from `lead_contractor_workflow.py:160,254,365` and `lead_contractor_models.py:72,82,87`. | The constants are SCREAMING_SNAKE, so a hyphen/space-focused eye misses them, but the NFR-5 regex matches them; no §1.x bucket names `model_catalog.py`. This is the largest gap R1 missed by not reading code — a guaranteed NFR-5 straggler with no removal phase. | New §1.6 row + §5 class A/B | `grep -riE "lead[-_ ]?contractor" src/startd8/model_catalog.py` empty after cleanup; every referencing call site resolves the renamed constant; suite green |
| R2-S2 | Interfaces | medium | Inventory the public `lead_agent` config field separately from prose: `WorkflowInput(name="lead_agent")` + `description="Lead contractor agent …"` (`lead_contractor_workflow.py:251,255`) and `PrimaryContractorConfig.lead_agent` (`lead_contractor_models.py:87`). | The new §3 string-forms row covers YAML/labels; a public input/field **name** on the canonical `Primary` workflow is an interface surface the audit still omits, and its description string trips the NFR-5 regex. The field name already contradicts its own docstring ("Primary agent spec"). | New row under §1.2/§1.3 (public surface) | After cleanup: description string is regex-clean; a rename-vs-document decision on the field name is recorded — see requirements R2-F2 |
| R2-S3 | Architecture | medium | Note in §5 (class E) that removal should **collapse the dual registration**, not just delete the lead names: `lead-contractor` and `primary-contractor` are two entry points (`pyproject.toml:101-102`) backed by two `__getattr__` branches (`__init__.py:76-81`) resolving the same class. Recommend a single registry-level id-normalization map as the home for the FR-4 transient alias. *(Scope note: structural simplification adjacent to the rename, not a behavior change — flag for explicit accept.)* | Two registry IDs for one workflow is accidental complexity the rename can erase; folding the transient alias into one map (vs perpetuating dual entry points) makes Phase-5 "drop the alias" a one-line deletion and stops `list_workflows()` advertising one workflow twice. | §5 class E note + a sentence in §1.3 | `list_workflows()` shows `primary-contractor` once; legacy-id lookup resolves via the single map; deleting that one entry fully retires the alias |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S4 | Validation | low | Make NFR-5's completion grep explicitly assert the **underscore SCREAMING_SNAKE form** (`lead_contractor`) over `src/`, not only the hyphen/space forms R1-S6 enumerated, so constants like `LEAD_CONTRACTOR_*` (R2-S1) cannot pass a hyphen-only spot check. | R1-S6 added the space form; the constant form is a *third* spelling the regex covers but the audit's per-bucket prose does not — a manual reviewer could declare "clean" prematurely. | §Method / §5 completion-grep note | Completion record shows the exact `grep -riE` output over `src/` with zero hits outside the allowlist, including underscore-form constants |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none remain — all R1 plan suggestions (R1-S1…R1-S9) were triaged into Appendix A before this round. R2-S1/S2 build on the now-applied §3 string-forms work (R1-S6) by adding the two surfaces it does not reach (the `model_catalog.py` constants and the `lead_agent` field name).

**Disagreements** (untriaged prior items this reviewer would weigh against): none — R1's applied items are sound; R2 extends rather than contests them.

#### Review Round R3 — composer-2.5-fast — 2026-05-30

- **Reviewer**: composer-2.5-fast
- **Date**: 2026-05-30 20:00:00 UTC
- **Scope**: Third pass — robustness, end-user value, adjacent accidental-complexity reduction. Builds on untriaged R2 (S1–S4); adds capability-index inventory, extended alias surfaces, ContextCore workflow id, and run-level id prefix. Does not re-propose R1 Appendix A items.

##### Sponsor focus-ask supplement (R3 — new code evidence only)

**Ask 1 — Phase green-independence (alias surfaces outside renamed files).**
- **Summary answer:** Partial — Phase 2 is green after R1-F1/F2, but Phase 5 grep can fail on aliases outside the four renamed modules.
- **Rationale:** FR-5 lists four workflow aliases; `LeadContractorConfig` / `LeadContractorResult` (`lead_contractor_models.py:358-359`, `__all__:22,29`) and lazy `LeadContractorCodeGenerator` export in `contractors/__init__.py:71-75,119` are not in FR-2's rename set or FR-5's four-alias list.
- **Assumptions / conditions:** Phase 5 acceptance grep is case-sensitive on `LeadContractor` prefix.
- **Suggested improvements:** See R3-S2.

**Ask 2 — `workflow_id` migration (ContextCore sibling + run-level ids).**
- **Summary answer:** Partial — FR-4 covers `lead-contractor` but not `lead-contractor-contextcore` or per-run `lc-` prefixes.
- **Rationale:** `PrimaryContractorContextCoreWorkflow` reports `workflow_id="lead-contractor-contextcore"` (`lead_contractor_contextcore_workflow.py:306`). Per-run instance ids use `f"lc-{uuid.uuid4().hex[:12]}"` (`lead_contractor_workflow.py:360,1033`) — outside NFR-5 regex but visible in traces/logs post-rename.
- **Assumptions / conditions:** ContextCore dashboards may filter on `-contextcore` suffix id; run ids appear in Tempo/Loki.
- **Suggested improvements:** See R3-S3, requirements R3-F2/R3-F8.

**Ask 4 — Audit inventory completeness (capability-index).**
- **Summary answer:** Partial — `docs/capability-index/` is a major user-facing straggler bucket not inventoried.
- **Rationale:** `startd8.agent.yaml`, `agent-card.json`, `mcp-tools.json` expose capability_id `startd8.workflow.builtin.lead_contractor`, example `workflow_id: "lead-contractor"`, and `lead_agent` in config schemas — matched by NFR-5's `docs/` scope but absent from audit §1–§3 and FR-8's named targets.
- **Assumptions / conditions:** MCP/agent discovery reads capability-index manifests.
- **Suggested improvements:** See R3-S1.

**Ask 5 — FR-5+FR-6 coordinated landing (config-key alias).**
- **Summary answer:** Depends — R1 runbook covers import-time breaks; saved YAML/config keys need a transient dual-key accept, not import aliases.
- **Rationale:** Cross-repo cutover handles Python symbols; in-flight workflow YAMLs and ContextCore configs still use `lead_agent`. A shared parser accepting `primary_agent` or legacy `lead_agent` de-risks the cutover without retaining `LeadContractor*` symbols (pairs with R2-F2).
- **Assumptions / conditions:** Consumers persist workflow config dicts with `lead_agent` key.
- **Suggested improvements:** Endorse R2-F2; see requirements R3-F4.

*Asks 3 is settled (R2 confirmed no Prime/Primary routing conflation); no new material.*

##### Executive summary

- **Triage R2 first** — R2-S1/S2 and R2-F1/F2 block NFR-5 (`model_catalog.py`, `lead_agent` field); R3 endorses rather than duplicates them.
- FR-5 lists **four** aliases but **six** importable `Lead*` symbols remain when counting `LeadContractorConfig`, `LeadContractorResult`, and `contractors/__init__.py` re-export (R3-S2).
- **`lead-contractor-contextcore`** workflow id and per-run **`lc-`** prefix are uninventoried FR-4 gaps (R3-S3).
- **`docs/capability-index/`** is user-facing (MCP/agent cards) and will fail NFR-5 / mislead agents unless FR-8 expands (R3-S1).
- **Endorse R2-S3/R2-F3:** single registry id-normalization map collapses dual entry-point accidental complexity.
- **Endorse R2-F4 accept-narrowly:** remove 11 unused IE re-exports + extract shared config parser — low-risk complexity win while files are open (R3-F6).
- Phase 2 gate should add explicit **entry-point smoke** after `pip install -e .` (R3-S5).

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Data | high | Add audit **§1.7 Capability manifests**: `docs/capability-index/{startd8.agent.yaml, agent-card.json, mcp-tools.json, startd8.workflow.*}` — capability_id `startd8.workflow.builtin.lead_contractor`, example configs citing `workflow_id: "lead-contractor"` and `lead_agent`. | NFR-5 grep includes `docs/`; these manifests are the MCP/agent discovery surface and are absent from §1–§3. FR-8 names CLAUDE.md + README only. | New §1.7 after §1.6 (or §3 row if §1.6 not yet applied from R2-S1) | `grep -riE "lead[-_ ]?contractor" docs/capability-index/` returns only documented residue post-cleanup |
| R3-S2 | Interfaces | medium | Inventory **model type aliases** under §1.2: `LeadContractorConfig` / `LeadContractorResult` (`lead_contractor_models.py:22,29,358-359`) and `contractors/__init__.py:71-75,119` lazy export of `LeadContractorCodeGenerator` — FR-5's "four aliases" omits these three surfaces. | Phase 5 grep-clean is unachievable if Config/Result aliases and `contractors/__init__.py` export survive; they are not in FR-2's rename set. | §1.2 table or new §1.2.1 "extended alias surfaces" | `grep -rn "LeadContractor" src/startd8/workflows/builtin/lead_contractor_models.py src/startd8/contractors/__init__.py` empty after Phase 5 |
| R3-S3 | Ops | medium | Add **§3 inventory row** for (a) `workflow_id="lead-contractor-contextcore"` (`lead_contractor_contextcore_workflow.py:306`) and (b) per-run instance id prefix `lc-` (`lead_contractor_workflow.py:360,1033`). | FR-4 migration set names `lead-contractor` only; ContextCore variant id and run-level `lc-` prefixes are observability stragglers that confuse post-rename trace search even if NFR-5 regex misses `lc-`. | §3 table + §5 class C note | ContextCore dashboards keyed on `-contextcore` id re-keyed; optional `pc-` prefix documented if renamed |
| R3-S5 | Validation | low | Add Phase 2 **entry-point smoke** to §5 gate: after `pip install -e .`, resolve all four entry points (`lead-contractor`, `primary-contractor`, both contextcore variants) via importlib/CLI without `ImportError`. | R1-F1 acceptance implies this but §5 Phase 2 gate table lists only grep + pytest — explicit smoke catches target-string typos before Phase 3. | §5 Phase 2 gate row | One-liner smoke script in completion record; all four entry points resolve |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S6 | Architecture | low | Note that **`PrimaryContractorWorkflow.metadata.name`** still carries an inline comment `# alias: "Lead Contractor Workflow"` (`lead_contractor_workflow.py:222`) — FR-3 prose cleanup should include metadata strings/comments, not only docstrings. | FR-3 acceptance scopes docstrings/comments but implementers may treat `WorkflowMetadata` fields as "code not prose"; the comment survives a docstring-only pass. | §1.4 or §5 Phase 1 | `grep -n "Lead Contractor" src/startd8/workflows/builtin/primary_contractor_workflow.py` empty post-Phase 1 |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-S1: `model_catalog.py` constants are a guaranteed NFR-5 straggler — must be inventoried before implementation.
- R2-S2: `lead_agent` public field is a user-facing interface surface separate from prose cleanup.
- R2-S3: dual registry registration should collapse to one id-normalization map — highest-value architectural simplification adjacent to the rename.
- R2-S4: completion grep must assert underscore SCREAMING_SNAKE form, not only hyphen/space forms.
- R2-F1: owning FR for `LEAD_CONTRACTOR_*` → `PRIMARY_CONTRACTOR_*` rename is blocking for NFR-5.
- R2-F2: `lead_agent` → `primary_agent` with transient dual-key accept is the right end-user migration path.
- R2-F3: FR-4 alias as single registry map — endorses R2-S3 mechanism in requirements prose.
- R2-F4: explicit accept/defer decision needed; **narrow accept** (re-exports + config parser only) recommended over full sync/async merge.

**Disagreements** (untriaged prior items this reviewer would weigh against): none.

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each Requirements doc FR/NFR to the audit section(s)/phase that address it.

| Requirement | Audit Section / Phase | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 Preserve two distinct workflows | §0 key fact 1; §5 (Prime out of scope) | Partial | Audit names Prime≠Primary but provides no negative-assertion guard that `prime_contractor_workflow.py`/its entry points stay byte-unchanged (see R1-F5, R1-S2). |
| FR-2 Rename four module files | §1.1; §5 class B (Phase 2) | Partial | Entry-point target strings (§1.3) invalidated by `git mv` have no phase assignment (R1-S4); packaging regen (§1.5) untimed (R1-S5). |
| FR-3 Purge prose/comment/docstring refs | §1.4; §5 class A (Phase 1) | Full | §1.4 enumerates the descriptive refs and the contextcore.py example id. |
| FR-4 Migrate `workflow_id` | §1.3; §3; §5 class C/E | Partial | task_errors dirs + ContextCore SpanState not inventoried (R1-S1, R1-F3); legacy-alias path untested (R1-F4); space-form `name:` not called out (R1-S6, R1-F7). |
| FR-5 Remove aliases + entry points | §1.2; §1.3; §5 class C (Phase 5) | Partial | `LeadContractorChunkExecutor` in non-renamed `development.py` has no owning phase (R1-S2, R1-F6). |
| FR-6 Migrate internal consumers (same effort) | §4; §5 class F | Partial | No cross-repo merge-order / atomic-landing mechanism for 3 repos with no shared CI (R1-S8, R1-F8). |
| FR-7 Rename/retarget lead-named tests | §2 | Partial | "Deprecation-shim test" assumes a shim artifact that v0.3 makes optional/contradictory (R1-F8). |
| FR-8 Update documentation | §1.4 (README); broader docs in §0 table (docs: 73 files) | Partial | Audit counts 415 doc matches but does not separate "API-stale" docs (must fix) from "historical record" docs (annotate only) per FR-8. |
| FR-9 Phased, independently-shippable | §5 reference classification | Partial | Phase numbers in audit §5 diverge from Requirements §5 (R1-S3); Phase 2 green-independence broken by entry-point target gap (R1-S4, R1-F1). |
| NFR-1 Behavior parity | §0 (rest = docstrings/comments, no behavior) | Full | — |
| NFR-2 History preservation (`git mv`) | §1.1 (rename instruction implied) | Full | — |
| NFR-3 No silent breakage / coordinated breakage OK | §4 | Partial | No documented rollback if coordinated landing fails partway (R1-F9). |
| NFR-4 Single source of truth | §0 key facts; §5 | Full | — |
| NFR-5 Auditable completion grep | §Method; §0 counts | Partial | Method scans only `.startd8/workflows/` not all of `.startd8/`; no reproducible per-scope baseline (R1-S1, R1-S6, R1-S9). |
| FR-NR Non-requirements (no Secondary/Tertiary; Prime untouched) | §0 key fact 2 | Full | — |

---

## Requirements Coverage Matrix — R2

Analysis only (not triage). R2 deltas vs R1, grounded in the actual `src/` code. Rows unchanged from R1 are omitted; only those whose coverage assessment moved (or whose gap is newly code-evidenced) are listed.

| Requirement | Audit Section / Phase | Coverage (R2) | Delta vs R1 / Gaps |
| ---- | ---- | ---- | ---- |
| FR-3 Purge prose/comment/docstring refs | §1.4 (+ new §1.6 if R2-S1 applied) | Partial (was Full) | **Downgraded:** §1.4 buckets descriptive prose only; the `lead_agent` field *name* + its "Lead contractor agent" description (`lead_contractor_workflow.py:251,255`) and the `model_catalog.py` constants are code identifiers, not prose, and are uncovered (R2-S1, R2-S2, R2-F1, R2-F2). |
| FR-4 Migrate `workflow_id` | §1.3; §3; §5 class C | Partial | Mechanism gap now code-evidenced: the migration should collapse the dual entry-point/dual-`__getattr__` registration into one id-normalization map rather than retaining two registry IDs (R2-S3, R2-F3). |
| NFR-1 Behavior parity | §0 | Partial (was Full) | **Downgraded:** the four `git mv` files carry adjacent accidental complexity (`fail_on_truncation` dup, unused re-exports, sync/async dup) the rename diff will touch; "no refactor" needs an explicit accept/defer call so NFR-1 is not silently violated mid-PR (R2-F4). |
| NFR-5 Auditable completion grep | §Method; §0 counts | Partial | New stragglers: `model_catalog.py:132-133` constants and the `lead_agent` description string both match the regex and are uninventoried (R2-S1, R2-S2, R2-S4, R2-F1). Underscore SCREAMING_SNAKE form should be asserted explicitly (R2-S4). |
| FR-1 Preserve two distinct workflows | §0 key fact 1; §5 | Full (confirmed) | **Upgraded confidence:** code read confirms **no vestigial Prime/Artisan routing** in the workflow module — conflation risk is purely textual, already guarded by R1-F5. |

**New surface not in any prior matrix row:** `src/startd8/model_catalog.py` (centralized `LEAD_CONTRACTOR_*` constants) and the `lead_agent` public config field — neither maps to an existing FR; R2-F1/R2-F2 propose owning FRs.

---

## Requirements Coverage Matrix — R3

Analysis only (not triage). R3 deltas vs R2 — capability-index, extended alias surfaces, ContextCore workflow id. Rows unchanged from R2 are omitted.

| Requirement | Audit Section / Phase | Coverage (R3) | Delta vs R2 / Gaps |
| ---- | ---- | ---- | ---- |
| FR-4 Migrate `workflow_id` | §1.3; §3; §5 class C | Partial | **New gap:** `lead-contractor-contextcore` id (`lead_contractor_contextcore_workflow.py:306`) and per-run `lc-` prefix (`lead_contractor_workflow.py:360`) not in migration set (R3-S3, R3-F2, R3-F8). |
| FR-5 Remove aliases + entry points | §1.2; §5 class E | Partial | **New gap:** `LeadContractorConfig`/`LeadContractorResult` + `contractors/__init__.py` export not in four-alias inventory (R3-S2, R3-F1). |
| FR-8 Update documentation | §0 docs table; new §1.7 if R3-S1 applied | Partial | **New gap:** `docs/capability-index/` manifests are user-facing MCP/agent discovery but not named in FR-8 (R3-S1, R3-F3). |
| FR-6 Migrate internal consumers | §4 cutover runbook | Partial | **Refinement:** transient `lead_agent` config-key accept (R3-F4) de-risks saved YAML independently of import-time cutover (endorses R2-F2). |

**Endorsements of R2 coverage assessments (unchanged, confirmed):** FR-3 Partial (model_catalog + lead_agent); NFR-5 Partial (regex stragglers); NFR-1 Partial (adjacent complexity needs defer/accept — R2-F4).
