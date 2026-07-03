# Manifest Suggester — Requirements

**Version:** 0.3 (Post lessons-learned hardening)
**Date:** 2026-07-02
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Plan:** `MANIFEST_SUGGESTER_PLAN.md`
**Extends / reuses (cite, don't duplicate):** the **Stakeholder Panel / Teian** value-recommendation
pass (`stakeholder_panel/`, the persona/roster/recommend→review→approve/provenance/grounding pattern to
*mirror*), the **manifest-authoring path** (`manifest_extraction/` pages/views extractors + the `manifest`
proposal kind in `kickoff_experience/proposals.py`), `languages/prisma_parser` (schema grounding),
`RED_CARPET_WIZARD_DRIVER`/advisor (where the "Your screens" gap surfaces), the **four-bucket separation**
in `CLAUDE.md`.

> **What this is.** A **stakeholder-informed, schema-grounded suggester** that **drafts candidate screens**
> (pages/views) for the human to **approve** — the manifest analogue of Teian's value-recommendation pass.
> Same "role-based agents draft content for approval" loop; the recommendation *type* is a pages/views
> **authoring-contract prose source** (not a scalar value-input field), applied through the **existing**
> `manifest` proposal kind. It answers "**which screens does my product need?**" — the decision the kickoff
> leaves entirely to hand-authoring today.

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass caught a **redundancy landmine** and sharpened the whole capability: a schema→CRUD
> baseline (the draft's core) would **duplicate what the deterministic `$0` cascade already builds**. The
> real, non-redundant value is **composite views + non-entity content pages** — which is also exactly what
> stakeholder *roles* are good at proposing.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| A schema-grounded **CRUD-per-entity** baseline is the core (FR-MS-1) | `pages.yaml` is for **owned, non-entity** pages (`pages_generator.py`); **entity CRUD is auto-generated from the schema** by the cascade. A CRUD baseline duplicates `$0` work. | **FR-MS-1 reframed:** suggest **composite views** (dashboard/board/workspace over entities) + **non-entity pages**, NOT CRUD. Schema-grounding = reference real entities *inside* composites. |
| Baseline and role-informed are separate tiers | Both target the same non-obvious composite/content screens. | **FR-MS-1/2 merge:** the `$0` baseline shrinks to a groundable starter dashboard; the paid role pass adds the rest. |
| "Reuse the panel infra" broadly | `persona`/`routing`/`roster` are **generic** (keyed on a `value_path`-like symbol) → reusable; but `recommend`/`input_domains`/`recommend_apply`/`grounding_guard` are **value-scalar-coupled** → NOT reusable. | **FR-MS-2/7 narrowed:** reuse persona/routing/roster + the *pattern*; own the manifest-shaped recommend/apply/grounding. |
| The `manifest` kind may need a dest hint (OQ-2) | `_apply_manifest` takes **prose `source` only** and server-derives the dest (round-trip-gated, no-clobber). | **OQ-2 resolved:** approved screen → a `manifest` proposal with `source` = prose. No new apply path (FR-MS-5). |

**Resolved open questions:** OQ-1 → views = `view: <name>` + `Kind ∈ {dashboard/board/workspace}`, pages =
`## Pages` (markdown the extractor round-trips). OQ-2 → the `manifest` kind takes prose, server-derives
dest. OQ-3 → persona/routing/roster reusable; recommend/apply/grounding are value-coupled → own them.
OQ-4 → model screens as a `value_path`-like symbol (`views`/`pages`); a design/PM persona owns it (roster
*content*, no new grammar). OQ-5 → baseline = a starter dashboard over primary entities (composite, not
CRUD). OQ-6 → dedupe by reading the live `views.yaml`/`pages.yaml`.

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK design-docs lessons before CRP:

- **[Prune phantom scope]** — *fired in planning:* the schema→CRUD baseline was architecturally wrong
  (duplicates the deterministic `$0` cascade). Already moved out of FR-MS-1 → the baseline is composites/
  non-entity pages only (recorded in §0, NR-3a).
- **[Overloaded-term co-location]** — the panel **owns `recommend`** (value scalars). The suggester lives
  in its **own package `manifest_suggester/`** and names its pass **`suggest`** (`startd8 screens suggest`)
  — it does **not** stack a second meaning onto the panel's `recommend`. (See FR-MS-7.)
- **[Single-source vocabulary ownership]** — the persona/roster/routing/provenance vocabulary is **owned by
  `stakeholder_panel`** (cited, non-normative snapshot here); the pages/views prose grammar is owned by the
  **authoring contract / `manifest_extraction`**; the `manifest` proposal kind by `proposals.py`. This doc
  **owns only** its new vocabulary — *manifest suggester*, *screen candidate*, *composite/non-entity screen*.
- **[Phantom-reference audit]** — every named symbol grepped + verified (see §Reference-Audit); new symbols
  marked to-be-created.
- **[CRP steering]** — brand-new doc (least-reviewed) → CRP target. Settled (focus file): propose-confirm
  floor + reuse-the-`manifest`-kind, **no-CRUD-baseline** (planning-settled), panel-isolation (NR-1).

### Reference-Audit

| Symbol | Owning module (verified present) |
|--------|----------------------------------|
| `persona.Persona.ask(question, value_path)` / `routing.route` / `routing.persona_matches` / `roster` | `stakeholder_panel/` |
| `_apply_manifest` (prose `source` → server-derived dest, round-trip-gated) / `PROPOSAL_KINDS` | `kickoff_experience/proposals.py` |
| `extract_pages` / `extract_views` (`view: <name>` + `Kind ∈ {dashboard/board/workspace}`) | `manifest_extraction/extractors.py` |
| entity CRUD auto-gen; `pages.yaml` = owned non-entity pages | `backend_codegen/pages_generator.py` |
| schema parse (entities/relations) | `languages/prisma_parser.py` |
| `CONVENTION_PATHS` (pages/views dest) | `wireframe/inputs.py` |

*New (to-be-created): `manifest_suggester/` (`candidates.py`, `grounding.py`, `suggest.py`, `store.py`),
`ScreenCandidate`, `startd8 screens` CLI.*

---

## 1. Problem Statement

The kickoff surfaces a "Your screens" gap (the portal example sat at 2/3, needing "add at least one page"),
but **nothing helps the user decide *which* screens their product needs.** Today that is pure
hand-authoring.

| Component | Current state | Gap for a screen suggester |
|-----------|--------------|----------------------------|
| **Manifest authoring** (`manifest_extraction` + the `manifest` proposal kind) | The user hand-writes authoring-contract prose (## Pages / ## Views) → the extractor turns it into `pages.yaml`/`views.yaml`; applied via the `manifest` proposal (round-trip + dest-confined). | No help deciding *which* pages/views to write. The user faces a blank grammar with no schema-aware or role-aware starting point. |
| **Stakeholder Panel / Teian** (`stakeholder_panel/`) | Role-based personas draft **scalar values** for the 3 value-input domains (strict parser + `estimate` provenance), reviewed + approved. | **Deliberately excludes screens** — a page is a structural manifest, not a scalar value; fusing it in would break the panel's clean abstraction (NR). |
| **Deterministic `$0` cascade** | Builds a working app *from* an approved `pages.yaml`/`views.yaml` (CRUD, HTMX, etc.). | Builds *from* a manifest; it does not decide *what screens should exist*. |
| **Schema** (`prisma/schema.prisma`, `languages/prisma_parser`) | The entities the app stores. | A rich, deterministic grounding source for candidate screens — currently unused for suggesting them. |

**What should exist:** a **separate capability on the manifest path** that (a) reads the schema to propose
a **schema-grounded baseline** of candidate screens, (b) lets **stakeholder roles** (PM/design/ops)
propose **non-obvious** screens beyond the entity baseline (a dashboard, a signup funnel, an admin page),
and (c) runs a **draft → review → approve** loop that outputs authoring-contract prose the human confirms,
applied via the existing `manifest` proposal kind — never authoring the screens' real content (bucket-4).

---

## 2. Guiding Principles

- **P1 — Mirror Teian, don't fuse into it.** Same role-based *draft → review → approve* loop and provenance
  discipline, but a **separate** capability/CLI and a **different recommendation type** (a manifest prose
  source, applied via the `manifest` kind, gated by the *extractor round-trip* — not a scalar splice).
- **P2 — Schema-grounded.** Every suggested screen references **real entities** from the on-disk schema
  (`prisma_parser`); a screen naming a non-existent entity is rejected (a grounding guard) before it can
  reach the round-trip-gated `manifest` apply.
- **P3 — Bucket-1 authoring only.** It proposes **which screens + their structure** (the manifest), never
  the screens' **real content** (bucket-4 — the user/company's). It does not change what the cascade builds.
- **P4 — Propose, then human-apply (inherited floor).** The loop drafts; the human approves each screen;
  the durable write is the existing `manifest` proposal at human privilege. The loop never writes; MCP
  read-only.
- **P5 — Reuse, don't reimplement.** The extractor, the `manifest` proposal kind + round-trip +
  dest-confinement, the persona/roster infra, and the schema parser all exist — this adds *sequencing,
  grounding, and a manifest-shaped recommendation*, not new engines.

---

## 3. Requirements

### A. Suggest candidate screens

- **FR-MS-1 — Schema-grounded *composite* suggestions (NOT CRUD)** *(reframed by planning)*. From the
  on-disk schema, deterministically (`$0`) propose a **starter composite** — a **dashboard view** over the
  primary entities — emitted as authoring-contract prose (`view: <name>` + `Kind: dashboard`). It does
  **NOT** propose entity-CRUD pages: **entity CRUD is already auto-generated by the cascade**; `pages.yaml`/
  `views.yaml` are for **composite views + non-entity content pages**. Schema-grounding means the composite
  references **real entities**, not that it enumerates CRUD.
- **FR-MS-2 — Role-informed suggestions (paid, opt-in), reusing persona/routing.** Reusing the
  stakeholder-panel **`persona` + `routing` + `roster`** (generic, keyed on a `value_path`-like symbol —
  *not* the value-domain `recommend`/`input_domains`, which stay scalar-only), a **PM/design/ops** persona
  drafts **non-obvious** composites/pages beyond the starter (a conversion funnel, an admin console, a
  settings page), **grounded in the entity facts** (the prompt carries the real entity list). Routing is
  **bounded** like the panel: the owning role for the screens symbol (`views`/`pages`) if present, else a
  high-confidence `answers_for` match, else skip — never a loose assignment.
- **FR-MS-3 — Only suggest what's missing.** The suggester proposes screens **not already present** in the
  live `pages.yaml`/`views.yaml` (dedupe against the current manifest), so it augments rather than
  duplicates. A screen already authored is left alone.

### B. Grounding & safety

- **FR-MS-4 — Grounding guard (schema-anchored).** Every suggested screen must reference **only declared
  entities/fields** from the parsed schema; a suggestion naming an unknown entity is **rejected** with a
  reason (mirrors the panel's grounding guard), before it can reach the `manifest` apply's round-trip gate.
- **FR-MS-5 — Round-trip-gated apply via the `manifest` kind.** An approved suggestion is applied **only**
  through the existing `manifest` proposal kind — the extractor round-trip + dest-confinement + no-clobber
  are the durable safety net (no new write path). A suggestion whose prose fails extraction is rejected at
  apply, not silently written.
- **FR-MS-6 — Provenance, never silently promoted.** A suggested screen carries a **provenance** marker
  (schema-derived baseline vs role-estimated) so an AI/role suggestion is never indistinguishable from a
  human-authored manifest; the human approval is the sole promotion gate.

### C. The loop & surface

- **FR-MS-7 — draft → review → approve (mirror the Teian *pattern*, own the engine)** *(narrowed)*. A
  **separate** CLI surface (`startd8 screens` or equivalent): `suggest` (`$0` starter + optional `--roles`
  paid pass), `review` (`$0` render), `approve`/`reject` (→ a `manifest` proposal). Mirrors Teian's loop
  shape but uses the suggester's **own** manifest-shaped recommend/apply/grounding (the panel's
  `recommend`/`recommend_apply`/`grounding_guard` are value-scalar-coupled and are **not** reused). Staged
  out-of-band; a stale suggestion (the screen was added meanwhile) is detected and skipped.
- **FR-MS-8 — Surfaces the Red Carpet "screens" gap.** When the advisor/wizard reports the screens gap,
  it points at this suggester as the guided way to fill it (a next-step/command), so the capability is
  discoverable at the moment of need.

---

## 4. Non-Requirements

- **NR-1 — Not fused into the Stakeholder Panel's value pass.** Separate capability, separate CLI; the
  panel stays scalar-value-only (its clean abstraction is preserved).
- **NR-2 — Not real content (bucket-4).** It proposes *which screens + their structure*; the screens' real
  copy/data is the user/company's, out of scope.
- **NR-3 — No new grammar / extractor / write engine.** Rides the existing pages/views extraction + the
  `manifest` proposal kind; adds no manifest kind and no parser.
- **NR-3a — Not an entity-CRUD generator.** Entity CRUD is already auto-generated by the deterministic
  cascade; the suggester proposes **composite views + non-entity content pages** only (planning-settled).
- **NR-4 — Doesn't change the cascade.** What the `$0` cascade builds from an approved manifest is
  unchanged.
- **NR-5 — Not polyglot.** Targets the deterministic Python manifest path.
- **NR-6 — Not an autonomous author.** The loop never writes; every screen is a human-approved proposal.

---

## 5. Open Questions

*All 6 resolved by the planning pass — see §0.*

- **OQ-1 — RESOLVED** → views = `view: <name>` + `Kind ∈ {dashboard/board/workspace}`; pages = `## Pages`
  (markdown the extractor round-trips).
- **OQ-2 — RESOLVED** → the `manifest` kind takes a prose `source` and **server-derives** the dest
  (round-trip-gated, no-clobber) — no dest hint; no new apply path.
- **OQ-3 — RESOLVED** → `persona`/`routing`/`roster` reusable (generic); `recommend`/`input_domains`/
  `recommend_apply`/`grounding_guard` are value-scalar-coupled → the suggester owns those.
- **OQ-4 — RESOLVED** → model screens as a `value_path`-like symbol (`views`/`pages`); a design/PM persona
  owns it via `answers_for` — roster *content*, no new grammar.
- **OQ-5 — RESOLVED** → the `$0` baseline is a **starter dashboard view over primary entities** (a
  composite), **not** CRUD (which the cascade already generates).
- **OQ-6 — RESOLVED** → dedupe by reading the live `views.yaml`/`pages.yaml`.

---

*v0.2 — Post-planning self-reflective update. The loop caught that a schema→CRUD baseline would **duplicate
the deterministic `$0` cascade** (entity CRUD is already auto-generated; `pages.yaml`/`views.yaml` are for
**composites + non-entity pages**), and sharpened the capability to suggesting **composite views +
non-entity content pages**. Panel reuse narrowed to `persona`/`routing`/`roster` + the pattern (the
value-scalar `recommend`/`apply`/`grounding` are owned, not reused); the `manifest` kind + extractor
round-trip are the confirmed apply/safety path. All 6 OQs resolved. Next: lessons hardening, then CRP.*

*v0.3 — Post lessons-learned hardening. Applied SDK design-docs lessons: prune-phantom-scope (the CRUD
baseline — already dropped in planning; NR-3a added), overloaded-term (own package + `suggest`, never the
panel's `recommend`), single-source vocabulary ownership (panel/authoring-contract/`proposals.py` own their
vocab; this doc owns only the suggester vocab), phantom-reference audit (all verified; §Reference-Audit),
CRP steering (target + settled items → focus file). Ready for CRP.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Areas Substantially Addressed (>= 3 accepted)

- **Data**: 3 accepted (R1-F2, R1-F4, R2-F3)

### Areas Needing Further Review (below threshold of 3)

- **Architecture**: 2/3 accepted (R1-F6, R2-F2)
- **Risks**: 2/3 accepted (R1-F5, R2-F1)
- **Validation**: 2/3 accepted (R1-F3, R3-F2)
- **Interfaces**: 1/3 accepted (R1-F1)
- **Security**: 1/3 accepted (R3-F1)
- **Ops**: 0/3 accepted

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R2-F1 | FR-MS-5 + FR-MS-7 are **jointly unsatisfiable** for a 2nd approved screen (`_apply_manifest` is a whole-file replace from one candidate's `source`, no merge, no reverse renderer) | claude-sonnet-5 (R2) | ACCEPT — **critical**. Add an explicit acceptance criterion to FR-MS-5/FR-MS-7: approving N screens in sequence (empty or non-empty starting manifest) yields **all N** in the final `views.yaml`/`pages.yaml`. Pairs with plan R2-S1 (accumulation strategy). | 2026-07-03 |
| R3-F1 | FR-MS-6 needs a criterion: a `ScreenCandidate`'s free-text fields must never contain `^#{2,4}\s` when assembled into the `manifest` `source` (`parse_sections` treats any such line as a section boundary) | claude-sonnet-5 (R3) | ACCEPT — **critical, security**. Concrete way the "human approval is the sole promotion gate" guarantee is silently defeated by candidate *content*. Pairs with plan R3-S1. Test: injected `### view:` line rejected/neutralized; `extract_manifests` on final `source` yields only intended entries. | 2026-07-03 |
| R1-F1 | FR-MS-2 should name the reuse target as `StakeholderPanel.ask(role_id, question, value_path=...)`, not `persona.Persona.ask` (which is uninstrumented) | claude-sonnet-5 (R1) | ACCEPT — high. As written, FR-MS-2 is satisfiable by a path that bypasses cost/telemetry/transcript. Pairs with plan R1-S1. Test: drafting call goes through `StakeholderPanel.ask` (cost recorded, transcript entry, span emitted). | 2026-07-03 |
| R1-F2 | FR-MS-1 "dashboard over the **primary entities**" (plural) needs a single-`Root`/join-awareness caveat (`extract_views` resolves exactly one `Root`; extra entities only via `Shows:`/`counts of` with a real join) | claude-sonnet-5 (R1) | ACCEPT — high. Pairs with plan R1-S2. Test: 2 unrelated primary entities → baseline references only one as `Root:`, no `Shows:` to the other. | 2026-07-03 |
| R2-F2 | FR-MS-1/FR-MS-4 should define "schema entities"/"declared entity" in terms of `manifest_extraction.entities.EntityGraph` (`resolve_entity`/`join_between`), not an independent `EntityFacts` | claude-sonnet-5 (R2) | ACCEPT — high. Prevents a parallel entity-matcher that silently disagrees with the extractor. Pairs with plan R2-S2. Test: same schema through the guard and the extractor's resolution → identical accept/reject for name variants. | 2026-07-03 |
| R1-F3 | FR-MS-4's grounding guard covers only entity/field existence; the real gate (FR-MS-5 via `extract_views`) also enforces Kind vocabulary, `board` `Group by`, derived-join existence. Broaden, or state it is necessary-but-not-sufficient | claude-sonnet-5 (R1) | ACCEPT — medium. Pairs with plan R1-S3. One test per rejection class: bad `Kind`, missing `Group by`, ungrounded `Shows:` pair. | 2026-07-03 |
| R1-F4 | OQ-1 understates the extractor Kind vocabulary — `_KINDS` is 7 values, not the 3 stated. Document v1's 3-kind restriction as a deliberate scope choice | claude-sonnet-5 (R1) | ACCEPT — medium. §Reference-Audit row for `extract_views`/Kind states the full 7-value set with a note on the v1 subset. Prevents a future reader/persona from being handed an incomplete vocabulary. | 2026-07-03 |
| R2-F3 | FR-MS-2 needs a criterion: the drafting prompt must supply the **literal exact declared entity name strings**, not a natural-language description | claude-sonnet-5 (R2) | ACCEPT — medium. `resolve_entity` normalizes only case/plurality/punctuation vs the exact name; paraphrase fails grounding for a prompt-design reason. Pairs with plan R2-S3. Test: drafting prompt text includes the verbatim declared entity-name list. | 2026-07-03 |
| R1-F5 | FR-MS-3's dedupe must specify slug/`ident` (`nfkd_kebab`) identity, not raw `name` equality | claude-sonnet-5 (R1) | ACCEPT — medium. Pairs with plan R1-S7. Test: existing view "Signup Funnel" + candidate "signup-funnel" recognized as the same slug and deduped. | 2026-07-03 |
| R3-F2 | FR-MS-7's `review` step needs a criterion that the rendered preview is the **literal text** that becomes the `manifest` `source`, not a summary (mirrors sibling FR-KIR-9) | claude-sonnet-5 (R3) | ACCEPT — medium (Validation). Pairs with plan R3-S2. Snapshot test: `review` render text == exact `source` string `approve` submits. | 2026-07-03 |
| R1-F6 | Add a §Reference-Audit row pointing `manifest_suggester/store.py` at the shipped `stakeholder_panel/proposals.py` `ProposalStore` as the reference shape | claude-sonnet-5 (R1) | ACCEPT — low. Makes P5 ("reuse, don't reimplement") concrete. Pairs with plan R1-S5/R1-S6. Row cites the path + properties to mirror (atomic write, `sort_keys`+`indent=2`, session GC, path-traversal guard). | 2026-07-03 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet — all R1–R3 F-suggestions accepted; see Appendix A) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-sonnet-5 — 2026-07-03 01:50:00 UTC

- **Reviewer**: claude-sonnet-5
- **Date**: 2026-07-03 01:50:00 UTC
- **Scope**: First pass, code-grounded against the live `startd8-sdk` tree (companion plan review — see
  `MANIFEST_SUGGESTER_PLAN.md` Appendix C R1 for the focus-file asks and S-suggestions this round also
  produced). This round's requirements-facing findings mirror the plan-facing ones where the *acceptance
  criteria themselves* need sharpening, not just the implementation approach.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Interfaces | high | **FR-MS-2** should name the reuse target explicitly as `StakeholderPanel.ask(role_id, question, value_path=...)`, not `stakeholder_panel.persona.Persona` (which the plan's Step 3 currently cites). Verified: `persona.py:Persona.ask` is an uninstrumented instance method (no cost tracking/transcript/OTel); `panel.py:StakeholderPanel.ask` is the layer that adds all three and is what the sibling `recommend_inputs` pass actually calls. | As written, FR-MS-2 is satisfiable by an implementation that bypasses cost/telemetry/transcript entirely (a literal reading of "reuse `persona.Persona.ask`"), which would silently create a second, unaccounted-for paid-call surface. | Section 3.A (FR-MS-2) | A test asserts the suggester's drafting call goes through `StakeholderPanel.ask` (cost is recorded, a transcript entry exists, a span is emitted) — not a bare `Persona` instance. |
| R1-F2 | Data | high | **FR-MS-1**'s "a dashboard view over the **primary entities**" (plural) needs a precise definition given the extractor's actual grammar: `extract_views` resolves exactly **one** `Root:` entity per view; additional entities can only enter via `Shows:`/`counts of`, and only when a derived join model actually connects them to the root. As written, "primary entities" (plural) with no join-awareness caveat is ambiguous about what the baseline concretely emits. | Verified in `manifest_extraction/extractors.py:extract_views` — `Root` is singular; a `Shows: A→B` pair with no join model between A and B is rejected with `reason="fk-unavailable... never a guessed <entity>Id"`. A baseline built naively against "primary entities" (plural) risks emitting a candidate that fails the very round-trip gate FR-MS-5 relies on. | Section 3.A (FR-MS-1) | A test: for a schema with 2 unrelated "primary" entities, the emitted baseline prose references only one as `Root:`, with no `Shows:`/`counts of` lines to the unrelated one. |
| R1-F3 | Validation | medium | **FR-MS-4**'s grounding guard, as written ("every `entities_referenced` must be a declared entity/field"), covers only entity/field existence. The real round-trip gate (FR-MS-5, via `extract_views`) also enforces Kind-vocabulary membership (7 values, not the 3 named in OQ-1), `board`'s required `Group by`, and derived-join existence for any `Shows:`/`counts of` reference — none of which a pure entity-existence check would catch. Either broaden FR-MS-4's acceptance criteria to include these, or explicitly state the guard is a **necessary-but-not-sufficient** pre-filter and the round-trip is authoritative. | As written, FR-MS-4 could be read as "the grounding guard is the completeness check," which isn't true given the extractor's fuller rejection surface — leaving several rejection classes untested until Step 7's round-trip test, one layer later than the requirement implies. | Section 3.B (FR-MS-4) | One test per rejection class: bad `Kind`, missing `Group by` on `board`, ungrounded `Shows:` pair. |
| R1-F4 | Data | medium | **OQ-1**'s resolution ("views = `view: <name>` + `Kind ∈ {dashboard/board/workspace}`") understates the real extractor vocabulary — `_KINDS` in `manifest_extraction/extractors.py` is `{dashboard, board, workspace, detail-compose, export-package, import-flow, computed-panel}` (7 values). Even if v1 intentionally restricts the suggester to the 3 simplest kinds, the doc should say so as a deliberate scope choice, not present it as the extractor's whole vocabulary. | A future reader (or a role persona prompted with "the Kind vocabulary is X") could be given an incomplete picture, and a later increment extending drafting to `board`/`detail-compose` would find the doc's own reference wrong. | Section 5 (OQ-1) | §6's Reference-Audit table row for `extract_views`/Kind vocabulary states the full 7-value set, with a note on which subset v1 drafts. |
| R1-F5 | Risks | medium | **FR-MS-3**'s dedupe criterion ("skip candidates whose name/slug already exists") should specify *which* — raw `name` string equality is insufficient because `extract_pages`/`extract_views` both derive a normalized slug/`ident` (`nfkd_kebab`) from the name; two differently-cased/punctuated names can collide at that layer even though a naive name-equality dedupe would treat them as distinct. | Leaving this ambiguous risks a suggested "new" screen that's actually a near-duplicate discovered only at apply time (round-trip/dest-collision) instead of at the dedupe step FR-MS-3 is meant to own. | Section 3.A (FR-MS-3) | A test: an existing view named "Signup Funnel" and a candidate named "signup-funnel" are recognized as the same slug and deduped. |
| R1-F6 | Architecture | low | Add a §6 Reference-Audit row (or a short note) pointing to the sibling `STAKEHOLDER_INPUT_RECOMMENDATIONS_*` feature's `proposals.py`/`ProposalStore` as the reference shape for this doc's own to-be-created `manifest_suggester/store.py`, since that staging-store pattern is now CRP-hardened and shipped (`src/startd8/stakeholder_panel/proposals.py`). | Cross-referencing a proven, already-reviewed pattern (rather than letting `store.py` be designed independently) is exactly the "reuse, don't reimplement" discipline P5 already states as a guiding principle — this makes it concrete. | Section 6 "Reference-Audit" | The row cites the file path and the specific properties to mirror (atomic write, sort_keys+indent=2, session GC, path-traversal guard on the session id). |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- None — first round, Appendix C had no prior entries.

#### Review Round R2 — claude-sonnet-5 — 2026-07-03 02:00:00 UTC

- **Reviewer**: claude-sonnet-5
- **Date**: 2026-07-03 02:00:00 UTC
- **Scope**: Second, adversarial pass (see the companion plan review's R2 for the full trace). This
  round's requirements-facing findings sharpen the acceptance criteria for the critical accumulation gap
  and the entity-resolution consistency issue found there.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Risks | critical | **FR-MS-5** ("An approved suggestion is applied only through the existing `manifest` proposal kind") and **FR-MS-7** ("approve/reject → a `manifest` proposal") together imply a per-screen, one-at-a-time apply — but as verified, `_apply_manifest` is a whole-file replace derived solely from the current proposal's `source` prose, with no merge against the live `views.yaml`/`pages.yaml` and no prose-reverse-renderer anywhere in the tree. As written, these two requirements are **jointly unsatisfiable** the moment a second screen is approved against a project that already has one (whether from a prior suggester approval or hand-authoring) — the second `approve` either refuses (clobber guard) or, if forced, destroys the first. | This is not a hypothetical edge case; FR-MS-3 ("only suggest what's missing... dedupe against the current manifest") is explicitly written for projects that already have entries in `views.yaml`/`pages.yaml`, so the very scenario FR-MS-3 assumes is the scenario FR-MS-5/7 cannot currently survive. | Section 3.A (FR-MS-3) and 3.B (FR-MS-5) | Add an explicit acceptance criterion to FR-MS-5 or FR-MS-7 requiring that approving N screens in sequence (against an initially non-empty or empty manifest) results in **all N** screens present in the final `views.yaml`/`pages.yaml`, not just the most recently approved one. |
| R2-F2 | Architecture | high | **FR-MS-1**/**FR-MS-4**'s "schema entities" / "declared entity/field" vocabulary should be defined in terms of the existing `manifest_extraction.entities.EntityGraph` (with its `resolve_entity`/`join_between` methods) rather than left implicit as a new, independently-specified `EntityFacts` type. | The requirements currently describe `EntityFacts` and the grounding guard's "declared entity" check as if they were free to be designed from scratch; without tying them explicitly to `EntityGraph`, an implementation could build a parallel entity-matching scheme that silently disagrees with what the round-trip extractor actually accepts (a "guard says grounded, extractor rejects" gap distinct from the structural-prerequisites gap already filed in R1-F3). | Section 3.A (FR-MS-1) and 3.B (FR-MS-4) | A test feeding the same schema through the suggester's grounding check and the extractor's own resolution, asserting identical accept/reject verdicts for a shared set of entity-name variants (plural, case, spacing). |
| R2-F3 | Data | medium | Add an acceptance criterion to **FR-MS-2** specifying that the drafting prompt given to the role-informed pass must supply the **literal, exact declared entity name strings**, not a natural-language description of the schema — since `EntityGraph.resolve_entity` normalizes only case/plurality/punctuation-squashing against the exact name, not free paraphrase. | Without this, a well-grounded persona reply describing an entity in ordinary prose (e.g. "the customer's profile" for a declared `CustomerProfile` entity) would be rejected by the grounding guard for a prompt-design reason, not a genuine hallucination — and the failure would be hard to distinguish from a real ungrounded reference without this criterion calling it out. | Section 3.A (FR-MS-2) | A test asserting the drafting prompt text includes the verbatim list of declared entity names from `EntityFacts`. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-F2: still stands independently of this round's accumulation-gap finding — the single-root/join-gating correction to FR-MS-1 remains necessary regardless of how R2-F1 is resolved.

#### Review Round R3 — claude-sonnet-5 — 2026-07-03 02:15:00 UTC

- **Reviewer**: claude-sonnet-5
- **Date**: 2026-07-03 02:15:00 UTC
- **Scope**: Third pass. See the companion plan review's R3 for the full trace of `parse_sections`'s
  pure line-scanning behavior and the section-injection risk it enables.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Security | critical | **FR-MS-6** ("the human approval is the sole promotion gate") and **P4** ("the human approves each screen") together imply that what the human reviews is what gets applied. Add an explicit acceptance criterion: a `ScreenCandidate`'s free-text fields (rationale, any persona-authored description) must never be permitted to contain a line matching `^#{2,4}\s` (a markdown heading marker) when assembled into the `manifest` proposal's `source` — verified that `manifest_extraction.grammar.parse_sections` treats any such line, anywhere in the document, as a new section boundary regardless of surrounding context, and `extract_views` picks up every resulting `view:`-titled section. Without this criterion, an "approved" candidate's prose could smuggle in additional, unreviewed manifest entries. | This is a concrete, previously-unstated way the "human approval is the sole promotion gate" guarantee can be silently defeated — not by a bug in the apply path, but by the *content* of what the human is asked to approve. | Section 3.B (FR-MS-6) | A test: a candidate with an injected `### view:` line in its rationale is either rejected before staging or has the injected line neutralized; `extract_manifests` on the final `source` yields only the intended entries. |
| R3-F2 | Validation | medium | **FR-MS-7**'s `review` step ("$0 render") should have an explicit acceptance criterion that the rendered preview is the **literal text** that will become the `manifest` proposal's `source` on approval — not a summarized re-derivation — mirroring FR-KIR-9's anti-anchoring "review renders the gap, not just the fill" discipline in the sibling Stakeholder Input Recommendations feature. | Without this, a human could approve based on a friendly summary that doesn't reflect exactly what will be extracted, undermining the same promotion-gate guarantee FR-MS-6/R3-F1 depends on. | Section 3.C (FR-MS-7) | A snapshot test comparing the `review` render's text against the exact `source` string that `approve` would submit for the same candidate. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-F1: still stands and interacts with this round's finding — any accumulation strategy chosen to resolve R2-F1 must also pass through R3-F1's sanitization on every assembled document, not just the first.

#### Review Round R4 — claude-sonnet-5 — 2026-07-03 02:20:00 UTC

- **Reviewer**: claude-sonnet-5
- **Date**: 2026-07-03 02:20:00 UTC
- **Scope**: Fourth pass. See the companion plan review's R4 for the full rationale — this round applies
  two lessons the sibling Stakeholder Input Recommendations feature already paid for through its own CRP
  cycle (budget-preflight ordering, staging-aware re-spend guard) as explicit acceptance criteria here.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Ops | high | **FR-MS-2** should state explicitly that the paid role-informed pass's budget preflight runs **after** FR-MS-3's dedupe, not before — otherwise the preflighted count includes candidates that will be dropped as duplicates, overestimating cost and risking a false budget denial. This mirrors `FR-KIR-12`'s resolved ordering in the sibling requirements doc (R3-F1-equivalent territory, resolved there as R3-S1/R1-F1). | Without this criterion, FR-MS-2 as written is satisfiable by an implementation that preflights the raw candidate count — the exact bug class the sibling project already found and fixed. | Section 3.A (FR-MS-2) | See the companion plan's R4-S1 validation approach. |
| R4-F2 | Risks | medium | **FR-MS-3**'s "only suggest what's missing" dedupe criterion should explicitly distinguish two axes: (a) dedupe against the **live, applied** `views.yaml`/`pages.yaml` (as currently written), and (b) dedupe against a **prior session's still-pending** candidates (not yet approved/rejected) — currently unaddressed. Without (b), running the role-informed pass twice before approving anything drafts and pays for the same screen twice. | This is the FR-KIR-12/Mottainai lesson the sibling requirements doc already encodes (R2-F2) for its own drafting pass, on a distinct axis this requirement doesn't currently name. | Section 3.A (FR-MS-3) | See the companion plan's R4-S2 validation approach. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R3-F1: still stands, independent of this round's ordering/dedup findings.
