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
