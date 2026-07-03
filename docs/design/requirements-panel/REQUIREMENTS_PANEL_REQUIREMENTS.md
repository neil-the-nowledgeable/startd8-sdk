# Requirements Panel — Requirements

**Version:** 0.3 (Post lessons-learned hardening)
**Date:** 2026-07-02
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Plan:** `REQUIREMENTS_PANEL_PLAN.md`
**Extends / reuses (cite, don't duplicate):** the **Stakeholder Panel** persona machinery
(`stakeholder_panel/` — `persona.Persona`, `panel.StakeholderPanel.ask`, `routing.route`,
`roster.py`, `proposals.ProposalStore`, `telemetry.span`, the recommend→review→approve *pattern*),
the **Manifest Suggester** design (`../kickoff/MANIFEST_SUGGESTER_{REQUIREMENTS,PLAN}.md` — the
"role-based agents draft a prose artifact for approval" sibling), the **CRP** workflow
(`convergent-review` → `architectural-review-log`, `workflows/builtin/`), `languages/prisma_parser`
(schema grounding), the **`reflective-requirements`** skill (the loop this capability automates), the
**four-bucket separation** in `CLAUDE.md`.

> **What this is.** A **persona-driven requirements *drafting* capability** that simulates a
> stakeholder elicitation session: role-based agents (end-user, PM, ops, security, compliance,
> sponsor) each draft candidate requirements from their vantage, a synthesis assembles a coherent
> **draft requirements document**, and a human stakeholder **approves** it. It is the **third sibling**
> in the pattern — after the Stakeholder Panel (drafts scalar *value-inputs*) and the Manifest
> Suggester (drafts *screens*), this one drafts *requirements prose*. It answers "**what should we
> even be building, and what did each stakeholder forget to say?**" — the elicitation the
> `reflective-requirements` loop does by hand today.

> **What this is NOT.** It does not *decide* what the product must do. Its output is
> **estimate-provenance candidate requirements** the human owns and accepts, edits, or discards. See
> **P1 (scope lock)** — this is the load-bearing boundary.

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass (reading the live `stakeholder_panel/` code) falsified **four** first-draft
> assumptions — the two grounding ones and the "there's an apply kind" one are load-bearing. This is
> the loop working: >30% of the naive reuse plan changed at document cost, not refactor cost.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| Reuse `grounding_guard.unsupported_specifics` as the brief/schema grounding gate | `grounding_guard.py:81-89` grounds specifics against the **persona's own brief corpus** (`goals`/`constraints`/`known_positions`/`display_name`) — **not** a project brief or schema. | **FR-RP-4 owns a project-grounding variant** (`ground_requirement`) that grounds against the **problem-statement brief + parsed schema**, reusing the guard's money/percent/temporal **extractors** (`extract_money`/`extract_percent`, publicly exported) but its **own corpus**. |
| A drafted requirement is an estimate, so treat it like `recommend.py` does | `recommend.py:130-133` **deliberately suppresses** `unsupported_specifics` for value estimates (only `check_contradiction` fires) because a scalar estimate is *expected* to introduce a value the brief never stated. | **Requirements are the inverse:** a fabricated specific (`"40% faster"`, `"$2M ARR"`) with no brief/schema support **is** the failure mode. FR-RP-4 must **run** the specifics check (not suppress it) and flag/soften unsupported specifics. |
| Reuse the `manifest` proposal kind for apply (like the Manifest Suggester) | There is **no "requirements" proposal kind** anywhere (`kickoff_experience/proposals.py` `PROPOSAL_KINDS` has no requirements-doc shape); requirements are a free markdown doc in `docs/design/`, not a grammar-gated manifest. | **FR-RP-6 apply = a plain markdown file-write at human privilege** (no new proposal kind); the **second gate is CRP** (`convergent-review`), not an extractor round-trip. |
| `input_domains.py` models the "what to draft" layer directly | It models **scalar YAML field-slots** (dotted keys, composite `{target,why}` rows); requirements units are **prose sections / FR-classes**, not YAML keys. | **FR-RP-1 owns a `RequirementDomain` descriptor** (the section/FR-class → owning-role map) — the *structural analogue* of `DomainSpec`/`FieldSlot`, not a reuse of it. |

**Resolved open questions:** OQ-1 → the drafting unit is a **requirement section / FR-class**
(Problem, per-area FR blocks, NRs, OQs), routed by an `answers_for`-named area symbol (`security`/
`ops`/`data`/…). OQ-2 → **synthesis is an explicit owned step** (personas draft per-area units → a
synthesis pass assembles one coherent doc → human approves the whole), never a silent per-item
overwrite (mirrors Manifest-Suggester R2-S1). OQ-3 → **reuse** persona/routing/roster/`ProposalStore`/
`panel.ask`/telemetry; **own** the requirements-shaped draft/synthesis/grounding/apply. OQ-4 → the
**second gate is CRP**; the loop *generates* a draft that CRP then *reviews* and the orchestrator
*triages* — closing a generate→review→triage loop that dogfoods `reflective-requirements` itself.
OQ-5 → the `$0` baseline is a **deterministic template + schema scaffold** (problem table, entity-
touching FR stubs, standard NR/OQ headings), the persona-less alternative. OQ-6 → dedupe/merge is the
synthesis pass's job (§ FR-RP-3).

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK design-docs lessons + the *shipped* Manifest-Suggester CRP findings (its R1–R3,
> just triaged) before CRP. Each changed the draft:

- **[Phantom-reference audit]** — every cited symbol grepped in `stakeholder_panel/` and verified (see
  §Reference-Audit); new symbols marked *to-be-created*. Caught the two grounding-guard corrections
  (§0) — the guard does **not** do what a name-level read implied.
- **[Prune phantom scope]** — the "reuse the `manifest` apply kind" line was architecturally wrong
  (no such kind for requirements) → moved to §0 and NR-RP-3; apply is a file-write + CRP gate.
- **[Overloaded-term co-location]** — the Stakeholder Panel **owns `recommend`** (value scalars) and
  the Manifest Suggester owns `suggest` (screens). This capability lives in its **own package
  `requirements_panel/`** and names its pass **`elicit`** (`startd8 requirements elicit`) — it does
  **not** stack a third meaning onto `recommend`/`suggest`.
- **[Single-source vocabulary ownership]** — persona/roster/routing/provenance vocabulary is **owned
  by `stakeholder_panel`** (cited, non-normative snapshot here); the requirements-doc grammar
  (`## Problem`/`### FR-*`/`## Non-Requirements`/`## Open Questions`) is the **`reflective-requirements`
  skill's** convention (cited). This doc **owns only** its new vocabulary — *requirements panel*,
  *requirement candidate*, *elicitation session*, *synthesis pass*, *requirement domain*.
- **[Carry the Manifest-Suggester CRP findings forward]** — three of its just-accepted findings
  transfer directly and are pre-baked here so CRP need not re-derive them: **the whole-doc
  accumulation gap** (its R2-S1 → our FR-RP-3 synthesis, no per-item overwrite), **heading-injection
  sanitization** (its R3-S1 → our FR-RP-7, since persona free-text becomes a markdown doc CRP later
  parses by `##`/`####` headings), and **`panel.ask` not bare `Persona.ask`** (its R1-S1 → our
  FR-RP-2, for cost/telemetry/transcript).
- **[CRP steering]** — brand-new doc (least-reviewed) → CRP target. Settled (focus file): P1 scope
  lock (estimate-drafts-for-approval, not authority), CRP-as-second-gate, panel-isolation (NR-RP-1),
  own-package/`elicit` naming.

### Reference-Audit

| Symbol | Owning module (verified present) |
|--------|----------------------------------|
| `Persona` / `Persona.ask(question, *, value_path="")` | `stakeholder_panel/persona.py` |
| `StakeholderPanel.ask(role_id, question, *, value_path="")` / `.ask_all` / `.preflight_budget` / `.briefs` / `span`/`_record_cost`/transcript | `stakeholder_panel/panel.py` |
| `route(briefs, value_path, claim="")` / `persona_matches` | `stakeholder_panel/routing.py` |
| `parse_roster` / `load_roster` / `validate_roster` (`domain: stakeholders`) | `stakeholder_panel/roster.py` |
| `PersonaBrief` (`role_id`,`goals`,`constraints`,`known_positions`,`out_of_scope`,`answers_for`) / `Recommendation` / `Grounding` | `stakeholder_panel/models.py` |
| `ProposalStore(project_root, session_id)` (atomic write, `sort_keys`+`indent=2`, `latest_session`/`session_ids`/`gc_stale_proposals`, `_safe_session_component`) | `stakeholder_panel/proposals.py` |
| `unsupported_specifics` / `extract_money` / `extract_percent` (extractors reusable; **corpus is persona-brief-scoped**) | `stakeholder_panel/grounding_guard.py` |
| `check_contradiction` | `stakeholder_panel/contradiction_guard.py` |
| `span` / `_stamp_span` (`stakeholder.recommend_pass` precedent) | `stakeholder_panel/telemetry.py`, `recommend.py` |
| `convergent-review` / `architectural-review-log` workflows (the second gate) | `workflows/builtin/{convergent_review,architectural_review_log}_workflow.py` |
| schema parse (entities/relations) | `languages/prisma_parser.py` |

*New (to-be-created): `requirements_panel/` (`domains.py`, `elicit.py`, `synthesis.py`,
`grounding.py`, `sanitize.py`, `baseline.py`, `store.py`, `apply.py`), `RequirementDomain`,
`RequirementCandidate`, `startd8 requirements` CLI.*

---

## 1. Problem Statement

The `reflective-requirements` loop (draft → plan → reflect → harden → CRP) is high-value but **entirely
hand-driven**: a single author writes v0.1 alone, and the "stakeholder perspectives" (security, ops,
compliance, the end-user) are simulated only implicitly, in one head. There is no capability that
**elicits** a first draft the way a real requirements workshop would — many roles contributing in
parallel, then synthesized.

| Component | Current state | Gap for a requirements elicitor |
|-----------|--------------|---------------------------------|
| **`reflective-requirements` skill** | A human author writes v0.1, plans, reflects, hardens; CRP reviews. | No **generative** first-draft step. v0.1 is a blank page; missing-perspective gaps surface only later, in CRP. |
| **Stakeholder Panel** (`recommend_inputs`) | Personas draft **scalar value-inputs** into 3 fixed domains (`estimate` provenance, approve-gated). | Drafts *values*, not *requirements prose*. No section/FR-class drafting, no synthesis into a doc. |
| **Manifest Suggester** (design-only) | Personas draft **screens** (pages/views prose), grounded in schema, applied via the `manifest` kind. | Drafts *structure*, not *intent*. Blessed template but a different artifact + apply seam. |
| **CRP** (`convergent-review`) | Multi-round **review** of an *existing* requirements+plan doc; appends to Appendix C; orchestrator triages. | **Review-only** — critiques a doc that must already exist. Nothing generates the doc it reviews. |
| **Schema** (`prisma/schema.prisma`) | The entities the app stores. | A deterministic grounding source for data-touching FRs — unused for drafting requirements. |

**What should exist:** a **persona-driven elicitation capability** that (a) deterministically (`$0`)
scaffolds a requirements **baseline** from the brief + schema, (b) lets **stakeholder roles** each
draft **candidate requirements** in the areas they own (security → security FRs, ops → ops/validation
FRs, end-user → UX FRs, …), (c) **synthesizes** the contributions into one coherent draft, grounded in
the brief + schema, and (d) runs a **draft → review → approve** loop whose output is a markdown
requirements doc the human confirms — then hands straight to **CRP** as the external second gate.
It never authors the *real* product intent (bucket-4); it produces a **starting draft**.

---

## 2. Guiding Principles

- **P1 — Scope lock: draft-for-approval, never authority (bucket boundary).** Requirements express
  *what the company wants built* — near bucket-4. This capability produces **estimate-provenance
  candidate requirements** the human **owns and approves**; it is an **elicitation simulator / starting
  draft generator**, never the source of truth for what the product must do. "High enough quality to
  accept as-generated" changes the **edit burden**, never whether the human approval gate exists. Every
  candidate carries a provenance marker; no requirement is silently promoted.
- **P2 — Mirror the panel *pattern*, own the engine.** Same role-based *draft → synthesize → review →
  approve* loop and provenance discipline, but a **separate** capability/CLI and a **different artifact**
  (a requirements markdown doc, grounded by brief+schema, gated by **CRP** — not a scalar splice, not an
  extractor round-trip).
- **P3 — Dual grounding (brief + schema).** Every drafted requirement is grounded **twice**: intent
  against the **problem-statement brief**, and any data-touching specific against the **parsed schema**.
  A requirement asserting an unsupported money/percent/date specific, or naming a non-existent entity,
  is **flagged/softened** before synthesis (P3 is advisory-then-CRP, not a hard block — CRP is the
  authoritative gate).
- **P4 — Propose, then human-apply (inherited floor).** The loop drafts and synthesizes; the human
  approves; the durable write is a plain markdown file at human privilege. The loop never writes a
  final doc unprompted; MCP read/preview-only (CLI is the sole writer, per the Concierge precedent).
- **P5 — Reuse, don't reimplement.** persona/routing/roster/`ProposalStore`/`panel.ask`/telemetry all
  exist and are CRP-hardened — this adds *sequencing, a requirements-domain descriptor, synthesis,
  project-grounding, and CRP hand-off*, not new persona/panel engines.
- **P6 — Dogfood the loop.** The capability *generates* a draft that `reflective-requirements`'s own
  CRP step then *reviews* and the orchestrator *triages* — the same generate→review→triage loop it
  automates, run on its own output.

---

## 3. Requirements

### A. Elicit candidate requirements

- **FR-RP-1 — `$0` deterministic baseline (persona-less, schema+brief grounded).** From the brief +
  on-disk schema, deterministically scaffold a **requirements baseline**: a Problem-Statement gap table,
  an **entity-touching FR stub per primary entity** (grounded in `prisma_parser`), and the standard
  `## Non-Requirements` / `## Open Questions` headings. This is the **"manifest suggester without a
  designated persona"** alternative the sponsor raised — always cheap, always safe, lower value; it runs
  with **no LLM**. It never invents intent — stubs are marked `<needs-owner>` placeholders.
- **FR-RP-2 — Role-informed drafting (paid, opt-in), via `StakeholderPanel.ask`.** For each requirement
  **domain** (§FR-RP-1's areas + roster-owned areas), route to the owning persona via `routing.route`
  and draft candidate requirements through **`StakeholderPanel.ask(role_id, prompt, value_path=area)`**
  — **not** a bare `Persona.ask` (which bypasses cost tracking, transcript, budget preflight, and OTel
  spans; verified `panel.py` vs `persona.py`). Routing is **bounded** like the panel: the owning role
  for the area if present, else a high-confidence `answers_for` match, else **skip the area** — never a
  loose assignment. The drafting prompt carries the **brief + the literal declared entity names** (so a
  data-touching FR references real entities verbatim).
- **FR-RP-3 — Synthesis pass (assemble one coherent doc; no silent overwrite).** A dedicated
  **synthesis** step merges every approved-for-synthesis candidate into **one** requirements document:
  dedupe near-identical FRs across roles, assign stable `FR-<AREA>-<n>` IDs, order by area, and resolve
  cross-role conflicts into an **Open Question** (never by dropping one silently). This is the analogue
  of the Manifest-Suggester's accepted **R2-S1 accumulation finding** — the artifact is assembled whole,
  not clobbered one candidate at a time.

### B. Grounding & safety

- **FR-RP-4 — Project-grounding guard (brief + schema; owned, not the panel's).** A **`ground_requirement`**
  check grounds each candidate against **the project brief corpus + the parsed schema** (not the
  persona's own brief). It **reuses** `grounding_guard.extract_money`/`extract_percent` (+ a temporal
  extractor) but with a **project corpus**, and — unlike `recommend.py` — it **runs** the
  unsupported-specifics check (a fabricated `"40% faster"`/`"$2M ARR"` with no brief/schema support is
  flagged). A data-touching FR naming an entity/field absent from the schema is flagged. Effects are
  **advisory** (flag + soften), with CRP as the authoritative gate (P3).
- **FR-RP-5 — Provenance, never silently promoted.** Every candidate and the synthesized doc carry a
  **provenance** marker (`$0`-baseline vs `estimate`-role-drafted, with role_id + model + session), so an
  AI/role-drafted requirement is never indistinguishable from a human-authored one; human approval is the
  sole promotion gate (P1/P4). Reuse the panel's `ESTIMATE_PROVENANCE`/`panel_origin` stamping shape.
- **FR-RP-6 — Approve = markdown file-write at human privilege + CRP hand-off (no new proposal kind).**
  An approved synthesized draft is written to `docs/design/<feature>/<FEATURE>_REQUIREMENTS.md` (v0.1)
  by the **CLI** (sole writer), then the loop **offers CRP** (`/new-cnvrg-rvw-prmpt` dual-doc) as the
  external second gate. There is **no** requirements proposal/grammar kind (unlike the Manifest
  Suggester); the durable write is a plain file, the gate is CRP.
- **FR-RP-7 — Heading-injection sanitization (before synthesis and write).** Every persona free-text
  field is scanned for a line matching `^#{2,4}\s` (a markdown heading) before it enters the synthesized
  document; such lines are **rejected or neutralized** so a persona cannot smuggle an unreviewed
  `## Non-Requirement` / `#### Review Round` / `## Appendix` section into the doc (which would corrupt
  both the requirements structure and the **CRP appendix scaffold** the doc is later handed to). This is
  the Manifest-Suggester's accepted **R3-S1** finding applied to this project's markdown surface.

### C. The loop & surface

- **FR-RP-8 — draft → synthesize → review → approve (mirror the panel *pattern*, own the engine).** A
  **separate** CLI surface (`startd8 requirements`): `elicit` (`$0` baseline + optional `--roles` paid
  pass), `synthesize` (`$0` assemble), `review` (`$0` render of the **literal** doc that would be
  written), `approve`/`reject` (→ file-write + CRP offer). Staged out-of-band in `store.py` (mirror
  `ProposalStore`'s shape). A stale session (the target doc was created meanwhile) is detected and the
  approve refuses rather than clobbering.
- **FR-RP-9 — Discoverable from the `reflective-requirements` entry point.** When a user invokes the
  reflective loop (or the Concierge surfaces a "no requirements doc yet" gap), point at
  `startd8 requirements elicit` as the guided way to produce v0.1 — so the capability is discoverable at
  the moment of need. Presentation-only.

---

## 4. Non-Requirements

- **NR-RP-1 — Not fused into the Stakeholder Panel's value pass.** Separate capability, separate CLI;
  the panel stays scalar-value-only (its clean abstraction is preserved).
- **NR-RP-2 — Not the source of product truth (bucket-4).** It drafts *candidate* requirements for human
  approval; the *real* intent is the user/company's (P1). It is not an autonomous product manager.
- **NR-RP-3 — No new proposal kind / grammar / write engine.** Approve is a plain markdown file-write;
  no `PROPOSAL_KINDS` addition, no extractor. (Contrast the Manifest Suggester, which rides the
  `manifest` kind — requirements have no such kind and need none.)
- **NR-RP-4 — Does not replace CRP.** It *generates* the draft CRP reviews; CRP remains the external
  second gate and is not reimplemented here.
- **NR-RP-5 — Not a planning/implementation generator.** It drafts *requirements*, not the plan
  (`implementation_engine`) or code (Prime/Micro-Prime). The plan is the reflective loop's Phase 2.
- **NR-RP-6 — Not autonomous.** The loop never writes a final doc unprompted; every doc is a
  human-approved, provenance-marked draft.
- **NR-RP-7 — Not polyglot-specific.** Grounds against the Python-path `prisma` schema; the drafted
  requirements are language-neutral prose.

---

## 5. Open Questions

*The 6 v0.1 OQs were resolved by the planning pass — see §0. Remaining for CRP:*

- **OQ-RP-1 — RESOLVED** → drafting unit = requirement **section / FR-class**, routed by an
  `answers_for`-named area symbol.
- **OQ-RP-2 — RESOLVED** → synthesis is an **owned step**; the doc is assembled whole (no per-item
  overwrite).
- **OQ-RP-3 — RESOLVED** → reuse persona/routing/roster/store/`panel.ask`/telemetry; own
  draft/synthesis/grounding/apply.
- **OQ-RP-4 — RESOLVED** → the second gate is **CRP**; the loop generates → CRP reviews → triage.
- **OQ-RP-5 — RESOLVED** → `$0` baseline = deterministic template + schema scaffold (persona-less).
- **OQ-RP-6 — RESOLVED** → dedupe/merge is the synthesis pass's responsibility.
- **OQ-RP-7 — OPEN (for CRP)** → the **roster for elicitation**: reuse the shipped reviewer-roles
  roster fixture shape, or ship a curated `requirements-stakeholders.yaml` (end-user/PM/ops/security/
  compliance/sponsor) as a default? (Leaning: ship a default, `answers_for`-keyed on FR areas.)
- **OQ-RP-8 — OPEN (for CRP)** → **acceptance quality signal**: is "accept as-generated" purely human
  judgment, or does the loop attach a *readiness score* (e.g. coverage of the 7 CRP areas + grounding
  flag count) to inform the human — without ever auto-approving? (Leaning: advisory readiness score,
  never a gate.)

---

*v0.1 — Draft (pre-planning): assumed broad panel reuse incl. the grounding guard and an apply kind.*

*v0.2 — Post-planning self-reflective update. Planning (live-code read) falsified 4 assumptions: the
grounding guard is persona-brief-scoped (own a project variant), `recommend.py` suppresses the
specifics check (requirements must run it), there is no requirements apply kind (file-write + CRP gate),
and requirement "domains" are prose sections not YAML slots (own a `RequirementDomain`). All 6 v0.1 OQs
resolved; 2 new OQs opened for CRP.*

*v0.3 — Post lessons-learned hardening. Applied phantom-reference-audit (§Reference-Audit; caught the
grounding-guard corrections), prune-phantom-scope (dropped the apply-kind → NR-RP-3), overloaded-term
(own package + `elicit`, not `recommend`/`suggest`), single-source vocabulary ownership, and carried
three just-accepted Manifest-Suggester CRP findings forward (R2-S1 synthesis, R3-S1 sanitization, R1-S1
`panel.ask`). CRP steering → focus file. Ready for CRP.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to
Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or
Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that
stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items
  already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest
  existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it
  in an **Endorsements** section instead of restating it.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or
  Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same
  idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

*(No review rounds yet.)*
