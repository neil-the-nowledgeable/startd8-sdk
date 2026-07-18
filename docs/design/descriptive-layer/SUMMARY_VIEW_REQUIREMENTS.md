# Summary View — Requirements (the Architect's glance-approve sheet)

**Version:** 0.1 (Draft — consolidation)
**Persona:** the **Architect** at the DATA MODEL front bookend (HITM §3.3).
**Purpose:** the *one screen* an architect reads to approve the convention manifest + contract
**without** reading `schema.prisma` — the summary altitude of the visualization layer.
**Consolidates (cite, do not restate — Mottainai):** `dev-os/NODE-SCHEMA.md` §3b (SV-1…SV-8, the
grammar), `DESCRIPTIVE_LAYER_REQUIREMENTS.md` FR-DL-12/13 (the render), `wireframe/WIREFRAME_REQUIREMENTS.md`
FR-W9 (the footer), and the architect kit's `validation-visualization.md` (the acceptance test).

---

## 1. What the summary MUST show (the signal inventory)

Each row is a signal the architect needs to answer *"is the shape right, and is it ready?"* — with
its grammar source and current build state. **Rule (SV-8 / FR-DL-13): no architect-relevant signal
stays `--json`-only or inline-only.**

| # | Signal | Answers | Source | Built? |
|---|---|---|---|---|
| FR-SV-1 | **Key-object counts** — entities · CRUD · pages · forms · views · AI passes | "how big?" | SV-2 · FR-W9 shape | ✅ |
| FR-SV-2 | **Core vs. derived** entities (the human-judged inputs vs generated) | "what do I actually decide?" | SV-4 (completeness signals vs `excluded`) | ⚠️ data present; label pending |
| FR-SV-3 | **Health roll-up** — `N planned / defaults / placeholder / not-defined / invalid` + worst-glyph | "is anything broken/missing?" | SV-5 · FR-W9 counts | ✅ |
| FR-SV-4 | **Content-authoring readiness %** — pages/view-copy/prompts/form-help authored/total | "is it ready for content handoff?" | SV-8 · FR-WCI-2 | ✅ (footer) |
| FR-SV-5 | **Presentation / display layer** — per-entity title/sections/label/omitted-ids | "are the UI groupings right?" | SV-8 · display.yaml | ✅ (Display section) |
| FR-SV-6 | **AI boundary** — which fields are human-authored vs AI-generated | "where does the model stop?" | SV-8 · `human_inputs` | ❌ inline-only → surface |
| FR-SV-7 | **Manifest provenance / override** — convention vs flag vs declared | "where did each input come from?" | SV-8 · `input_provenance`/`status_override` | ❌ `--json`-only → surface |
| FR-SV-8 | **Readiness** — cascade `scaffold/backend/views: ready\|blocked(reason)` | "can I run the cascade?" | SV-6 · FR-W9 | ✅ |
| FR-SV-9 | **AI-pass input graph** — `reads X → writes Y` + `source_binding` per pass | "what feeds the model?" | `ai_passes` `input_entities`/`source_binding` | ⚠️ outputs shown, inputs buried → surface |
| FR-SV-10 | **Orphan entities / FK relation graph** — entities with no view/page; the relation shape | "is anything stranded / how do they connect?" | needs new compute over the schema | ❌ not computed (high effort — deferred) |
| FR-SV-11 | **AI-pass ordering / dependency** — pass execution order + which passes depend on which | "is the AI pipeline sequenced right?" | `ai_passes` `trigger`/`input_entities` | ❌ order shown flat, deps buried |

> **Audit (2026-07-18, direct):** ranked buried set = **AI boundary (FR-SV-6)** + **core/derived
> label (FR-SV-2)** [both HIGH, low effort → surfacing now] · **AI-pass inputs (FR-SV-9)** [MED,
> small → surfacing now] · provenance/override (FR-SV-7) [MED, quiet — surface only on override] ·
> orphan/FK graph (FR-SV-10) [HIGH, high effort — deferred].

## 2. How it's shown (grammar, cited)

- **Summary before detail, drillable** (SV-1): the summary is the collapsed root; every count drills
  to its section.
- **Counts carry meaning** (SV-3): a WHAT + derivation (`155 CRUD = ~5 × 31`), never bare numbers.
- **Deterministic + speakable** (SV-7 / invariant 8): a pure function of the plan; the whole summary
  is renderable as one spoken line for a non-visual architect.
- **Honest-skip** (SV-5/6 / route_state): `not-defined`/`owned-elsewhere` excluded from denominators;
  a blocked cascade names its blocker (never silent zeros).

## 3. Acceptance test (the bar this view must clear)

> **Can an architect approve the planned shape at a glance, and confidently reject/flag when it's
> wrong — without reading `schema.prisma`?**

Proven on the reference consumer (`kits/architect/example-strtd8-summary.md`): the raw wireframe
footer passed the *aggregate* glance (size/health/readiness) but failed the *semantic* glance
("is it *right*?") until SV-4 (core/derived) + FR-SV-4/5/6 surfaced the buried signals. The bar:
each FR-SV-* row is glance-legible and, where it's a decision (FR-SV-2, FR-SV-6), states the decision.

## 4. Non-Requirements

- Not a gate (advisory; no `--fail-on-incomplete`).
- Not content generation (surfaces the plan; never drafts).
- Not a re-spec of SV-* / FR-DL / FR-W9 — this doc **consolidates and cites** them for the architect.

---

*v0.1 — consolidation of the summary-view requirements scattered across NODE-SCHEMA §3b, FR-DL-12/13,
and FR-W9, framed for the Architect persona. §1 FR-SV-9 + build states to be completed from the
exhaustive buried-signal audit (in progress).*
