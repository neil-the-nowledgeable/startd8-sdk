"""M2 inference unit tests — primitives, guards, and the R1-S7/R1-S8 contracts."""

from __future__ import annotations

import pytest

from startd8.manifest_extraction.prisma_emitter import _BOOKKEEPING, reserved_field_names
from startd8.tsdb_maturation import ReadResult, Series, Specimen
from startd8.tsdb_maturation.infer import (
    InferenceError,
    OBSERVED_AT_FIELD,
    PRISMA_SCALAR_TYPES,
    assert_graph_invariants,
    camel,
    derive_measure_name,
    infer_identity,
    infer_scalar_type,
    infer_schema,
    is_display_column,
    rename_if_reserved,
)


def _spec(records, metric="gov_expenditure_amount"):
    series = [Series(labels={k: v for k, v in r.items()}, value=1.0, timestamp=0.0) for r in records]
    return Specimen.from_read_result(ReadResult(metric=metric, lookback="3000d", series=tuple(series)))


# --------------------------------------------------------------------------- #
# FR-3 type inference.                                                          #
# --------------------------------------------------------------------------- #
def test_infer_scalar_type():
    assert infer_scalar_type(["2025", "2026"]) == "Int"
    assert infer_scalar_type(["-3", "4"]) == "Int"
    assert infer_scalar_type(["1000000.50", "2.0"]) == "Decimal"
    assert infer_scalar_type(["2026-01-01T00:00:00Z"]) == "DateTime"
    assert infer_scalar_type(["corrections", "health"]) == "String"
    assert infer_scalar_type([]) == "String"
    assert infer_scalar_type([None, ""]) == "String"


def test_infer_scalar_type_mixed_falls_back_to_string():
    assert infer_scalar_type(["2025", "enacted"]) == "String"


# --------------------------------------------------------------------------- #
# camel / display / rename primitives.                                          #
# --------------------------------------------------------------------------- #
def test_camel():
    assert camel("fiscal_year") == "fiscalYear"
    assert camel("data_completeness") == "dataCompleteness"
    assert camel("source") == "source"


def test_is_display_column():
    cols = ["department", "department_display", "fund_source", "fund_source_display"]
    assert is_display_column("department_display", cols)
    assert is_display_column("fund_source_display", cols)
    assert not is_display_column("department", cols)
    # A *_display without a slug sibling is NOT a display column.
    assert not is_display_column("orphan_display", ["orphan_display"])


def test_rename_if_reserved():
    reserved = frozenset(reserved_field_names())
    assert rename_if_reserved("source", reserved) == "dataSource"  # collides → renamed
    assert rename_if_reserved("department", reserved) == "department"  # no collision
    assert rename_if_reserved("created_at", reserved) == "dataCreatedAt"  # createdAt collides


def test_rename_collision_check_r1_f10():
    # A contrived reserved set where the rename target ALSO collides → fail loudly, no silent clobber.
    reserved = frozenset({"source", "dataSource"})
    with pytest.raises(InferenceError, match="also reserved"):
        rename_if_reserved("source", reserved)


# --------------------------------------------------------------------------- #
# R1-F8 measure-name collision.                                                #
# --------------------------------------------------------------------------- #
def test_derive_measure_name_basic():
    assert derive_measure_name("gov_expenditure_amount", []) == "amount"
    assert derive_measure_name("gov_expenditure_count", []) == "count"


def test_derive_measure_name_collides_with_label():
    # A label already named 'amount' forces the measure to a distinct suffixed name.
    assert derive_measure_name("gov_expenditure_amount", ["amount"]) == "amount2"
    assert derive_measure_name("gov_expenditure_amount", ["amount", "amount2"]) == "amount3"


# --------------------------------------------------------------------------- #
# FR-4 identity tie-break.                                                      #
# --------------------------------------------------------------------------- #
def test_infer_identity_single_column():
    records = [{"k": "a"}, {"k": "b"}, {"k": "c"}]
    assert infer_identity(records, ["k"]) == ["k"]


def test_infer_identity_lexicographic_tiebreak():
    # Two single columns are each unique → lexicographic picks the alphabetically-first.
    records = [{"a": "1", "b": "x"}, {"a": "2", "b": "y"}, {"a": "3", "b": "z"}]
    assert infer_identity(records, ["b", "a"]) == ["a"]


def test_infer_identity_golden_tiebreak_prefers_golden():
    # Both {a} and {b} are unique + equally minimal; golden=['b'] wins over lexicographic ['a'].
    records = [{"a": "1", "b": "x"}, {"a": "2", "b": "y"}, {"a": "3", "b": "z"}]
    assert infer_identity(records, ["a", "b"], golden=["b"]) == ["b"]


def test_infer_identity_empty_raises():
    with pytest.raises(InferenceError):
        infer_identity([], ["a"])


# --------------------------------------------------------------------------- #
# Declared --identity path + raw-input guard.                                  #
# --------------------------------------------------------------------------- #
def test_declared_identity_wins():
    spec = _spec([{"a": "1", "b": "x"}, {"a": "2", "b": "y"}])
    res = infer_schema(spec, entity_name="T", identity=["a", "b"])
    assert set(res.identity_labels) == {"a", "b"}


def test_declared_identity_unknown_column_raises():
    spec = _spec([{"a": "1"}, {"a": "2"}])
    with pytest.raises(InferenceError, match="unknown label"):
        infer_schema(spec, entity_name="T", identity=["nope"])


def test_infer_schema_rejects_aggregated_specimen():
    spec = Specimen.from_records("m", [{"a": "1", "value": 3.0}], aggregated=True)
    with pytest.raises(Exception):  # SpecimenError via assert_raw
        infer_schema(spec, entity_name="T")


def test_infer_schema_no_labels_raises():
    # A specimen with only the measure/observed_at (no label columns) cannot be inferred.
    spec = Specimen.from_records("m", [{"value": 1.0, "observed_at": "2025-01-01T00:00:00Z"}])
    with pytest.raises(InferenceError, match="no label"):
        infer_schema(spec, entity_name="T")


# --------------------------------------------------------------------------- #
# Structure of a simple inference.                                             #
# --------------------------------------------------------------------------- #
def test_infer_schema_adds_measure_and_observed_at():
    spec = _spec([{"region": "us"}, {"region": "eu"}])
    res = infer_schema(spec, entity_name="T")
    field_names = {f.name for f in res.graph.entities["T"].fields}
    assert "amount" in field_names  # measure derived from gov_expenditure_amount
    assert OBSERVED_AT_FIELD in field_names
    assert res.measure_field == "amount"
    # measure is forced Decimal (OQ-9)
    measure = next(f for f in res.graph.entities["T"].fields if f.name == "amount")
    assert measure.prisma_type == "Decimal"


def test_default_entity_name_derived_from_metric():
    spec = _spec([{"region": "us"}, {"region": "eu"}], metric="gov_expenditure_amount")
    res = infer_schema(spec)  # no entity_name
    assert res.entity == "GovExpenditureAmount"


# --------------------------------------------------------------------------- #
# R1-S7 — public reserved-names accessor is the supported contract.            #
# --------------------------------------------------------------------------- #
def test_reserved_accessor_matches_emitter_injection_set():
    # Contract test: the public accessor agrees with the emitter's actual _BOOKKEEPING set.
    assert reserved_field_names() == tuple(name for name, _ in _BOOKKEEPING)
    assert set(reserved_field_names()) == {
        "id", "ownerId", "source", "confirmed", "createdAt", "updatedAt"
    }


# --------------------------------------------------------------------------- #
# R1-S8 — direct-graph invariant checks.                                       #
# --------------------------------------------------------------------------- #
def test_assert_graph_invariants_catches_reserved_field():
    from startd8.manifest_extraction.entities import DocEntity, DocField, EntityGraph
    from startd8.manifest_extraction.prisma_emitter import render_prisma_schema

    # A field literally named 'source' (reserved) must be caught by the invariant guard.
    g = EntityGraph()
    g.entities["T"] = DocEntity(
        name="T",
        fields=(DocField("source", "String", "String", True, "", False, 0),),
        heading_path=(),
    )
    result = render_prisma_schema(g)
    with pytest.raises(InferenceError):
        assert_graph_invariants(g, "T", result)


def test_valid_prisma_scalar_types_are_emitted_only():
    assert "Decimal" in PRISMA_SCALAR_TYPES
    assert "Int" in PRISMA_SCALAR_TYPES
    assert "String" in PRISMA_SCALAR_TYPES
    assert "DateTime" in PRISMA_SCALAR_TYPES


def test_golden_specimen_passes_all_invariants():
    # The full michigan inference renders clean (no errors/unrenderable) — the R1-S8 agreement.
    from tests.unit.tsdb_maturation.test_infer_golden import michigan_specimen

    res = infer_schema(michigan_specimen(), entity_name="DepartmentBudget")
    assert res.schema.errors == ()
    assert res.schema.unrenderable == ()
