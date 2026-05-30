# FR-6 Consumer-Migration Checklist (Phase 4 prep)

**Version:** 1.0
**Date:** 2026-05-30
**Companion:** `LEAD_CONTRACTOR_REMOVAL_REQUIREMENTS.md` (v0.4), `LEAD_CONTRACTOR_REMOVAL_AUDIT.md` (v1.1)
**Status:** Phase 4 prep — **OQ-6 live re-verification done**. Consumer edits **not yet staged**.

> **⚠ Headline finding — the FR-6 premise is invalidated.** The requirements (FR-6, OQ-3,
> NFR-3) assume **"ContextCore and wayfinder (the only consumers — maintainer-controlled)."**
> A live sweep of all 76 sibling repos under `~/Documents/dev/` found **9 repos with
> code-level dependencies** on the removed `Lead*` symbols — not 2. This changes the
> "land FR-5 + FR-6 together atomically" plan: you cannot atomically land across 9 repos
> with no shared CI. See **§3 Planning impact** before scheduling Phase 5.

---

## 0. OQ-6 — live re-verification method

```
grep -rIlE "LeadContractor|lead-contractor|lead_contractor" <each sibling repo>
  --exclude-dir={.git,node_modules,.venv,venv,__pycache__,.claude,dist,build,.startd8,site-packages}
```
then classified each hit as **code dependency** (imports a removed `Lead*` symbol or an old
`lead_contractor_*` module path) vs **prose/state-only** (docs, stored SpanState, dashboards —
non-breaking; the Phase-3 transient registry alias resolves id lookups until Phase 5).

`ContextCore` and `contextcore` are the **same checkout** (identical git HEAD) — counted once.
`startd8-work` / `strtd8` have **no `Lead*` symbol imports** (prose only) — not consumers.

---

## 1. Consumer inventory (re-verified)

### 1a. Code consumers — MUST migrate before/with FR-5 (breaking)

| Repo | `Lead*` symbols imported | Old module-path imports¹ | Notes |
|------|--------------------------|--------------------------|-------|
| **ContextCore** | `LeadContractorWorkflow`, `LeadContractorContextCoreWorkflow`, `LeadContractorCodeGenerator` | 8 files | Largest consumer (TUI, phase3, runner — matches MEMORY.md) |
| **wayfinder** | `LeadContractorWorkflow`, `LeadContractorContextCoreWorkflow` | 7 files | Integration backlog pipeline (matches MEMORY.md) |
| **011yBubo** | `LeadContractorWorkflow`, `LeadContractorConfig` | 1 file | **new** (not in MEMORY.md) |
| **contextcore-viewer** | `LeadContractorWorkflow`, `LeadContractorCodeGenerator` | 0 | **new** |
| **contextcore-demo-retail** | `LeadContractorWorkflow`, `LeadContractorCodeGenerator` | 0 | **new** — MEMORY.md said "PrimeContractor only"; it also imports Lead |
| **wayfinder-demo-retail** | `LeadContractorWorkflow` | 0 | **new** |
| **Gabba-Gallery-migration** | `LeadContractorCodeGenerator`, bare `LeadContractor` | 1 file | **new** |
| **contextcore-dot-me** | `LeadContractorWorkflow` | 1 file | **new** |
| **contextcore-beaver** | `LeadContractorWorkflow` | 0 | **new** |

¹ `from startd8.workflows.builtin.lead_contractor_{workflow,models,contextcore_workflow} import …`
— these **break the instant the repo installs the Phase-2 SDK** (module renamed), independent of
Phase 5. Only the SDK version pin protects them today.

### 1b. Prose / state / dashboard-only — non-breaking (optional cleanup)

`OTel`, `old_contextcore-startd8`, `contextcore-mole`, `contextcore-owl`, `online-boutique-demo`
(its 64 `startd8.…` imports are `artisan_phases`/`checkpoint`, **not** lead_contractor),
`cap-dev-pipe`, `edge-brains`, `OSS`, `startd8-work`, `strtd8`, `nemotron-challenge`, `game`.
These reference the **id string** in docs/stored state/dashboards; the Phase-3 transient registry
alias keeps id lookups resolving, so they do not break at the SDK boundary. Re-key opportunistically.

---

## 2. Per-consumer migration (identical mechanical edits)

For each code consumer in §1a, apply (behavior-preserving — same classes, canonical names):

| From (removed in FR-5 / renamed in FR-2) | To (canonical) |
|------------------------------------------|----------------|
| `LeadContractorWorkflow` | `PrimaryContractorWorkflow` |
| `LeadContractorContextCoreWorkflow` | `PrimaryContractorContextCoreWorkflow` |
| `LeadContractorCodeGenerator` | `PrimaryContractorCodeGenerator` |
| `LeadContractorConfig` | `PrimaryContractorConfig` |
| `LeadContractorResult` | `PrimaryContractorResult` |
| `from …builtin.lead_contractor_workflow import` | `from …builtin.primary_contractor_workflow import` |
| `from …builtin.lead_contractor_models import` | `from …builtin.primary_contractor_models import` |
| `from …builtin.lead_contractor_contextcore_workflow import` | `…primary_contractor_contextcore_workflow…` |
| `from …contractors.generators.lead_contractor import` | `…generators.primary_contractor import` |
| workflow id `"lead-contractor"` / `"lead-contractor-contextcore"`² | `"primary-contractor"` / `"primary-contractor-contextcore"` |

² id-string updates are **not strictly required for green** while the transient registry alias
lives (Phase 3 → removed in Phase 5), but should be done so consumers are clean before the alias drops.

**Per-repo gate:** after edits, the consumer's own suite is green against an editable install of the
`feat/lead-contractor-removal` SDK branch. Checklist row complete ⇒ that repo is "staged/green" (FR-6 acceptance).

- [ ] ContextCore — 3 symbols + 8 module-path files + id strings
- [ ] wayfinder — 2 symbols + 7 module-path files + id strings
- [ ] 011yBubo — 2 symbols + 1 module-path file
- [ ] contextcore-viewer — 2 symbols
- [ ] contextcore-demo-retail — 2 symbols
- [ ] wayfinder-demo-retail — 1 symbol
- [ ] Gabba-Gallery-migration — generator symbol + 1 module-path file
- [ ] contextcore-dot-me — 1 symbol + 1 module-path file
- [ ] contextcore-beaver — 1 symbol

---

## 3. Planning impact — decision needed before Phase 5

The 2→9 consumer expansion breaks key assumptions; **route back through the requirements**:

1. **"Land together atomically" (FR-6/NFR-3) is infeasible across 9 repos.** Recommend the
   transient registry alias (Phase 3) **and** a transient `Lead*` import-alias bridge are kept as a
   **time-boxed migration window** (days/weeks), retiring them only after all 9 repos are green —
   i.e. revert OQ-4's "transient, single coordinated change" toward a short **staged** rollout.
   This contradicts the v0.3 "no deprecation window" stance and should be an explicit re-decision.
2. **Module-path importers (ContextCore, wayfinder, 011yBubo) already break on the Phase-2 SDK.**
   **Verified: there is NO version-pin firewall.** ContextCore consumes the SDK via
   `STARTD8_SDK_ROOT` + `PYTHONPATH` (source/path-based, not `startd8==x.y`), and the SDK is
   installed **editable** in `.venv` (`Editable project location: …/startd8-sdk`). So consumers run
   against **whatever branch this working tree has checked out** — the Phase-2 module rename
   exposes module-path importers the moment they execute against this branch (acute given the 30+
   active agent worktrees sharing the tree). **Implication:** a transient `Lead*` **import-alias
   bridge** in the SDK (not just the registry id alias) is effectively **required** to keep
   path-based consumers green during the staged migration; do not rely on version pinning.
3. **MEMORY.md is stale** — update its "Downstream Projects" list from 2 to the 9 in §1a.
4. Several consumers are **demos** (`*-demo-retail`, `Gabba-Gallery-migration`, `contextcore-beaver`).
   Decide whether demos are in the coordinated gate or migrated lazily (they may tolerate brief breakage).

---

## 4. Recommended Phase 4/5 sequence (given the expansion)

1. **Keep both transient aliases live** (registry id-normalization — done in Phase 3; add a `Lead*`
   import alias bridge if FR-5 removal is staged rather than atomic).
2. Migrate consumers in dependency order: **ContextCore → wayfinder** (core), then the 7 smaller
   repos in parallel; each lands on its own branch, green against the SDK branch.
3. Only after **all 9** are green: land FR-5 (remove aliases + entry-point names) and drop both
   transient aliases in the same SDK commit (one-line deletions per R2-F3).
4. Re-run NFR-5 grep across SDK **and** each consumer; diff against the R1-S9 baseline.
