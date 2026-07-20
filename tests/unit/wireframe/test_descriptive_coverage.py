"""M-SHC-2 — the self-hosted-content coverage guard (FR-SHC-3/4).

The regression guard: every REQUIRED cell of the expected audience matrix (record-type schema × roles)
is authored. This generalizes the R1-F4 completeness bar to the whole matrix — so adding a section, or
first using a new role, without authoring its required cells FAILS CI (Kaizen: stop drift you can now see).
"""

from __future__ import annotations

from startd8.wireframe.descriptive_schema import (
    ROLES,
    SECTION_SCHEMA,
    SUMMARY_SCHEMA,
    format_report,
    matrix_coverage,
    schema_for,
)


def test_expected_matrix_is_fully_authored() -> None:
    """The regression guard — 100% coverage of every required cell (FR-SHC-4)."""
    cov = matrix_coverage()
    assert cov["gaps"] == [], f"un-authored content cells (author these): {cov['gaps']}"
    for role in ROLES:
        assert cov["by_role"][role].ratio == 1.0, f"{role} coverage {cov['by_role'][role]}"
    assert cov["overall"].ratio == 1.0
    assert cov["overall"].total > 0  # the matrix isn't empty (guards a silently-broken loader)


def test_two_record_types_are_declared() -> None:
    """FR-SHC-2 — the spike's key discovery: section and summary are distinct record types."""
    assert set(SECTION_SCHEMA) == set(SUMMARY_SCHEMA) == set(ROLES)
    # the summary record's end_user shape is the intro (headline/lead/steps/closing), not DOES/WON'T/NEED
    assert set(SUMMARY_SCHEMA["end_user"]["required"]) == {"headline", "lead", "steps", "closing"}
    assert "wont" in SECTION_SCHEMA["end_user"]["required"]        # section carries the framing
    assert "wont" not in SUMMARY_SCHEMA["end_user"]["required"]    # summary does not
    assert schema_for("summary") is SUMMARY_SCHEMA
    assert schema_for("forms") is SECTION_SCHEMA


def test_guard_fails_on_a_missing_required_cell() -> None:
    """The guard must actually catch a gap — drop a required end_user field and assert it's reported."""
    records = {
        "pages": {"what": "x", "why": "y", "do": "z",
                  "audience": {"end_user": {"title": "Screens", "what": "the screens",
                                            "wont": "w"}}},  # 'need' intentionally missing
    }
    cov = matrix_coverage(records)
    assert "pages.end_user.need" in cov["gaps"]
    assert cov["by_role"]["end_user"].ratio < 1.0


def test_fluency_is_reported_not_counted() -> None:
    """NR-2 — fluency variants surface informationally but never move the coverage denominator."""
    cov = matrix_coverage()
    assert set(cov["fluency"]) >= {"entities", "forms"}          # sparse, opt-in
    # coverage denominator excludes fluency: only required base+audience cells are counted
    assert cov["overall"].total == sum(
        len(schema_for(k)[r]["required"]) for k in _record_keys() for r in ROLES
    )


def test_resolver_fields_are_single_sourced_from_schema() -> None:
    """AR-1: describe()'s output fields ARE the declared SECTION_SCHEMA fields — no hardcoded drift.
    Adding a field to the schema without teaching the resolver (or vice versa) fails here."""
    from startd8.wireframe.describe import describe
    from startd8.wireframe.descriptive_schema import SECTION_SCHEMA, field_order
    from startd8.wireframe.plan import WireframeSection

    out = describe(WireframeSection("entities", "Entities", "planned"), None)  # plan unused by the fill
    assert set(out) - {"key"} == set(field_order(SECTION_SCHEMA))


def test_report_renders() -> None:
    report = format_report()
    assert "coverage" in report.lower()
    assert "no gaps" in report.lower()   # current state is clean


def _record_keys():
    from startd8.wireframe.describe import _records
    return list(_records().keys())
