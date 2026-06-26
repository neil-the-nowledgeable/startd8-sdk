"""FR-VIP-2 — `parse_conventions` is the strict round-trip authority for conventions.yaml.

Pins: a well-formed sheet parses; the `data_model` enums + unknown top-level keys + a missing
`language` + a wrong `domain` all loud-fail with a clear, keyed message (so a malformed value YAML
fails the round-trip gate at ingestion, never at generation time).
"""

from __future__ import annotations

import pytest

from startd8.kickoff_inputs import (
    ConventionsManifest,
    DataModelConventions,
    parse_conventions,
)

GOOD = """
domain: conventions
provenance_default: templated
language: python
stack: {framework: fastapi, data_layer: sqlmodel}
module_paths: {tables: app.tables}
naming: {route_style: kebab-case, metric_prefix: widget_}
data_model:
  money: cents
  datetime: utc
  recurrence: structured
  references: loose-allowed
  weekday: iso
  computed_fields: ["run-out forecast"]
  deferred: ["adherence (FR-21)"]
field_authorship: prisma/human_inputs.yaml
architecture_notes:
  - "CONTRACT-FIRST: one schema is the source of truth."
"""


def test_parses_a_well_formed_sheet():
    m = parse_conventions(GOOD)
    assert isinstance(m, ConventionsManifest)
    assert m.language == "python" and m.domain == "conventions"
    assert m.provenance_default == "templated"
    assert m.stack == {"framework": "fastapi", "data_layer": "sqlmodel"}
    assert m.naming["metric_prefix"] == "widget_"
    assert isinstance(m.data_model, DataModelConventions)
    assert m.data_model.money == "cents" and m.data_model.weekday == "iso"
    assert m.data_model.computed_fields == ["run-out forecast"]
    assert len(m.architecture_notes) == 1


def test_data_model_is_optional():
    m = parse_conventions("language: go\n")
    assert m.language == "go" and m.data_model is None and m.stack == {}


@pytest.mark.parametrize(
    "bad, msg",
    [
        ("language: python\ndata_model:\n  money: dollars\n", "`data_model.money` must be one of"),
        ("language: python\ndata_model:\n  cadence: weekly\n", "unknown keys"),
        ("language: python\nbogus: x\n", "unknown top-level keys"),
        ("domain: views\nlanguage: python\n", "`domain` must be 'conventions'"),
        ("stack: {}\n", "`language` is required"),
        ("language: python\nstack: [a, b]\n", "`stack` must be a mapping"),
        ("language: python\narchitecture_notes: 'one'\n", "must be a list of strings"),
    ],
)
def test_loud_fail(bad, msg):
    with pytest.raises(ValueError) as exc:
        parse_conventions(bad)
    assert msg in str(exc.value)


def test_empty_or_absent_still_requires_language():
    with pytest.raises(ValueError, match="`language` is required"):
        parse_conventions("")
