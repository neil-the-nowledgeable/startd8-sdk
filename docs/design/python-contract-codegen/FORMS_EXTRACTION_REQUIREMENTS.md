# Forms-Section Extraction (`extract_forms`) — Requirements

**Version:** 0.2 (Post-planning — self-reflective update; pre-CRP)
**Date:** 2026-06-08
**Status:** **DEFERRED** (planning pass found no prose input in the real corpus — see §0). The
architecture is settled and the build is ~½-day *if* a demand trigger fires; until then the
already-shipped gate-half (`parse_forms` in the round-trip) is the correct stopping point.
**Plan:** `FORMS_EXTRACTION_PLAN.md`
**Companion:** `FORM_SUBMIT_BEHAVIOR_REQUIREMENTS.md` (defines the `forms:`/`on_create` knob this
derives — see its OQ-4 "derivation half remains future work"), `src/startd8/manifest_extraction/`
(the deterministic doc→manifest pipeline this extends), `src/startd8/backend_codegen/forms_manifest.py`
(`parse_forms`, the round-trip parser — already wired into the extraction gate). Motivating gap:
`forms:`/`on_create` is the **only** authored knob in the `views.yaml` family that the ingestion
pipeline does **not** derive — every other manifest (`views`, `pages`, `app`, `ai_passes`,
`human_inputs`, `completeness`) has an extractor; `forms` does not, so a project wanting non-default
post-create behavior must hand-author it.

> **Objective.** Add `extract_forms()` — a deterministic extractor that derives the per-entity
> `on_create` knob from an **explicit, structured key-line** in the requirements prose, slotting in
> beside `extract_views` (`extract.py:101`). Closed-vocabulary, `$0` LLM, forensic
> `ExtractionRecord` trail, round-trip-validated by the already-wired `parse_forms`. **Not** a
> free-text NLP inference step (see §3) — it reads a declared directive, exactly as `extract_views`
> reads `Kind:`/`Root:`.

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2. The planning pass (`FORMS_EXTRACTION_PLAN.md`
> §Discoveries) made one **disposition-changing** finding (D-5) plus three architecture resolutions:

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| The feature is worth building now | **The real strtd8 corpus (16 entities) has ZERO prose describing post-create behavior** — no directives, no rapid/sequential-entry intent (the main `form` use case). The derivation half has no input to derive from. | **Status → DEFERRED.** Build only when a real project authors `forms:` overrides and asks them to be derived. |
| `extract_forms` is a separate extractor with its own candidate slot (OQ-2 open) | One `views.yaml` candidate slot + a `first-non-None-wins` guard (`extract.py:100`) — a separate extractor would overwrite `extract_views` or be dropped across docs | Must **fold into `extract_views`** — mandatory, not a choice. A separate extractor would have been a latent bug. |
| Round-trip validation needs new wiring (FR-FX-5) | `extract.py` already calls `parse_forms` in the `views.yaml` round-trip (the shipped gate-half) | FR-FX-5 is **free** — no new round-trip code. |
| Directive home is open (OQ-1) | `key_lines()` parses any section; entities are *table*-bodied sections (awkward for key-lines); a dedicated `Forms:` section mirrors `extract_views` exactly | OQ-1 → a **`Forms:` section** with `<Entity>: <archetype>` key-lines. |

**Resolved open questions:**
- **OQ-1 → `Forms:` section + `<Entity>: <archetype>` key-lines** (reuses `key_lines` +
  `graph.resolve_entity` verbatim).
- **OQ-2 → fold into `extract_views`** — forced by the single-candidate/first-wins guard, not a
  preference.
- **OQ-3 → sorted-by-entity** for byte-stable round-trips.
- **OQ-4 → name-only, schema-light** (PK-suitability stays the generator's `FR-FS-8` job).
- **OQ-5 → DEFER.** No prose input exists in the real corpus; the gate-half is the right stopping
  point. **This is the headline outcome** — the planning pass caught a speculative build at
  document cost, before shipping an extractor nobody's prose feeds.

> **Why this isn't WONTFIX:** the need is plausible-but-unproven, not refuted. Two concrete
> revisit triggers (a project expressing post-create intent for ≥2 entities, or the knob growing to
> `on_update`/`on_delete`) would flip this to a ~½-day build whose architecture is already settled
> below.

---

## 1. Problem Statement

The manifest-extraction pipeline (`extract.py`) turns a requirements/design doc into six structured
manifests, each via a dedicated deterministic extractor that reads **structured prose**
(section-titled key-lines like `View: X` → `Kind: dashboard`, or reinforced annotations) and emits
an `ExtractionRecord` per decision (EXTRACTED / DEFAULTED / NOT_EXTRACTED — the forensics trail).

| Manifest | Extractor | Reads |
|----------|-----------|-------|
| `views.yaml` (`views:`) | `extract_views` | `View:`-titled sections + key-lines |
| `pages.yaml` | `extract_pages` | page sections |
| `app.yaml` | `extract_app` | scaffold/runtime key-lines |
| `ai_passes.yaml` | `extract_ai_passes` | pass sections |
| `human_inputs.yaml` | `extract_human_inputs` | "ONLY HUMANS ENTER THIS" phrasing + field annotations |
| `completeness.yaml` | `extract_completeness` | completeness section signals |
| **`views.yaml` (`forms:`)** | **— none —** | **the gap this closes** |

The `forms:` section is parsed (`parse_forms`) and validated at ingestion (the round-trip gate runs
both `parse_views` *and* `parse_forms` over an emitted `views.yaml`), and honored by the generator
(`on_create` → 303 destination). But it is never **produced** by ingestion — so the knob is
authored-or-absent, never derived from the doc that already describes the desired flow.

## 2. Requirements

**FR-FX-1 (deterministic key-line, not NLP).** `extract_forms` derives `on_create` from an
**explicit declared directive** in the prose — a closed-vocabulary token (`detail | list | form |
confirmation`), parsed like `extract_views` parses `Kind:`. It performs **no** free-text intent
inference (§3). Unrecognized tokens are recorded `NOT_EXTRACTED` with a reason, never guessed.

**FR-FX-2 (folds into `extract_views`, not a separate slot).** Planning (D-1) showed `views.yaml`
has a **single** candidate slot under a `first-non-None-wins` guard, so the forms derivation MUST
fold into `extract_views` (attaching a `forms:` key to its returned dict —
`{"views": [...], "forms": {"Activity": {"on_create": "form"}}}`), not register a separate
candidate. A standalone `extract_forms` would overwrite the `views:` payload or be dropped across
multi-doc runs.

**FR-FX-3 (entity resolution).** Each directive names an entity; resolve it via
`graph.resolve_entity()` (the same path `extract_views`/`extract_human_inputs` use). An
unresolvable entity → `NOT_EXTRACTED` record with reason `entity not declared`, the directive
skipped — never a hard failure (degrade, FR-W13 ethos).

**FR-FX-4 (forensic records).** Emit one `ExtractionRecord` per directive: `EXTRACTED` (value =
the archetype) for a resolved entity + valid token; `NOT_EXTRACTED` (with reason) for an unknown
entity or token. Path convention `/forms/<Entity>` (mirroring `/views/<ident>`, `/fields/<target>`).

**FR-FX-5 (round-trip safe — already wired).** The emitted fragment, serialized into `views.yaml`,
passes `parse_forms(known_entities=...)` — which `extract.py`'s round-trip **already calls** (the
shipped gate-half, D-2). So this requirement needs **no new code**: "extracted" ⇒ "generatable" by
construction, validated by the existing gate.

**FR-FX-6 (default = silence).** Absence of any directive yields `None` (no `forms:` section) —
which the generator already reads as "every entity → `detail`". The extractor never emits a
directive for an entity the doc didn't mention (no `detail` noise).

**FR-FX-7 (idempotent + byte-stable).** Same doc → same fragment, deterministically ordered
(declaration order or sorted — OQ-3), so re-ingestion is a no-op and the round-trip is stable.

**FR-FX-8 (tests).** Unit: a directive section → the right `{entity: on_create}` map; unknown
token → `NOT_EXTRACTED`; unknown entity → `NOT_EXTRACTED`; no directive → `None`; emitted fragment
round-trips through `parse_forms`. An end-to-end extract.py test: a doc with both `View:` sections
and form directives produces a `views.yaml` carrying **both** `views:` and `forms:`, gate-green.

## 3. Non-Requirements

- **No free-text / NLP intent inference.** "Take them to a fresh form to add another" → `form` is
  **out of scope** — that is an LLM/fuzzy concern, antithetical to the deterministic, auditable
  extractor pattern (and would belong in a different layer, not `manifest_extraction`). This
  extractor reads a *declared* archetype token only.
- **No new vocabulary.** Strictly the four `on_create` archetypes `parse_forms` already accepts;
  this extractor never invents destinations.
- **No `on_update`/`on_delete`** — those knobs don't exist in `forms_manifest` yet (a separate
  increment); nothing to extract.
- **No schema/PK validation** — that's the generator's job (no-PK fallback is FR-FS-8). The
  extractor only resolves entity *names*, not their suitability.
- **No edits to the `views:` extraction** beyond the integration seam needed to co-emit `forms:`.

## 4. Open Questions

All five v0.1 open questions were resolved by the planning pass — see §0. **OQ-5 is the disposition:
DEFER** (no prose input in the real corpus). The §"Build plan" in `FORMS_EXTRACTION_PLAN.md` is held
ready, not executed, with two concrete revisit triggers.

---

*v0.2 — Post-planning self-reflective update. **Disposition changed from build → DEFER**: the real
16-entity strtd8 corpus contains no post-create-behavior prose to derive from, so the derivation
half has no input and the shipped gate-half is the right stopping point. 3 architecture OQs resolved
(fold-into-`extract_views` is forced by the single-candidate guard; round-trip already validates
`forms:`; `Forms:`-section directive home). The pre-planning insight held: deterministic key-line
extraction, never NL inference (§3). The loop's value here was catching a speculative build at
document cost.*
