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

### Areas Substantially Addressed (>= 3 accepted)

- **Data**: 5 accepted (R1-F3, R1-F4, R2-F2, R2-F3, R2-F5)
- **Interfaces**: 3 accepted (R1-F1, R1-F6, R2-F4)

### Areas Needing Further Review (below threshold of 3)

- **Validation**: 2/3 accepted (R1-F2, R2-F1)
- **Security**: 1/3 accepted (R1-F5)

> Triage disposition: **all 11 R1+R2 F-suggestions ACCEPTED**; Appendix B empty. Bodies not yet
> rewritten — these notes are the v0.4 delta. Two accepted **as-refined** by R2's disagreement block:
> **R1-F2** (drop the "mirror `check_grounding`'s enum-hedge" AC — a `RequirementCandidate` has no
> self-reported `Grounding` enum; AC becomes "candidate text byte-unchanged; a `flags` list is
> populated") and **R1-F5** (broaden the scan, but the neutralize-vs-gate tension with plan R1-S2 is
> reconciled by plan R2-S5: blockquote-demotion passes, a surviving line-start heading fails).

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | FR-RP-2 must **own** owner-resolution; state `route()` reusable but `resolve_owner` not; add it to §Reference-Audit as "not reusable" | claude-opus-4-8-1m (R1) | ACCEPT — **high**. Requirements-side mirror of plan R1-S1 (`input_domains.resolve_owner:308-325` returns `None` off the 3 value domains). v0.4: FR-RP-2 + §Reference-Audit row. Test: `resolve_owner("security", briefs) is None`; the owned resolver returns the role. | 2026-07-02 |
| R1-F3 | FR-RP-3 must state the dedupe **similarity rule** + a **keep-both-on-uncertainty → Open Question** tie-break, so dedupe never silently drops a distinct FR | claude-opus-4-8-1m (R1) | ACCEPT — **high** (endorsed R2). Under-defined dedupe is the exact R2-S1-class clobber. v0.4: FR-RP-3. Test: two roles' *distinct* similar-normalizing FRs both survive (or → OQ); two *identical* FRs merge to one. | 2026-07-02 |
| R1-F5 | Broaden FR-RP-7's heading scan to `^#{1,6}\s` **and** setext underlines (`^=+$`/`^-+$`); neutralize-on-write | claude-opus-4-8-1m (R1) | ACCEPT — **high, as-reconciled by plan R2-S5**. Scan broadening accepted outright (`#{2,4}` misses h1/h5/h6 + setext). The "neutralize-on-write" half is reconciled with the readiness gate (plan R1-S2) via **plan R2-S5**: blockquote-demotion is the primitive; the gate fails only on a surviving line-start heading. v0.4: FR-RP-7. Test fixtures: `# x`, `###### x`, setext `Title\n---` all neutralized. | 2026-07-02 |
| R2-F2 | FR-RP-4 must handle `_YEAR` prose-flooding — prime the corpus with brief/schema temporal tokens **or** demote bare-year specifics to advisory-low | claude-opus-4-8-1m (R2) | ACCEPT — **high**. Verified `_YEAR = \b(19\|20)\d{2}\b` (`grounding_guard.py:44`) matches every year in prose ("by 2027", model IDs) → chronic false flags. v0.4: split FR-RP-4 severities — money/percent/explicit-date flag; bare year advisory-low. Test: "deliver by 2027" (brief silent) → advisory-low; "$2M ARR" still flags. | 2026-07-02 |
| R2-F3 | FR-RP-5 must carry provenance **per-FR** (inline marker or manifest keyed by `FR-<AREA>-<n>`), not one doc-level stamp | claude-opus-4-8-1m (R2) | ACCEPT — **high**. Load-bearing for P1's "never indistinguishable" — a mixed doc ($0 stub + role FR + human edit) can't be expressed doc-level. Pairs with plan R2-S3. v0.4: FR-RP-5. Test: 1 baseline + 1 role + 1 human FR carry three distinguishable per-FR markers surviving `review` + re-parse. | 2026-07-02 |
| R2-F5 | Define "primary entity" (FR-RP-1) via `PrismaModel.compound_unique_keys()` — exclude compound-`@@id` join tables | claude-opus-4-8-1m (R2) | ACCEPT — **medium**. Supplies R1-F6's concrete deterministic rule (`prisma_parser.py:100-111`). v0.4: FR-RP-1 cites it. Test: 2 domain models + 1 compound-`@@id` join model → stubs for the 2 only. | 2026-07-02 |
| R1-F4 | FR-RP-3 must define what "stable `FR-<AREA>-<n>` IDs" means across re-runs (persisted/content-hash, not re-ordinal) | claude-opus-4-8-1m (R1) | ACCEPT — **medium** (endorsed R2). CRP anchors on FR-IDs; a re-elicit renumber breaks every prior anchor. v0.4: FR-RP-3. Test: re-synthesize with one added candidate → pre-existing FR IDs unchanged. | 2026-07-02 |
| R2-F1 | FR-RP-4's owned `extract_temporal` must replicate the guard's bare-month exclusion + day-adjacency (`_MONTH_DATE`) | claude-opus-4-8-1m (R2) | ACCEPT — **high**. Requirements-side of plan R2-S2; the cited prose-safety control is private/non-reused. v0.4: FR-RP-4. Test: bare month verb → no temporal flag; "March 2027" → flag. | 2026-07-02 |
| R1-F6 | FR-RP-1 must define "primary entity" and join/compound-`@@id` handling | claude-opus-4-8-1m (R1) | ACCEPT — **medium**, **implemented via R2-F5** (`compound_unique_keys()` is the discriminator). v0.4: FR-RP-1. Test: schema with 2 domain + 1 join model yields stubs for the intended set. | 2026-07-02 |
| R2-F4 | FR-RP-8 `review` must state **where** advisory grounding flags surface — out-of-band alongside the literal bytes, machine-readable for the readiness gate (R1-S2) | claude-opus-4-8-1m (R2) | ACCEPT — **medium**. Resolves the FR-RP-7/R3-S2 vs FR-RP-4 seam: flags out-of-band (approver sees them; doc bytes stay clean for CRP). v0.4: FR-RP-8 + FR-RP-4. Test: `review` shows N flags while doc bytes contain zero flag text; the gate reads the same flags. | 2026-07-02 |
| R1-F2 | Define what "soften" does in FR-RP-4, or reduce to flag-only | claude-opus-4-8-1m (R1) | ACCEPT — **medium, as-refined by R2**. Drop the original "mirror `check_grounding`'s return shape" AC — a `RequirementCandidate` has **no** self-reported `Grounding` enum to downgrade (that path is persona-answer-specific, `grounding_guard.py:118-124`). Refined AC: **candidate text is byte-unchanged; only a `flags` list is populated** (no enum-hedge). v0.4: FR-RP-4, P3. Test: byte-compare candidate text pre/post grounding. | 2026-07-02 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet — all R1–R2 F-suggestions accepted; see Appendix A) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

*(No review rounds yet.)*

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-02

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-02 00:00:00 UTC
- **Scope**: Requirements (F-prefix) — code-grounded against live `stakeholder_panel/` + `languages/prisma_parser.py`. Focus-file asks addressed first.

##### Focus-file asks (sponsor)

**Ask 1 — Is "estimate-provenance candidate requirements for approval" a real bucket-4 boundary?**
- **Summary answer:** Yes, the boundary is real *given* one added invariant the docs do not yet state.
- **Rationale:** P1/NR-RP-2 + FR-RP-5 provenance + human-only promotion make the *artifact* bucket-3-ish (a draft), not bucket-4 authorship, consistent with `recommend.py`'s `ESTIMATE_PROVENANCE`/`disposition="draft"` precedent (recommend.py:141,149). The residual leak is that a persona-drafted FR *asserting intent* ("the system MUST support SSO") is qualitatively closer to product authorship than a scalar estimate ("$2M ARR"). The boundary holds only if every non-`<needs-owner>` candidate is provably traceable to the brief (grounding) AND no candidate is promoted without an explicit human act.
- **Assumptions / conditions:** FR-RP-4 grounding actually runs on prose (see Ask 2) and the readiness gate (R1-S2) blocks approve on ungrounded intent FRs.
- **Suggested improvements:** State a new invariant in P1: "a candidate asserting a MUST/SHALL that is neither brief-traceable nor marked `<needs-owner>` is a grounding failure, not a draft." Add to §7.

**Ask 2 — Is the owned brief+schema grounding variant (FR-RP-4) sound for requirement prose?**
- **Summary answer:** Partial — the *extractor reuse* is sound; the *corpus half* and the "soften" effect are underspecified for prose.
- **Rationale:** `extract_money`/`extract_percent` are public (grounding_guard.py:68-69) and value-normalized, and `_MONTH_DATE`/`_temporal` already drop bare month words (grounding_guard.py:39-46,72-78) — good for prose false-positive control. But `unsupported_specifics` does **exact-set** membership (grounding_guard.py:96-104): a brief "≈$2M" vs candidate "$2M" both normalize to 2000000.0 → matches, but "under 200ms"/"99.9% uptime" style specifics will flag unless the brief states the identical number. The schema half of the project corpus only helps *entity-name* checks; it contributes nothing to money/percent/temporal (schema field names carry no `$`/`%`/dates). "Advisory-then-CRP" is the right severity for the specifics extractor (it is heuristic); an *entity/field that does not exist in the parsed schema* is deterministic and should be a harder flag than a fuzzy percent.
- **Assumptions / conditions:** the paid drafting prompt actually injects the literal entity names (FR-RP-2) so the schema-reference check has ground truth.
- **Suggested improvements:** Split FR-RP-4 into two severities: (a) schema-entity/field absence = **high/deterministic** flag; (b) unsupported money/percent/temporal = **advisory**. Define "soften" concretely (see R1-F2).

**Ask 3 — Is FR-RP-3 synthesis ("dedupe + stable IDs + order + conflicts→OQ") enough?**
- **Summary answer:** No — dedupe and ID-stability are under-defined and are the two places multi-role→one-doc can silently lose or corrupt content.
- **Rationale:** "dedupe near-identical FRs (slug/normalized text)" (plan Step 5) has no similarity rule: exact-normalized match under-dedupes (two phrasings of one FR survive as duplicates), fuzzy match over-dedupes (drops a distinct FR — the exact R2-S1 failure the doc claims to prevent). "Stable `FR-<AREA>-<n>` IDs" has no cross-run definition; ordinal assignment renumbers on any re-elicit, breaking the FR-ID anchors CRP later depends on. The R2-S1 "assemble whole, never per-item overwrite" discipline *does* hold structurally (synthesis emits one doc), but only if dedupe never drops silently.
- **Assumptions / conditions:** none.
- **Suggested improvements:** R1-F3 (dedupe rule + keep-both-on-uncertainty→OQ), R1-F4 (ID stability definition).

**Ask 4 — Is CRP-as-second-gate a clean gate or a circularity risk?**
- **Summary answer:** Mild circularity; mitigated by a deterministic pre-CRP readiness gate (OQ-RP-8 should resolve to a *blocking* $0 check, not merely an advisory score).
- **Rationale:** The generator's only correctness signal is the CRP it feeds, and both can share the same model family (self-review blind spots). A $0 deterministic readiness check breaks the loop: it does not judge *quality* (CRP's job) but *readiness* (no unresolved grounding flags on intent FRs, no silently-promoted `<needs-owner>`, no injected headings survived). This is not auto-approval — it gates whether approve is even offered.
- **Assumptions / conditions:** the readiness check is deterministic and human still approves.
- **Suggested improvements:** Resolve OQ-RP-8 toward a blocking pre-CRP readiness gate; see plan R1-S2.

**Ask 5 — Value vs cost: is the `$0` baseline worth it; is paid elicitation better than single-author+CRP?**
- **Summary answer:** The `$0` baseline is worth it (it is the safe floor and the discoverability hook); the paid pass earns its cost only for the *multi-perspective coverage* a single author misses — which is unmeasured today.
- **Rationale:** The `$0` scaffold (FR-RP-1) is cheap, always-safe, and is exactly what FR-RP-9 points reflective-loop users at; keep it. The paid role pass's differentiator over "single author + CRP" is parallel missing-perspective elicitation (security/compliance/ops), but nothing in the spec *measures* whether the paid pass surfaces perspectives the baseline+CRP would not — so its value is asserted, not demonstrated.
- **Assumptions / conditions:** none.
- **Suggested improvements:** Add an OQ (or fold into OQ-RP-8's readiness score) tracking per-area coverage delta baseline→paid, so the paid pass's value is observable rather than assumed.

##### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Interfaces | high | FR-RP-2 must **own owner-resolution**; do not rely on `stakeholder_panel.input_domains.resolve_owner`. State that `route()` (answers_for-vs-value_path) is reusable but owner resolution is new. Add `resolve_owner`'s real location to §Reference-Audit with a "not reusable" note. | `resolve_owner(domain_name, briefs)` lives in `input_domains.py:308-325` (NOT `routing.py`) and calls `get_domain(domain_name)` (line 316) — for any name outside the 3 value DOMAINS (`business-targets`/`conventions`/`build-preferences`) it returns `None`, so **every** RequirementDomain (`problem`/`data`/`ux`/`ops`/`security`/`compliance`) would be skipped and no persona would ever draft. It also keys on `spec.owning_role`, which no RequirementDomain has. The §Reference-Audit table omits `resolve_owner` entirely. | §Reference-Audit table + FR-RP-2 | Unit test: an owned requirements domain resolves to its role via a `RequirementDomain`-aware resolver; assert `input_domains.resolve_owner("security", briefs)` returns `None` (proving non-reuse). |
| R1-F2 | Validation | medium | Define what "soften" does in FR-RP-4 ("flag + soften"), or reduce to flag-only. As written the mutation is untestable. | FR-RP-4/P3 say effects are "advisory (flag + soften)" but never define whether "soften" edits the candidate text, hedges a grounding enum (as `check_grounding` downgrades GROUNDED→UNCERTAIN, grounding_guard.py:122), or annotates only. An undefined text mutation on a bucket-boundary artifact is a silent-authorship risk. | FR-RP-4, P3 | AC: "a flagged candidate's text is unchanged; only its `flags`/grounding marker is set" (mirror `check_grounding`'s return shape) — testable by byte-comparing candidate text pre/post grounding. |
| R1-F3 | Data | high | FR-RP-3 must state the dedupe similarity rule and a **keep-both-on-uncertainty → Open Question** tie-break, so dedupe can never silently drop a distinct FR. | "dedupe near-identical FRs" with no rule either under-dedupes (duplicates survive) or over-dedupes (drops a real FR — the very R2-S1 clobber the doc claims to prevent). | FR-RP-3 | Test: two roles' *distinct* FRs that normalize similarly are NOT merged (both survive, or a conflict OQ is emitted); two *identical* FRs merge to one. |
| R1-F4 | Data | medium | FR-RP-3 must define what "stable `FR-<AREA>-<n>` IDs" means across re-runs (e.g. IDs persisted in the store / content-hash-derived, not re-ordinal-assigned). | Requirements are handed to CRP, which anchors suggestions on FR-IDs. If a re-elicit renumbers FRs, every prior CRP anchor breaks. | FR-RP-3 | Test: re-synthesize with one added candidate; assert pre-existing FR IDs are unchanged. |
| R1-F5 | Security | high | Broaden FR-RP-7's `^#{2,4}\s` scan to `^#{1,6}\s` **and** setext underlines (`^=+$`/`^-+$` under a text line), and prefer neutralize-on-write over reject-only. | An injected `# ` (h1), `##### ` (h5/h6), or setext heading escapes `#{2,4}` yet still corrupts the doc structure and the CRP `####`-keyed appendix scaffold FR-RP-7 exists to protect. | FR-RP-7 | Test fixtures: `# x`, `###### x`, and a setext `Title\n---` in a persona field are all neutralized before synthesis. |
| R1-F6 | Interfaces | medium | FR-RP-1 must define "primary entity" for the per-entity FR stub, and how join/compound-`@@id` models are treated. | `prisma_parser` exposes `PrismaModel` with no "primary" notion; "one stub per primary entity" is ambiguous — emitting a stub per join table (compound `@@id`) produces noise, per-model may over-generate. | FR-RP-1 | Test: a schema with 2 domain models + 1 join model yields stubs only for the intended set per the stated rule. |

**Endorsements**: none (no prior rounds).
**Disagreements**: none (no prior rounds).

#### Review Round R2 — claude-opus-4-8-1m — 2026-07-02

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-02 00:00:00 UTC
- **Scope**: Requirements (F-prefix) — adversarial second pass. Goes deeper than R1: second-order effects, symbol-reuse falsification against live `stakeholder_panel/grounding_guard.py`, `recommend_provenance.py`, `languages/prisma_parser.py`, and interactions *between* untriaged R1 items. Does not restate R1.

##### Executive summary (R2)

- **Falsified-reuse #2**: the docs' prose false-positive *control* leans on the guard's conservative temporal handling, but `_temporal`/`_MONTH_DATE`/`_QUARTER`/`_YEAR` are **private** (only `extract_money`/`extract_percent` are in `__all__`, grounding_guard.py:26-31) — FR-RP-4 writes a **new** `extract_temporal`, so the cited control does not exist unless replicated (R2-F1).
- **Deterministic prose false-positive**: `_YEAR` = `\b(19|20)\d{2}\b` (grounding_guard.py:44) flags **every** year token in requirement prose ("by 2027", roadmap dates) not verbatim in the brief — the largest, most certain false-positive vector, unaddressed by R1's Ask 2 (R2-F2).
- **Provenance is doc-level but the artifact is mixed**: FR-RP-5 stamps "the synthesized doc" (singular marker), yet one doc mixes `$0`-baseline stubs + paid role FRs + human edits — a doc-level marker cannot say *which FR is which*, defeating P1's "never indistinguishable" (R2-F3).
- **Advisory flags have no surface**: FR-RP-8 `review` renders "literal doc bytes"; FR-RP-4 flags are advisory metadata — if flags are not in the bytes the approver never sees them; if they are, they pollute the doc CRP parses (R2-F4).
- **`compound_unique_keys()` gives R1-F6 a concrete rule**: prisma_parser.py:100-111 already exposes `@@id` composites — "primary entity" is definable deterministically (R2-F5).

##### Feature Requirements Suggestions (R2)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Validation | high | FR-RP-4 must specify that the **owned** `extract_temporal` replicates the guard's bare-month exclusion + day-adjacency (`_MONTH_DATE`) and year handling — the false-positive control the docs cite is otherwise absent. | Plan Risk R1 mitigation ("the guard already drops bare month words — grounding_guard.py:39-46") references `_temporal`/`_MONTH_DATE`, which are **private** (not in `__all__`, grounding_guard.py:26-31). FR-RP-4/plan Step 2 write a *new* `extract_temporal`; nothing forces it to inherit the conservative behavior, so the cited prose-safety property is unfounded. | FR-RP-4 (§3B); cross-ref plan Risk R1 | AC: a candidate containing a bare month verb ("may improve latency") produces **no** temporal flag; "March 2027" does. Byte-compare against the private `_temporal` on a fixture corpus. |
| R2-F2 | Data | high | FR-RP-4 must handle the `_YEAR` prose-flooding case: either prime the project corpus with brief/schema-derived temporal tokens **or** demote bare-year specifics to advisory-low (keep money/percent/explicit-date as the flagging class). | `_YEAR` (`\b(19\|20)\d{2}\b`, grounding_guard.py:44) matches any year; requirement prose routinely cites years ("ship by 2027", "the 2026 roadmap", model IDs embedding 2025). Every year not verbatim in the brief becomes an "unsupported-specific" → the grounding guard chronically false-flags on exactly the prose it is meant to protect. R1's Ask 2 covered percent/ms but not the year vector. | FR-RP-4; P3 | AC: candidate "deliver by 2027" with brief silent on 2027 yields at most an advisory-low flag, never a hard/high flag; a fabricated "$2M ARR" still flags. |
| R2-F3 | Data | high | FR-RP-5 must carry provenance **per-FR** (inline marker or a provenance manifest keyed by `FR-<AREA>-<n>`), not one doc-level stamp — a synthesized doc mixes `$0`-baseline stubs, paid role FRs, and post-approve human edits. | FR-RP-5 says "the synthesized doc carry a provenance marker" (singular). But P1/FR-RP-5's own promise is "an AI/role-drafted requirement is never indistinguishable from a human-authored one" — a doc-level marker cannot express mixed provenance, so a reader cannot tell which FR is `$0` vs paid vs human. This directly weakens the load-bearing P1 boundary the focus file asks us to pressure-test. | FR-RP-5 | AC: a doc with 1 baseline stub + 1 role FR + 1 human-edited FR carries three distinguishable per-FR provenance markers that survive `review` render and re-parse. |
| R2-F4 | Interfaces | medium | FR-RP-8 `review` must state **where** advisory grounding flags surface: out-of-band alongside the literal doc bytes (not inside them), and machine-readable so the pre-CRP readiness gate (R1-S2) can consume them. | FR-RP-8 defines `review` as "$0 render of the **literal** doc that would be written"; FR-RP-4 flags are advisory metadata. If flags live only outside the bytes, the human approving via `review` never sees the ungrounded specifics; if inline, they corrupt the doc CRP parses. The seam is unspecified and is exactly the P1 approval surface. | FR-RP-8; FR-RP-4 | AC: `review` output shows N grounding flags while the literal doc bytes contain zero flag text; the same flags are readable by the readiness gate. |
| R2-F5 | Data | medium | FR-RP-1 should define "primary entity" via the available deterministic API: exclude models whose PK is a compound key over relation FKs (join tables), using `PrismaModel.compound_unique_keys()`. | R1-F6 flagged "primary entity" undefined; the parser already exposes the discriminator — `compound_unique_keys()` returns `@@id`/`@@unique` composites (prisma_parser.py:100-111), so a join model (compound `@@id` over FKs) is detectable with no LLM. FR-RP-1 can cite this rule directly instead of leaving it open. | FR-RP-1 | Test: a schema with 2 domain models + 1 compound-`@@id` join model yields entity-touching stubs only for the 2 domain models. |

**Endorsements** (prior untriaged R1 items this reviewer agrees with):
- R1-F3: dedupe with no similarity rule is the exact R2-S1 clobber risk; keep-both-on-uncertainty→OQ is the right floor.
- R1-F4: FR-ID stability is load-bearing because CRP anchors on FR-IDs; a re-elicit renumber silently breaks every prior anchor.
- R1-F5: broadening the heading scan to `^#{1,6}` + setext is necessary — but see R2 Disagreements for its tension with the R1-S2 readiness gate.

**Disagreements / refinements** (untriaged R1 items to weigh at triage):
- R1-F2 (refine, not reject): "mirror `check_grounding`'s return shape" is a partial mismatch — a `RequirementCandidate` has **no** self-reported `Grounding` enum to downgrade GROUNDED→UNCERTAIN (that path is persona-answer-specific, grounding_guard.py:118-124). The AC should be "candidate text byte-unchanged; a `flags` list is populated" **without** importing the enum-hedge semantics, else it implies a state the artifact does not have.
- R1-F5 (tension flag): "prefer neutralize-on-write (demote to blockquote)" conflicts with R1-S2's readiness-gate criterion "any injected heading only demoted (not removed) ⇒ fail approve". A `> ## x` blockquote is safe for `^`-anchored CRP `####` parsing, so demotion *should* pass — the two items must be reconciled (see plan R2-S5).
