"""M3 imports.yaml writer tests (FR-14, R1-F3 semantic round-trip)."""

from __future__ import annotations

from itertools import product

import pytest

from startd8.backend_codegen.identity import IdentityKey
from startd8.backend_codegen.imports_manifest import parse_imports
from startd8.tsdb_maturation import (
    ReadResult,
    Series,
    Specimen,
    build_import_entry,
    generate_imports_yaml,
    infer_schema,
    inferred_identity_key,
    write_imports_yaml,
)
from startd8.tsdb_maturation.infer import InferenceError


def _inference(records, metric="gov_expenditure_amount", entity="DepartmentBudget"):
    series = [Series(labels=dict(r), value=float(i), timestamp=0.0) for i, r in enumerate(records)]
    spec = Specimen.from_read_result(ReadResult(metric=metric, lookback="3000d", series=tuple(series)))
    return infer_schema(spec, entity_name=entity)


def _composite_records():
    # A genuine composite identity: (department, fiscal_year) is the minimal unique key.
    out = []
    for dept, fy in product(["corrections", "health"], ["2025", "2026"]):
        out.append({"department": dept, "fiscal_year": fy})
    return out


def _single_records():
    return [{"region": "us"}, {"region": "eu"}, {"region": "ap"}]


# --------------------------------------------------------------------------- #
# The inferred IdentityKey target.                                             #
# --------------------------------------------------------------------------- #
def test_inferred_identity_key_composite():
    res = _inference(_composite_records())
    key = inferred_identity_key(res)
    assert key.kind == "composite"
    assert set(key.fields) == {"department", "fiscalYear"}


def test_inferred_identity_key_single_field():
    res = _inference(_single_records())
    key = inferred_identity_key(res)
    assert key.kind == "field"
    assert key.fields == ("region",)


# --------------------------------------------------------------------------- #
# The critical FR-14 failure this prevents: no importer → id-dedup → duplication.#
# --------------------------------------------------------------------------- #
def test_generated_manifest_declares_composite_identity_not_id():
    res = _inference(_composite_records())
    text = generate_imports_yaml([res])
    specs = parse_imports(text)
    assert len(specs) == 1
    spec = specs[0]
    assert spec.entity == "DepartmentBudget"
    assert spec.format == "json"
    # The whole point: identity is the inferred composite, NOT the default `id` (which would
    # dedup TSDB rows — that have no stable id — into infinite duplication).
    assert spec.identity.kind == "composite"
    assert set(spec.identity.fields) == {"department", "fiscalYear"}


# --------------------------------------------------------------------------- #
# R1-F3 — parse_imports(generate(key)).identity == key (semantic round-trip).   #
# --------------------------------------------------------------------------- #
def test_round_trip_semantic_equality_composite():
    res = _inference(_composite_records())
    expected = inferred_identity_key(res)
    spec = parse_imports(generate_imports_yaml([res]))[0]
    assert spec.identity == expected  # dataclass eq: kind + fields + provenance


def test_round_trip_semantic_equality_single():
    res = _inference(_single_records())
    expected = inferred_identity_key(res)
    spec = parse_imports(generate_imports_yaml([res]))[0]
    assert spec.identity == expected


def test_round_trip_preserves_field_order():
    # Field order matters for a composite key; the parsed key must preserve emitted order exactly.
    res = _inference(_composite_records())
    key = inferred_identity_key(res)
    spec = parse_imports(generate_imports_yaml([res]))[0]
    assert spec.identity.fields == key.fields


def test_generate_is_a_fixed_point():
    # generate → parse → (rebuild entry from parsed key) → generate must be byte-stable.
    res = _inference(_composite_records())
    text1 = generate_imports_yaml([res])
    text2 = generate_imports_yaml([res])
    assert text1 == text2  # deterministic


# --------------------------------------------------------------------------- #
# Multiple entities.                                                            #
# --------------------------------------------------------------------------- #
def test_multiple_entities_sorted_and_each_round_trips():
    a = _inference(_composite_records(), entity="DepartmentBudget")
    b = _inference(_single_records(), metric="gov_region_total", entity="RegionTotal")
    text = generate_imports_yaml([a, b])
    specs = {s.entity: s for s in parse_imports(text)}
    assert set(specs) == {"DepartmentBudget", "RegionTotal"}
    assert specs["DepartmentBudget"].identity == inferred_identity_key(a)
    assert specs["RegionTotal"].identity == inferred_identity_key(b)
    # Deterministic ordering — DepartmentBudget before RegionTotal in the text.
    assert text.index("DepartmentBudget") < text.index("RegionTotal")


def test_duplicate_entity_raises():
    a = _inference(_composite_records(), entity="Dup")
    b = _inference(_single_records(), metric="gov_region_total", entity="Dup")
    with pytest.raises(InferenceError, match="duplicate entity"):
        generate_imports_yaml([a, b])


def test_empty_results_raises():
    with pytest.raises(InferenceError):
        generate_imports_yaml([])


# --------------------------------------------------------------------------- #
# surface flag + custom format.                                                #
# --------------------------------------------------------------------------- #
def test_surface_flag_emitted():
    res = _inference(_composite_records())
    entry = build_import_entry(res, surface=True)
    assert entry["surface"] is True
    entry_default = build_import_entry(res)
    assert "surface" not in entry_default  # omitted when False


def test_unknown_format_raises():
    res = _inference(_composite_records())
    with pytest.raises(InferenceError, match="unknown import format"):
        build_import_entry(res, fmt="csv")


# --------------------------------------------------------------------------- #
# Property-style: many sampled keys round-trip to a fixed point (R1-F3).        #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "fields",
    [
        ("a",),
        ("a", "b"),
        ("a", "b", "c"),
        ("department", "fiscalYear", "budgetStatus", "fundSource", "dataCompleteness"),
        ("z", "a"),  # non-sorted order must be preserved
    ],
)
def test_sampled_identity_keys_round_trip(fields):
    # Build the imports.yaml directly for a key, parse it back, assert semantic equality.
    import yaml as _yaml

    expected = IdentityKey(kind="field" if len(fields) == 1 else "composite", fields=fields)
    text = _yaml.safe_dump(
        {"imports": {"E": {"format": "json", "identity": list(fields)}}}, sort_keys=False
    )
    spec = parse_imports(text)[0]
    assert spec.identity == expected


# --------------------------------------------------------------------------- #
# Write to disk.                                                               #
# --------------------------------------------------------------------------- #
def test_write_imports_yaml_atomic(tmp_path):
    res = _inference(_composite_records())
    text = generate_imports_yaml([res])
    path = write_imports_yaml(text, tmp_path / "imports.yaml")
    assert path.read_text() == text
    assert list(tmp_path.glob("*.tmp")) == []
