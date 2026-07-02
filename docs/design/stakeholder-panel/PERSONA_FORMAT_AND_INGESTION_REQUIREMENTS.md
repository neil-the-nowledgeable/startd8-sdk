# Persona Format & Ingestion Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-07-02
**Status:** Draft
**Extends:** `STAKEHOLDER_PANEL_REQUIREMENTS.md` v0.3 (FR-1/FR-2 roster, OQ-1 grammar decision)
**Companion plan:** `PERSONA_FORMAT_AND_INGESTION_PLAN.md` v1.0

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2, after surveying the SDK's parse/extract infra.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| "Formalize the template" is substantial work | Template **plumbing is already complete** — the roster is in `_KICKOFF_FILES` (`writes.py:41`), download-derived, byte-identity-guarded (M0) | **FR-1 narrowed** to a *schema reference doc*; the real formalization is the strict parser (FR-2) |
| We might reuse `manifest_extraction` to parse the roster | Engine is **welded to the app-codegen/Prisma grammar** — not reusable; only its `Status/SourceRef/ExtractionRecord` dataclasses are liftable | **FR-8 firmed**; roster stays out of the grammar (reaffirms panel OQ-1); provenance dataclasses declined for v1 |
| Strict vs. permissive validation is a hard conflict | Clean split available: **strict on document structure** (unknown-key typo guard) + **coerce field elements** + soft-report content | **FR-2 firmed** (OQ-2 resolved) |
| A new adapter-registry mechanism is needed | The **entry-point idiom** (`providers/registry.py:131`) is the established rail | **FR-4 firmed** — mirror it, don't invent (OQ-3 resolved) |
| The pilot script can be reused directly | It hand-writes YAML and is benchmark-named | **FR-5 firmed**: emit through `Roster` (re-validated), generalize to a `role-rubric` **format family** |
| Ingestion may need auto-detect / per-field provenance | Explicit adapter + a generated **header** suffices; a **round-trip gate** is the quality bar | **FR-7 firmed** header-only (OQ-6); **NR-4** auto-detect out; OQ-7 → round-trip gate in |

**Resolved open questions:**
- **OQ-1 → Stays in `stakeholder_panel/roster.py`** (not moved to `kickoff_inputs/`) — copy the
  *contract*, keep the panel self-contained.
- **OQ-2 → Strict document structure, coerced field elements, soft content reporting.**
- **OQ-3 → `adapt(text: str) -> Roster`; group `startd8.stakeholder_panel.roster_adapters`.**
- **OQ-4 → `role-rubric` adapter lives in SDK core** (generic format family, not benchmark-specific).
- **OQ-5 → `startd8 panel import`** subcommand (panel CLI is the writer surface).
- **OQ-6 → Header-level provenance only**; `manifest_extraction` dataclasses left unlifted.
- **OQ-7 → Yes — ingestion round-trip-gates** (emit roster → reparse via FR-2 before accepting).

---

## 1. Problem Statement

The Stakeholder Panel (M0–M3) ships a persona **roster** format (`stakeholders.yaml`) — the
`PersonaBrief`/`Roster` contract in `stakeholder_panel/models.py`, projected as a template by
Concierge `instantiate-kickoff` and loaded by `stakeholder_panel/roster.py`. The Summer-2026 pilot
proved a second demand: an **external** persona format (`reviewer_roles.yaml`:
`key/label/lens/rubric/coverage/out_of_scope`) was converted into a roster by a **one-off argparse
script** living outside the SDK, untested, hand-writing YAML rather than round-tripping through
`Roster`.

Two gaps follow: (a) the native roster format is *packaged* but not *formalized* — it has no strict
canonical parser gate (unlike the sibling `kickoff_inputs` value YAMLs), so a typo'd roster is
silently coerced rather than loudly rejected; and (b) there is no in-SDK, reusable, testable path to
**ingest** an external persona format into a validated roster — every new source format would spawn
another one-off script.

This document specifies (1) formalizing the native roster template with a strict parser peer to
`kickoff_inputs`, and (2) a pluggable persona-format **ingestion adapter** capability. It also settles
the requester's "if useful" question: **which existing SDK parsing/extraction infra to reuse vs.
build fresh.**

| Component | Current State | Gap |
|-----------|--------------|-----|
| Native roster template | Packaged + projected + byte-identity-guarded (M0) | No strict parser gate; `Roster.from_dict` is permissive (coerces, ignores unknown top-level keys) — no typo guard |
| External format ingestion | One-off script in `benchmarking/` repo (`reviewer_roles_to_roster.py`) | Not in SDK, untested, bypasses `Roster` validation; each new format = another script |
| Format-adapter plumbing | None | No adapter contract, no registry — no way to register/discover persona-format adapters |
| Reuse of extraction infra | Ad hoc | Unclear which of `manifest_extraction` / `kickoff_inputs` / `concierge/derive` to lean on |

---

## 2. Requirements

### A. Formalize the native roster format

- **FR-1 — Canonical persona-format schema (doc).** The `PersonaBrief`/`Roster` shape is the *single
  canonical* persona format. Template **plumbing already exists** (M0: packaged, projected,
  download-derived, byte-identity-guarded), so FR-1 is scoped to an **authoritative schema reference**
  (`ROSTER_SCHEMA.md`) any external tool can target — mirroring how `reviewer_roles.yaml` documents
  itself as panel-consumable. Cross-linked from the template header.
- **FR-2 — Strict roster parser gate.** Add a strict canonical parser (`parse_roster`) for
  `stakeholders.yaml`, mirroring the `kickoff_inputs.parse_conventions` *contract* (kept in
  `stakeholder_panel/roster.py`, not moved). It loud-fails (`RosterError`) on a non-mapping root, a
  wrong/absent `domain:` discriminator, and **unknown top-level or per-persona keys** (typo guard).
  It is the one authority shared by the template *and* every ingested roster. Reconciled split:
  **strict on document structure**, **coerce field element types** (unchanged `Roster.from_dict`
  behavior), and **soft-report content** via `validate_roster` (unique ids / required fields /
  non-empty briefs). `load_roster` adopts `parse_roster`; `assess_roster` already degrades a
  `RosterError` to `invalid`.

### B. External persona-format ingestion

- **FR-3 — Ingestion adapter contract + round-trip gate.** Define a persona-format **adapter**:
  `adapt(text: str) -> Roster` that emits through the `Roster` contract (never hand-written YAML).
  Ingestion (`ingest()`) then **round-trip-gates** (OQ-7): serialize the adapter's `Roster` → reparse
  via the FR-2 strict `parse_roster` + `validate_roster` before accepting, so a buggy adapter fails
  loudly at import time, not at panel-load time. Ingestion is **one-way** (external → roster).
- **FR-4 — Pluggable adapter registry.** Adapters are discoverable via the entry-point group
  **`startd8.stakeholder_panel.roster_adapters`**, mirroring `providers/registry.py`
  (`importlib.metadata.entry_points` + old-Python fallback), so a downstream project can register its
  own persona-format adapter without editing the SDK. Provide `discover()`, `get_adapter(name)`
  (missing ⇒ error listing `available()`), and `register()` for tests.
- **FR-5 — First built-in adapter (role-rubric).** Promote the pilot converter into a **generic**
  `role-rubric` adapter (the `key/label/lens/rubric/coverage/out_of_scope` shape), named for the
  *format family*, not the benchmark, living in SDK core. It builds `PersonaBrief`/`Roster` objects
  directly and returns a **validated `Roster`** (no raw `yaml.safe_dump`). Faithful mapping:
  `key→role_id`, `label→display_name`, `lens→goals`, `rubric→known_positions`+`answers_for`,
  `coverage→constraints`, `out_of_scope→out_of_scope`.
- **FR-6 — Ingestion surface (CLI).** `startd8 panel import --format <name> <source> [--out <path>]
  [--force]` runs the named adapter, round-trip-gates (FR-3), and writes the roster (default
  `docs/kickoff/inputs/stakeholders.yaml` under `--project`; refuses to clobber without `--force`) —
  CLI-as-sole-writer. Unknown format ⇒ a clear error listing registered adapters.
- **FR-7 — Ingested-roster provenance (header).** An ingested roster carries a generated header
  (`# GENERATED from <source> via <format> adapter — edit the source, re-run import`) so it is
  distinguishable from a hand-authored roster and regeneratable. Header-level only — no per-field
  `ExtractionRecord` (ingestion maps a whole structured file, not prose).

### C. Reuse decision (the "if useful")

- **FR-8 — Reuse the right rails, avoid the wrong ones.** The capability **reuses**: the
  `kickoff_inputs` per-domain `parse_X(text)->Manifest` + `domain:`-discriminator + loud-fail
  contract (FR-2), and the `providers/registry.py` entry-point idiom (FR-4). It **does not** enroll
  the roster into the `manifest_extraction` grammar or reuse `concierge/derive` — both are welded to
  the buildable-app **relational/Prisma** grammar and would wrongly drag the roster into app codegen
  + round-trip-to-schema validation (reaffirms panel OQ-1).

---

## 3. Non-Requirements

- **NR-1 — Not a manifest-extraction grammar kind.** Reaffirms panel OQ-1: the roster is a plain
  value input the panel reads; it is not an app-codegen manifest and `manifest_extraction/` is not
  touched.
- **NR-2 — No prose/NLP extraction.** Personas come from *structured* YAML (native) or a *structured*
  external format via an adapter — never NL-extracted from freeform markdown.
- **NR-3 — No reuse of `concierge/derive`.** That path introspects Pydantic → Prisma entities; a
  persona roster has no entities/relations to derive.
- **NR-4 — No format auto-detection.** The caller names the adapter (`--format`); the SDK does not
  guess an unknown file's format.
- **NR-5 — One-way only.** No external ⇐ roster writeback or bidirectional sync; the source format
  stays the upstream authority.
- **NR-6 — No new template plumbing.** Packaging/projection/download/byte-identity (M0, `writes.py`)
  are reused unchanged.
- **NR-7 — No SDK coupling to a downstream format.** The built-in adapter targets the *role-rubric
  format family*, not any one project's file.

---

## 4. Open Questions

*(OQ-1 through OQ-7 resolved by the planning pass — see §0.)*

- **OQ-8 (deferred)** — Should the benchmarking one-off `reviewer_roles_to_roster.py` be retired in
  favor of `startd8 panel import --format role-rubric` (N3), or kept as a thin shim that calls the
  SDK? Cosmetic; resolve when N2 lands.
- **OQ-9** — If a future external format is *lossy* into the roster (fields with no `PersonaBrief`
  home), does the adapter drop them silently, warn, or stash them in a passthrough? v1 `role-rubric`
  is lossless, so this is dormant until a second adapter needs it.

---

*v0.2 — Post-planning self-reflective update. 1 requirement narrowed (FR-1: template plumbing already
done → schema doc), 6 firmed (FR-2/FR-3/FR-4/FR-5/FR-6/FR-7), 1 non-requirement added implicitly
(header-only provenance), 7 open questions resolved, 2 residual/deferred. Reuse verdict settled
(FR-8): mirror `kickoff_inputs` + `providers/registry.py`; do **not** touch `manifest_extraction` or
`concierge/derive`. Companion plan: `PERSONA_FORMAT_AND_INGESTION_PLAN.md` v1.0.*
