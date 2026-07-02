# Persona Format & Ingestion Implementation Plan

**Version:** 1.0
**Date:** 2026-07-02
**Tracks requirements:** `PERSONA_FORMAT_AND_INGESTION_REQUIREMENTS.md` v0.2
**Status:** Planned (pre-implementation)

---

## 0. Grounding: what the infra survey established

- **`manifest_extraction/` engine is NOT reusable** — hard-wired to the buildable-app grammar
  (imports `backend_codegen`/`view_codegen`/`languages.prisma_parser`; `EntityGraph` is a Prisma IR;
  the candidate/round-trip file set is a fixed literal). Do **not** enroll the roster (reaffirms panel
  OQ-1). Its **`Status`/`SourceRef`/`ExtractionRecord`** dataclasses (`models.py`) are the only
  liftable pieces — and we decline to lift them for v1 (see OQ-6).
- **`kickoff_inputs/` is the rail to mirror.** Uniform contract: `parse_X(text) -> frozen Manifest`,
  a `domain:` discriminator, **loud-fail `ValueError` on non-mapping root / wrong domain / unknown
  top-level key** (`conventions.py:117`, `business_targets.py:100`). No registry — dispatch is the
  literal `round_trips` dict in `extract.py`, which we do not touch.
- **`concierge/derive/` is NOT reusable** — Pydantic→Prisma relational derivation; a roster has no
  entities. Only its "unratified candidate + report, CLI-sole-writer" *ceremony* transfers as an idea.
- **No adapter registry exists**, but the **entry-point idiom does** — `providers/registry.py:131`,
  `workflows/registry.py:155`, `secrets/registry.py:55` all use `importlib.metadata.entry_points(group=…)`
  with an old-Python fallback. Mirror it; do not invent a mechanism.
- **Template plumbing is done** — the roster is already in `_KICKOFF_FILES` (`writes.py:41`),
  download-manifest-derived, and inside the byte-identity test. "Formalize" ≠ new plumbing.
- **The gap is validation rigor + ingestion**: `Roster.from_dict` is permissive/coercive
  (`models.py:40,123`) — no typo guard — whereas the pilot converter (`reviewer_roles_to_roster.py`)
  is an untested out-of-SDK script that hand-writes YAML instead of round-tripping `Roster`.

## 1. Module layout

| File | Responsibility | Requirements |
|------|----------------|--------------|
| `stakeholder_panel/roster.py` (extend) | `parse_roster(text)` — strict structural gate (peer to `kickoff_inputs`), then delegate to `Roster.from_dict` + `validate_roster`. `load_roster` adopts it. | FR-2 |
| `stakeholder_panel/adapters/__init__.py` | Adapter protocol (`name`, `adapt(text)->Roster`) + registry (`discover()`, `get_adapter()`, `available()`) — copied from `providers/registry.py` | FR-3, FR-4 |
| `stakeholder_panel/adapters/role_rubric.py` | The generic `role-rubric` adapter (promoted `convert()`), emitting a **validated** `Roster` | FR-5 |
| `stakeholder_panel/ingest.py` | `ingest(format_name, source_text) -> Roster`: run adapter → serialize → **reparse via `parse_roster` (round-trip gate)** → return; stamp provenance | FR-3, FR-6, FR-7, OQ-7 |
| `cli_panel.py` (extend) | `startd8 panel import --format <name> <src> [--out] [--force]` | FR-6 |
| `docs/design/stakeholder-panel/ROSTER_SCHEMA.md` | Authoritative persona-format schema reference | FR-1 |
| `pyproject.toml` | entry-point group `startd8.stakeholder_panel.roster_adapters` with `role-rubric` | FR-4, FR-5 |

## 2. FR-2 — strict roster parser (resolves OQ-1/OQ-2)

- **OQ-1 → stays in `stakeholder_panel/roster.py`** (not moved to `kickoff_inputs/`): keeps the panel
  self-contained (M0 principle); we copy the *contract*, not the package. `manifest_extraction`'s
  `round_trips` dict is untouched (the roster is not an app manifest).
- **OQ-2 → strict document structure, coerced field elements.** `parse_roster(text)`:
  1. `yaml.safe_load` → must be a mapping (else `RosterError`).
  2. `domain` must equal `"stakeholders"` (discriminator, else `RosterError`).
  3. Reject **unknown top-level keys** (allow-set: `domain`, `provenance_default`, `personas`,
     `protocol_version`) and **unknown per-persona keys** (allow-set = `PersonaBrief` fields) — the
     typo guard.
  4. Then `Roster.from_dict` (unchanged coercion of element types) + return.
  `load_roster` calls `parse_roster` (so structural strictness is the default); `validate_roster`
  still does the **soft field-level** reporting (unique ids, required fields, non-empty briefs).
  `assess_roster` already catches `RosterError` → reports `invalid` gracefully (no change needed).
- Back-compat: valid rosters (template + pilot output) use only known keys, so nothing breaks; the
  M0 "permissive" note in the panel requirements is updated.

## 3. FR-3/FR-4/FR-5 — adapter + registry (resolves OQ-3/OQ-4)

- **OQ-3 → adapter = `adapt(text: str) -> Roster`** (mirrors `parse_X(text)`; text not path/dict, so
  the CLI owns file I/O). Entry-point group **`startd8.stakeholder_panel.roster_adapters`**
  (namespaced like `startd8.contractors.deterministic_providers`).
- **OQ-4 → `role-rubric` lives in SDK core** as a built-in adapter — the
  `key/label/lens/rubric/coverage/out_of_scope` shape is a generic format family, not benchmark-
  specific. Named `role-rubric`.
- Registry mirrors `providers/registry.py`: module-level cache, `discover()` (entry points + built-ins),
  `get_adapter(name)` (→ clear error listing `available()` on miss), `register()` for tests.
- `role_rubric.adapt` = the pilot `convert()` mapping, but building `PersonaBrief`/`Roster` objects
  directly and returning the `Roster` (no `yaml.safe_dump`); the CLI serializes once, at the end.

## 4. FR-6/FR-7 — ingestion + surface (resolves OQ-5/OQ-6/OQ-7)

- **OQ-5 → `startd8 panel import`** subcommand (panel CLI is the writer surface, NR-7/OQ-7 of the
  panel spec). Signature: `--format <name>` (required), `SOURCE` path (arg), `--out` (default
  `docs/kickoff/inputs/stakeholders.yaml` under `--project`), `--force` (refuse clobber otherwise).
- **`ingest(format_name, source_text)`** (in `ingest.py`): `get_adapter(name).adapt(text)` → `Roster`
  → `yaml.safe_dump(roster.to_dict())` → **`parse_roster(dumped)` + `validate_roster`** (OQ-7
  round-trip gate: an adapter that emits a bad roster fails loudly here, not at panel-load time) →
  return `(roster, yaml_text)`.
- **OQ-6 → header-level provenance only** (FR-7). Prepend `# GENERATED from <source> via <format>
  adapter — edit the source, re-run import`. No per-field `ExtractionRecord` (ingestion maps a whole
  structured file, not prose; per-field traceability is overkill). `manifest_extraction/models.py`
  stays unlifted.
- **OQ-7 → yes, round-trip gate** (above).

## 5. FR-1 — schema reference

Write `ROSTER_SCHEMA.md`: the `PersonaBrief` fields (role_id rules, display_name, goals, constraints,
known_positions, out_of_scope, answers_for) + `Roster` envelope (`domain`, `provenance_default`,
`personas`) + the strict-parse rules (FR-2) + "how to target this from an external tool." Cross-link
from the template header and `reviewer_roles.yaml`'s "panel-consumable" note.

## 6. Test plan

- `parse_roster`: strict rejects unknown top-level key, unknown persona key, wrong `domain`, non-
  mapping root; accepts the shipped template + a valid roster; still coerces scalar→list fields.
- registry: `discover()` finds the built-in `role-rubric`; `get_adapter("nope")` errors with the
  available list; `register()` works for a fake adapter.
- `role-rubric` adapter: converts a `reviewer_roles.yaml` fixture → validated `Roster` with the exact
  field mapping (incl. `out_of_scope` pass-through and `answers_for` = rubric names); round-trips
  through `parse_roster` cleanly.
- `ingest`: round-trip gate rejects an adapter that emits an invalid roster; provenance header
  present; deterministic output (same input → byte-identical roster).
- CLI: `panel import --format role-rubric <fixture> --out <tmp>` writes a valid roster; `--force`
  clobber guard; unknown `--format` lists adapters; then `panel list <tmp-project>` succeeds ($0).
- Regression: existing M0–M3 roster/panel tests still green (strict parse must not break valid input).

## 7. Sequencing

- **N0** — `parse_roster` strict gate + `ROSTER_SCHEMA.md` (formalization; no new deps). Updates the
  panel spec's "permissive" note. Ship-able alone.
- **N1** — adapter protocol + registry + `role-rubric` built-in + entry point (ingestion core, no CLI).
- **N2** — `ingest.py` round-trip gate + `startd8 panel import` CLI + provenance header.
- **N3** — (optional) retire/redirect the benchmarking one-off script to call `startd8 panel import`;
  add a fixture from `reviewer_roles.yaml`.

Each increment branch-first, tested, lint-clean before the next.
