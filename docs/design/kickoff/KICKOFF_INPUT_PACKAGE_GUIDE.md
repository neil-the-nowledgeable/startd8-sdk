# Kickoff Input Package — Internal Guide

**Version:** 0.1
**Date:** 2026-06-05
**Status:** Active
**Audience:** Internal — startd8-sdk team + future Claude sessions. (The package *contents* are
business-facing; this guide is about producing and operating them.)
**Templates:** [`templates/`](templates/) (project-agnostic; instantiate per project)
**Reference instance:** `strtd8/docs/kickoff/` (the StartDate app — first instantiation)
**Requirements basis:** [`../KICKOFF_REQUIREMENTS.md`](../KICKOFF_REQUIREMENTS.md) (input
classes + FR-X machinery), [`../HITM_ROLE_MODEL_REQUIREMENTS.md`](../HITM_ROLE_MODEL_REQUIREMENTS.md)
(roles/tiers), [`OBSERVABILITY_DEFAULTS_END_USER_APPLICATION.md`](OBSERVABILITY_DEFAULTS_END_USER_APPLICATION.md)
(the first industry default dataset)

---

## 1. What the package is

The **kickoff input package** is the per-project deliverable that operationalizes the kickoff
requirements: a small set of documents placed in the *consuming project* that (a) explains the
kickoff process to that project's stakeholders in business language, and (b) holds the
**value-shaped** kickoff inputs in separate files by domain, every value carrying provenance.

```
<project>/docs/kickoff/
├── KICKOFF_INTRO.md                  ← the process, in plain language + this project's posture
├── KICKOFF_INPUTS_EXPLAINED.md       ← per-domain: what we ask, why the build needs it, who provides it
└── inputs/
    ├── business-targets.yaml         ← KPIs, traction, unit economics, monetization   (class E / Group E)
    ├── observability.yaml            ← SLOs, thresholds, receivers, runbook, owners   (classes A–E)
    ├── conventions.yaml              ← stack, module paths, naming, field authorship  (class H + I language)
    └── build-preferences.yaml        ← budgets, model routing, profile, unattended    (class I)
```

**Deliberately NOT in the package** (file-shaped inputs with their own lifecycle): the data-model
contract, the assembly manifests, and content prose — those are inventoried by the project's
`ASSEMBLY_INPUTS.md` (template: [`ASSEMBLY_INPUTS_TEMPLATE.md`](ASSEMBLY_INPUTS_TEMPLATE.md)).
The package holds *values*; the inventory holds *files*. Together they are the complete kickoff
input surface.

**Role-kit connection:** the package + the inventory ARE the docs-first kit components for the
business-side roles (Customer/PO, BA, PM — HITM FR-J9, per the 2026-06-05 Q8 docs-first
decision). `conventions.yaml` is the Architect's kit centerpiece.

## 2. How it's used (lifecycle)

1. **Instantiate** — copy [`templates/`](templates/) into `<project>/docs/kickoff/`, replace
   `<…>` placeholders, delete what doesn't apply. The template set now also includes the
   **requirements/plan authoring trio**: [`templates/REQUIREMENTS_TEMPLATE.md`](templates/REQUIREMENTS_TEMPLATE.md)
   + [`templates/PLAN_TEMPLATE.md`](templates/PLAN_TEMPLATE.md) (fill-in skeletons, exact
   headings, `▷` guidance lines) and
   [`templates/HOW_TO_AUTHOR_REQUIREMENTS_AND_PLANS.md`](templates/HOW_TO_AUTHOR_REQUIREMENTS_AND_PLANS.md)
   (the team-facing guide: process, controlled vocabularies, rules of thumb, observed
   mistakes) — these produce the *extraction-source* docs the deterministic pipeline consumes
   (format spec: [`templates/REQUIREMENTS_AND_PLAN_FORMAT.md`](templates/REQUIREMENTS_AND_PLAN_FORMAT.md)).
2. **Pre-fill** — per the operator decisions (2026-06-05 Q4/Q7): observability values come from
   the matching **industry default dataset** (`config-default`); business targets and budgets
   get **LLM-drafted starter values** (`estimate`) — *never blank fields*; conventions are
   ingestion-generated (production) or team-authored (prototype mode).
3. **Collect/validate** — production posture: each domain's owning role reviews and approves;
   any human-adjusted value flips provenance to `authored`. Prototype/solo posture: the team
   plays all roles; values stay `estimate`/`config-default` until deliberately committed.
4. **Consume** — pipeline runs read the values (manifest merge at INIT, pre-seeded
   `question-answers.yaml` for RESOLVE); the pre-flight report shows every value's
   status + provenance — honest about what's real vs drafted.
5. **Converge** — as the project's business understanding firms up (e.g. strtd8's
   `BUSINESS_INSIGHTS.md`), starters get replaced and marked `authored`. The package is a living
   surface, not a one-time form.

## 3. The provenance discipline (the part that makes pre-filling safe)

| Provenance | Meaning | Set when |
|------------|---------|----------|
| `authored` | a real human decision | a person chose/confirmed the value (explicitly passing a flag counts, even at the default number) |
| `estimate` | LLM-drafted starter | pre-fill at instantiation; **never silently promoted** |
| `config-default` | deliberate industry-dataset default | dataset merge; distinguishable from an unfilled placeholder (no sentinels — `.test` TLD, env-indirection) |

Two hard rules carried from the requirements: **estimates never count as authored** in any
provisioning score, and **contacts/escalation have no LLM starter** (tier U — real people can't
be drafted; the fictional block ships flagged "replace before non-demo use").

## 4. Production vs prototype posture

| | Production (real customer) | Prototype/dogfood (e.g. StartDate) |
|---|---|---|
| Who fills values | named roles (Customer/PO, BA, PM, Architect, Ops) | the team, playing all roles (HITM solo mode) |
| Humans required to start | yes — the tier-E/U decisions | **no** — everything pre-filled |
| Gates | validation points per role | exist, honest, don't block |
| Why it still works | provenance + pre-flight report keep drafted-vs-decided visible either way | |

The prototype posture is itself a test of the process: same package, same machinery, zero
waiting on stakeholders — maximum repeatability.

## 5. Per-domain notes for instantiators

- **business-targets.yaml** — adapt metric *names* to the project's product; the shape (funnel /
  traction / unit economics / monetization / per-role goals) is what's stable. Dormant-mode
  entries (e.g. pre-monetization) are fine — declare intent early.
- **observability.yaml** — start from the closest industry dataset
  (`end_user_application` is the only one so far; new industries ⇒ new dataset docs beside it).
  The owners block is the only mandatory human replacement.
- **conventions.yaml** — the run-028 guard. In production this is generated by plan ingestion
  and validated by the Architect (kickoff master OQ-1 resolution); hand-author only when the
  team is the architect. Must agree with `build-preferences.yaml` `language`.
- **build-preferences.yaml** — never pin model version strings (model tiers resolve via
  `model_catalog`); budgets are honest fictions until someone owns them.

## 6. Maintenance

- New industry dataset → new `OBSERVABILITY_DEFAULTS_<INDUSTRY>.md` beside this guide; the
  observability template references "the matching dataset," so templates don't change.
- Template/instance drift: instances may diverge freely (they're the project's property); if a
  *structural* improvement shows up in an instance, backport it to `templates/`.
- These templates are tier-R candidates (reuse-approved after a validated instantiation + run).
