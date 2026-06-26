"""FR-VIP-1/3/5/9/10 — conventions prose is deterministically compiled to conventions.yaml.

The value-input proving slice: `extract_conventions` turns a `## Technology conventions` section into
`conventions.yaml`, round-tripped through `parse_conventions` (extract_manifests raises if it fails).
Pins: structured fields (stack/module_paths/naming/data_model) extract semantically (FR-VIP-10); a bad
data-model enum is flagged NOT_EXTRACTED, never guessed (FR-VIP-5 / contract §3); aspect/layer
synonyms normalize; a second project's prose extracts through the same code unchanged (FR-VIP-9).
"""

from __future__ import annotations

import yaml

from startd8.manifest_extraction import Status, extract_manifests

# Project-agnostic prose (no household identifiers — FR-VIP-9). `data layer`/`templates dir`/`metric
# prefix` exercise the spaces→underscore + synonym normalization; `Weekday: martian` is a bad enum.
_DOC = """
# WidgetCo conventions (prose source)

## Technology conventions

- Language: python
- Field authorship: prisma/human_inputs.yaml
- Provenance default: templated

| Layer | Choice | Plain meaning |
|-------|--------|---------------|
| framework | fastapi | server-rendered |
| data layer | sqlmodel | pydantic-compatible |
| database | sqlite | local-only |

### Module layout

| Role | Path |
|------|------|
| tables | app.tables |
| templates dir | app/templates |

### Naming

| Aspect | Style |
|--------|-------|
| routes | kebab-case |
| metric prefix | widget_ |

### Data-model conventions

- Money: cents
- Recurrence: structured
- Weekday: martian

#### Computed fields
- a derived forecast

#### Deferred
- a later feature

### Architecture invariants

- CONTRACT-FIRST: one schema.prisma is the source of truth.
- SELF-HOSTED: data stays on the local network.
""".strip()


def _conventions(doc=_DOC):
    res = extract_manifests({"reqs.md": doc})
    raw = res.manifests.get("conventions.yaml")
    return (yaml.safe_load(raw) if raw else None), res


def test_emitted_and_round_trips():
    # extract_manifests round-trips the candidate through parse_conventions; a failure would raise.
    got, res = _conventions()
    assert got is not None
    assert got["domain"] == "conventions"


def test_structured_fields_extract_semantically():
    got, _ = _conventions()
    assert got["language"] == "python"
    assert got["provenance_default"] == "templated"
    assert got["field_authorship"] == "prisma/human_inputs.yaml"
    assert got["stack"] == {"framework": "fastapi", "data_layer": "sqlmodel", "database": "sqlite"}
    assert got["module_paths"] == {"tables": "app.tables", "templates_dir": "app/templates"}
    assert got["naming"] == {"route_style": "kebab-case", "metric_prefix": "widget_"}


def test_data_model_extracts_and_flags_bad_enum():
    got, res = _conventions()
    dm = got["data_model"]
    assert dm["money"] == "cents" and dm["recurrence"] == "structured"
    assert "weekday" not in dm  # `martian` is out of vocabulary → dropped, not guessed
    assert dm["computed_fields"] == ["a derived forecast"]
    assert dm["deferred"] == ["a later feature"]
    flagged = [
        r for r in res.records
        if r.manifest == "conventions.yaml" and r.status == Status.NOT_EXTRACTED
        and r.value_path.endswith("/weekday")
    ]
    assert flagged and "vocabulary" in flagged[0].reason


def test_architecture_notes_carried_verbatim():
    got, _ = _conventions()
    assert got["architecture_notes"] == [
        "CONTRACT-FIRST: one schema.prisma is the source of truth.",
        "SELF-HOSTED: data stays on the local network.",
    ]


def test_every_value_carries_a_sourceref():
    _, res = _conventions()
    extracted = [r for r in res.records if r.manifest == "conventions.yaml"
                 and r.status == Status.EXTRACTED]
    assert extracted and all(r.source is not None and r.source.doc == "reqs.md" for r in extracted)


def test_no_conventions_section_emits_nothing():
    got, res = _conventions("## Overview\n\nNo conventions here.\n")
    assert got is None
    assert "conventions.yaml" not in res.manifests


def test_second_project_extracts_through_same_code(  ):
    # FR-VIP-9: a different stack/language extracts unchanged — no built-in vocabulary.
    doc = (
        "## Technology conventions\n\n- Language: go\n\n"
        "| Layer | Choice | Plain meaning |\n|--|--|--|\n| framework | gin | x |\n"
    )
    got, _ = _conventions(doc)
    assert got["language"] == "go"
    assert got["stack"] == {"framework": "gin"}
    assert "data_model" not in got  # optional subsection absent
