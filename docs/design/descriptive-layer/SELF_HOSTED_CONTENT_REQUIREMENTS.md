# Self-Hosted Content — Requirements (maintain our own content like a wireframed project)

**Version:** 0.1 (Draft — pre-planning)
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
- **FR-SHC-2 — A declared record schema (our "data model").** The shape of a descriptive record MUST be
  **declared**, not implicit in `describe.py`: the field set, which fields are required vs optional, and
  the audience axes (role × fluency). This is the analog of a project's entity schema — the contract the
  content fills, against which coverage is measured.
- **FR-SHC-3 — Coverage of the content matrix (the completeness analog).** The authoring state of the
  matrix — which `(section × role × fluency × field)` cells are **authored** vs **degrading to base** —
  MUST be computable and expressed the same way FR-WCI-2 expresses project content: authored/total per
  axis (per role, per fluency, per section), an `overall` %, honestly un-authored (never faked, never a
  gate). Reuse `CoverageStat`/`ContentCoverageStats` (Mottainai), don't invent a parallel scorer.
- **FR-SHC-4 — Gaps surfaced as authoring to-dos.** An un-authored cell MUST be **surfaced** (a "content
  to author" list — the NEED / not_defined analog), not silently invisible. The R1-F4 completeness bar
  (every section carries end_user DOES/WON'T/NEED) is the first slice of this; FR-SHC generalizes it to
  the whole matrix (all authored roles × fluencies).
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

- **OQ-SHC-1 — Dogfood-full vs lightweight report.** Run `descriptive.yaml` through a wireframe-like
  coverage view (maximal dogfood, most legible), or ship a focused `startd8 describe --coverage` /
  test-asserted report reusing `ContentCoverageStats`? (Lean: lightweight report first; escalate to a
  visual coverage view only if the matrix grows enough to warrant it — avoid over-formalizing, per the
  DEV-OS "run the manual loop N times first" rule.)
- **OQ-SHC-2 — The expected-matrix denominator.** Coverage needs a target: what cells *should* exist?
  (e.g. `sections × {architect, end_user} × {base + declared fluencies}`.) Where is that intent declared
  — a small config, or inferred from which roles/fluencies appear anywhere in the manifest?
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
| A "coverage over the audience matrix" computation | — | ❌ **does not exist yet** (the FR-SHC-3 gap) |
| An "expected matrix" / intent declaration | — | ❌ does not exist (OQ-SHC-2) |

---

*v0.1 — Draft, pre-planning. Grounded on the real project-content mechanisms (`CONVENTION_PATHS`,
`ContentCoverageStats`). Next: a planning pass to stress-test — especially FR-SHC-5 (dogfood-full vs
report) and OQ-SHC-2 (the expected-matrix denominator) — then §0 reflection, lessons/principle hardening,
and optional CRP. Deliberately resists building the coverage tool until the shape is confirmed.*
