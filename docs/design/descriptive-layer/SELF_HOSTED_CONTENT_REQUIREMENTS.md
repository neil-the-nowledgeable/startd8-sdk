# Self-Hosted Content — Requirements (maintain our own content like a wireframed project)

**Version:** 0.2 (Post-planning — self-reflective update; spike-grounded)
**Date:** 2026-07-19
**Status:** Draft
**Concept key:** `FR-SHC` (Self-Hosted Content). Stable prefix; the framing ("dogfooded content",
"content-as-a-project") may change, the key does not — [[concept-key-not-presentation-name]].

> **The idea.** The descriptive / audience content we author (`descriptive.yaml` — the what/why/do/next/
> wont/need/title records, their role × fluency variants, the intro/summary copy) is the *content of a
> product* (the wireframe-visual preview). Right now it's maintained ad-hoc — a hand-edited YAML plus
> Python. **Every startd8 app we wireframe defines + maintains *its* content with real discipline**
> (convention-declared manifests, a data-model/schema, honest content-completeness scoring, gap
> surfacing). This spec asks: **maintain OUR content the same way** — so the tooling eats its own
> dog food, and the content matrix is legible, coverage-tracked, and gap-aware instead of implicit.

**Reuses (cite, do not restate — Mottainai):**
- Project content *declaration* → `wireframe/inputs.py` `CONVENTION_PATHS` (14 keys: `pages.yaml`,
  `view_prose.yaml`, `form_prose.yaml`, `prompts/…`, `display.yaml`, …).
- Project content *completeness* → `wireframe/plan.py` `ContentCoverageStats` / `CoverageStat` (FR-WCI-2:
  authored/total per surface, `overall` %, "visibility only, never a gate, honestly un-authored").
- Our content today → `wireframe/descriptive.yaml` + `describe.py` (`_variant` resolver, single-source,
  authored, deterministic — FR-DL-5/8, FR-AUD-1).
- The maturity/closure discipline → `dev-os/CLOSURE-LEDGER.md`, the [[requirements-preview-capability]].

---

## 0. Planning Insights (Self-Reflective Update)

> A planning **spike** computed the audience-matrix coverage over the real `descriptive.yaml`. What it
> revealed (v0.1 → v0.2):

| v0.1 Assumption | Spike Discovery | Impact |
|---|---|---|
| One uniform descriptive-record schema | The `summary` record's fields (`headline/lead/steps/closing`) differ from a section record's (`title/what/wont/need/do/next`) | **FR-SHC-2 declares per-*type* schemas** (section-record + summary-record), not one |
| Coverage will find current gaps | Expected-matrix coverage is **already 100%** (arch 40/40, end_user 60/60 — the R1-F4 bar is met) | **FR-SHC-4 reframed**: the value is a *regression guard + a visible number*, not fixing a present hole |
| Might need dogfood-full (run our content through the app cascade) | Coverage is **~30 lines reusing `CoverageStat`**; a cascade run would be contrived machinery | **OQ-SHC-1 → lightweight report** (FR-SHC-5 narrows); the accidental-complexity guard holds |
| Fluency is part of the matrix | Fluency is **sparse/opt-in** (2 of 10 sections) | Excluded from the denominator (NR-2 holds); reported informationally |

**Resolved open questions:**
- **OQ-SHC-1 → lightweight report.** A `matrix_coverage()` rollup + a regression-guard test now; a visual
  coverage view is deferred until the matrix is big enough to warrant it (don't over-formalize).
- **OQ-SHC-2 → the denominator is `record-type schema × roles-in-use`.** Fluency cells are reported, not
  counted. The "expected matrix" = what each record *type* requires, for each role actually in play.

---

## 1. Problem Statement

A wireframed app's content is a **first-class, tracked artifact**: declared by convention, scored for
completeness, and its gaps surfaced (the wireframe literally says "6% authored — pages 3/3 · view-copy
4/9 · …"). Our *own* content — the audience narration that powers that very preview — has none of that:
no declared schema, no coverage number, no gap list. We only discover an un-authored `(role, fluency,
section)` cell by reading the YAML or noticing a section fell back to base. That's the exact "you don't
see the gap until after it's built" failure the wireframe exists to prevent — turned on ourselves.

| Aspect | A wireframed app's content | Our descriptive/audience content (today) |
|---|---|---|
| Declared where | `CONVENTION_PATHS` (conventional manifest files) | `descriptive.yaml` (one file, no declared record schema) |
| "Data model" / shape | entities / `schema.prisma` | implicit in `describe.py` (`what/why/do/next/wont/need/title`) |
| Completeness scored | FR-WCI-2 `ContentCoverageStats` (authored/total, %) | **none** — coverage of the audience matrix is invisible |
| Gaps surfaced | not_defined content → NEED; content % in the band | **none** — an un-authored cell silently degrades to base |
| Maintained/validated by | `startd8 wireframe` (+ tests) | hand-edited YAML; no coverage/validate tool |

## 2. The mapping (project content ⟷ our content)

| Project concept | Self-hosted content analog (FR-SHC) |
|---|---|
| Entities / data model (the shape content fills) | **The descriptive-record schema** — the field set (`what/why/do/next/wont/need/title`) × the audience axes (role × fluency) |
| `CONVENTION_PATHS` manifest declaration | **`descriptive.yaml` as the declared content manifest** (single-source, conventional home) |
| Content files (page bodies, prompts, view/form prose) | **The authored audience cells** — each `(section × role × fluency × field)` |
| FR-WCI-2 content completeness (authored/total, %) | **Audience-matrix coverage** — authored cells vs the expected matrix; an overall % |
| not_defined content → NEED / the content band | **Un-authored cells surfaced as "content to author"** (the NEED analog) |
| The wireframe preview (shape + gaps, honest) | **A coverage view of the content matrix** (dogfood the same tooling where it fits) |

## 3. Requirements

- **FR-SHC-1 — Convention-declared, single-source manifest.** Our content MUST live in one manifest at a
  conventional location (today `descriptive.yaml`), single-sourced — the renderer/composer holds no
  authored strings (already FR-DL-5). The manifest is the *only* home for the words; code reads, never
  embeds. (The self-hosted analog of `CONVENTION_PATHS`.)
- **FR-SHC-2 — Declared record-*type* schemas (our "data model").** The shape of a descriptive record MUST
  be **declared**, not implicit in `describe.py`. The spike proved there are **two record types**, each with
  its own required-vs-optional field set per role: the **section-record** (`title/what/wont/need/do/next`)
  and the **summary-record** (`headline/lead/steps/closing`). This declared schema is the analog of a
  project's entity schema — the contract the content fills, against which coverage is measured — and it is
  read by BOTH the coverage rollup and (over time) the resolver, so the expected shape is single-sourced.
- **FR-SHC-3 — Coverage of the content matrix (the completeness analog).** The authoring state of the
  matrix — which `(section × role × fluency × field)` cells are **authored** vs **degrading to base** —
  MUST be computable and expressed the same way FR-WCI-2 expresses project content: authored/total per
  axis (per role, per fluency, per section), an `overall` %, honestly un-authored (never faked, never a
  gate). Reuse `CoverageStat`/`ContentCoverageStats` (Mottainai), don't invent a parallel scorer.
- **FR-SHC-4 — Gaps surfaced + a regression guard.** An un-authored cell of the *expected* matrix MUST be
  surfaced (a "content to author" list — the NEED / not_defined analog), and its absence MUST be a
  **CI-failing regression guard** — because the spike found the expected matrix is already 100% authored
  (R1-F4 met), so FR-SHC's live value is *keeping it from silently drifting* (a new section or newly-used
  role landing without its cells), not fixing a present hole. Generalizes the R1-F4 bar to the whole matrix.
- **FR-SHC-5 — Dogfood the same tooling where it earns its place.** Where it adds real value (not
  machinery for its own sake), the content SHOULD be inspectable with the SAME mechanism a project uses —
  ideally by treating the descriptive manifest as a wireframe-able "project" whose *completeness* is the
  audience-cell coverage, or a lightweight `describe --coverage` report reusing the FR-WCI-2 rollup.
  **Reuse over rebuild.** If dogfooding would require a parallel subsystem, prefer the lightweight report.
- **FR-SHC-6 — Same invariants as project content.** Deterministic, authored, no-LLM, single-source,
  visibility-only (never a gate) — identical to FR-WCI-2 + FR-AUD-C5 + FR-DL-8.

## 4. Non-Requirements

- **NR-1 — Not a CMS / not a new subsystem.** No content-management app, no new store. Reuse the manifest
  + coverage mechanisms that already exist. (DEV-OS accidental-complexity guard: a standard, not machinery.)
- **NR-2 — Not a full matrix.** Sparse-degrading stays (FR-AUD NR-1): the *expected* matrix is only the
  cells we intend to author (e.g. all sections × {architect base, end_user × its authored fluencies}),
  not every role × every fluency. Coverage measures against the *declared intent*, not a cartesian max.
- **NR-3 — Not necessarily a literal startd8 app.** Our content need not gain a `schema.prisma` or run
  through the full app cascade; FR-SHC-5 reuses the *coverage* idea, not the whole generator, unless the
  wireframe path is genuinely reusable as-is.
- **NR-4 — Not a gate.** Coverage is advisory (like FR-WCI-2). Low coverage never blocks a build/commit.
- **NR-5 — Not (yet) all DEV-OS content.** v1 scopes to the wireframe descriptive/audience content
  (`descriptive.yaml`). Generalizing to other authored corpora (lessons, role kits, capability manifests)
  is OQ-SHC-3, deferred until the pattern is proven on this one.

## 5. Open Questions

- **OQ-SHC-1 → RESOLVED (planning spike): lightweight report.** `matrix_coverage()` rollup + a
  regression-guard test now; a visual coverage view / cascade dogfood is deferred until the matrix warrants
  it. (The spike showed coverage is ~30 lines; a cascade run would be contrived machinery.)
- **OQ-SHC-2 → RESOLVED: the denominator is `record-type schema × roles-in-use`.** Each record *type*
  (section / summary) declares its required fields per role; the expected matrix is that, for each role
  actually present. Fluency cells are *reported*, not counted (sparse/opt-in, NR-2).
- **OQ-SHC-3 — Scope of "our content".** Just `descriptive.yaml`, or all DEV-OS authored corpora
  (lessons-learned, role kits, capability manifests, the requirements docs themselves)? (Lean: prove on
  `descriptive.yaml`; Yokoten later.)
- **OQ-SHC-4 — Schema home.** Where does the FR-SHC-2 record schema live — a declared spec file (JSON
  Schema / a `descriptive.schema.yaml`), a docstring contract, or the FR-AUD-1 requirement text as the
  normative source? (Ties to the single-source discipline.)

## Reference-Audit (to verify during planning — v0.1 assumptions)

| Symbol / asset | Owner | Assumed to exist? |
|---|---|---|
| `CONVENTION_PATHS` (14 content/manifest keys) | `wireframe/inputs.py` | ✅ verified 2026-07-19 |
| `ContentCoverageStats` / `CoverageStat` (authored/total/%, `overall`) | `wireframe/plan.py` | ✅ verified 2026-07-19 |
| `descriptive.yaml` records + `describe.py` `_variant` | wireframe module | ✅ (this session) |
| A "coverage over the audience matrix" computation | — (to build, M-SHC-1) | ⚠ **proven feasible by the spike** (~30 lines reusing `CoverageStat`); not yet shipped |
| An "expected matrix" / intent declaration | — (to build, M-SHC-0) | ⚠ shape resolved (record-type schema × roles); not yet declared in code |
| Two record *types* (section vs summary), different field sets | `descriptive.yaml` | ✅ confirmed by the spike (the key discovery) |

---

*v0.2 — Post-planning self-reflective update. A spike computed the real coverage (arch 40/40, end_user
60/60 — 100%) and surfaced the two-record-types discovery; OQ-SHC-1 (lightweight report) and OQ-SHC-2
(denominator = record-type schema × roles-in-use) resolved; FR-SHC-2 split by record type, FR-SHC-4
reframed as a regression guard. Plan: `SELF_HOSTED_CONTENT_PLAN.md`. Next: lessons/principle hardening +
optional CRP, then build M-SHC-0/1/2. Still WIP-parked behind CL-16.*

*v0.1 — Draft, pre-planning. Grounded on `CONVENTION_PATHS` + `ContentCoverageStats`.*
