# Stakeholder Panel — Roster (persona) format

**The canonical persona format** the Stakeholder Panel consumes. This is the single shape any tool
should target when producing personas for the panel (native authoring, or an external-format
ingestion adapter). It is a plain YAML file — `docs/kickoff/inputs/stakeholders.yaml` — read by
`startd8.stakeholder_panel.roster.parse_roster`.

> **Drift guard (FR-1 / R2-F2).** The field lists in the machine-readable block below are asserted
> equal to the `PersonaBrief` / `Roster` dataclasses **and** the `parse_roster` allow-set by
> `tests/unit/stakeholder_panel/test_roster_schema_doc.py`. Editing a model field without updating
> that block (or vice-versa) fails the build — so this document cannot silently lie.

---

## Document shape

```yaml
domain: stakeholders            # REQUIRED discriminator — must be exactly "stakeholders"
provenance_default: authored    # optional; free-text provenance marker
protocol_version: "1.0"         # optional; the roster contract version (see Versioning)
personas:                       # the roster
  - role_id: product-owner      # REQUIRED — stable kebab-case address (see role_id rules)
    display_name: Product Owner # REQUIRED — the human name the persona speaks as
    goals: ["ship the MVP by Q3"]
    constraints: ["budget <= $5k/mo"]
    known_positions: ["no PII in logs"]
    out_of_scope: ["database engine choice"]
    answers_for: ["Order.*", "pricing"]   # routing hints (value_path/entity prefixes)
```

## Persona fields (`PersonaBrief`)

| Field | Type | Required | Meaning |
|-------|------|----------|---------|
| `role_id` | string | **yes** | Stable kebab-case address (`^[a-z0-9]+(-[a-z0-9]+)*$`); unique across the roster; how a question is routed to this persona. |
| `display_name` | string | **yes** | Who the persona says it is. |
| `goals` | list[string] | — | What this persona is trying to achieve (its lens). |
| `constraints` | list[string] | — | Hard limits it enforces (budget, deadline, compliance). |
| `known_positions` | list[string] | — | Opinions/decisions already made that it will voice. |
| `out_of_scope` | list[string] | — | Topics it must decline — drives the panel's *defer* behavior. |
| `answers_for` | list[string] | — | Routing hints: `value_path`/entity prefixes this persona owns (e.g. `Order.*`). |

A persona needs **at least one** of `goals` / `constraints` / `known_positions` (an otherwise-empty
brief is reported invalid). Scalar values are coerced to single-element lists.

## Roster envelope (`Roster`)

| Key | Required | Meaning |
|-----|----------|---------|
| `domain` | **yes** | Must be `stakeholders` (the strict-parse discriminator). |
| `personas` | — | The list of persona briefs (an empty/absent list is reported "no personas"). |
| `provenance_default` | — | Free-text provenance marker (e.g. `authored`). |
| `protocol_version` | — | The roster contract version; defaults to the SDK's current. |

## Strict parse rules (`parse_roster`, FR-2)

`parse_roster` is **strict on document structure** and **lenient-coercing on field element types**:

- Root must be a YAML **mapping**; an empty document is an empty roster.
- `domain` must equal `stakeholders`.
- **Unknown top-level or per-persona keys are rejected** (`RosterError`) — a typo guard. The allowed
  keys are derived from the dataclasses, never hand-listed.
- Element types are coerced (a scalar becomes a one-item list); **content** problems (duplicate
  `role_id`, empty brief) are reported by `validate_roster` as a soft list, not raised.

## Versioning (forward-compat)

`protocol_version` is read, not merely tolerated:

- A roster whose **major** version exceeds the SDK's is **rejected** (upgrade the SDK).
- A roster with the **same major but a newer minor** relaxes the unknown-top-level-key guard to a
  **warning** — so an additive future key does not hard-fail an older SDK.

## Targeting this format from an external tool

Emit YAML matching the shape above (or build `PersonaBrief`/`Roster` objects and serialize via
`Roster.to_dict`). Do **not** hand-write around the schema — round-trip through `parse_roster` +
`validate_roster` to get the same guarantees the panel enforces. External *formats* (a different
persona schema) are converted by a registered ingestion adapter (see the ingestion requirements),
not by targeting this doc directly.

---

<!-- ROSTER-SCHEMA-FIELDS: machine-checked block; keep in sync with the models (test enforces). -->
```yaml
persona_fields: [role_id, display_name, goals, constraints, known_positions, out_of_scope, answers_for]
roster_top_level_keys: [domain, personas, provenance_default, protocol_version]
```
