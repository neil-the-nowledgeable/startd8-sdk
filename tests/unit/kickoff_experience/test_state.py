"""M1 — canonical view-model + extraction-state fold.

Exercised against the real golden extraction fixture (every §2.x surface + the contract's declared
non-conformances), so the derived attention/ambiguity labels are validated on genuine records.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.kickoff_experience import (
    Ambiguity,
    Attention,
    FieldState,
    build_kickoff_state,
    field_states,
    source_inventory,
)
from startd8.kickoff_experience.state import classify_ambiguity
from startd8.manifest_extraction import Status, extract_manifests
from startd8.manifest_extraction.models import ExtractionRecord, SourceRef

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "manifest_extraction"
    / "kickoff.md"
)


@pytest.fixture(scope="module")
def result():
    return extract_manifests({"kickoff.md": FIXTURE.read_text(encoding="utf-8")})


@pytest.fixture(scope="module")
def state():
    return build_kickoff_state({"kickoff.md": FIXTURE.read_text(encoding="utf-8")})


# --- fold + ordering ---------------------------------------------------------------------------

def test_field_states_one_per_record_in_stable_order(result) -> None:
    fields = field_states(result)
    assert len(fields) == len(result.records)
    identities = [f.identity for f in fields]
    assert identities == sorted(identities), "must be byte-stable identity order"


def test_every_status_maps_to_an_attention(state) -> None:
    for f in state.fields:
        assert f.attention in {
            Attention.OK, Attention.REVIEW, Attention.BLOCKED, Attention.BACKLOG
        }
    # The fixture contains extracted entities and author-actionable non-conformances.
    assert state.attention_counts[Attention.OK] > 0
    assert state.attention_counts[Attention.BLOCKED] > 0


def test_counts_match_raw_status(result, state) -> None:
    for status in (Status.EXTRACTED, Status.DEFAULTED, Status.NOT_EXTRACTED):
        assert state.counts[status] == len(result.by_status(status))


# --- attention projection ----------------------------------------------------------------------

def _make(status, reason=None):
    return ExtractionRecord(
        manifest="schema.prisma", value_path="/x", status=status, reason=reason
    )


def test_extracted_is_ok() -> None:
    assert FieldState.from_record(_make(Status.EXTRACTED)).attention == Attention.OK


def test_defaulted_is_review_not_ok() -> None:
    # FR-NEW-5: defaulted is provenance-critical and must be distinct from extracted.
    fs = FieldState.from_record(_make(Status.DEFAULTED, reason="kind-aware derivation"))
    assert fs.attention == Attention.REVIEW
    assert fs.ambiguity == Ambiguity.NONE


def test_generator_gap_is_backlog_not_blocked() -> None:
    fs = FieldState.from_record(
        _make(Status.NOT_EXTRACTED, reason="generator-gap: no AppManifest field")
    )
    assert fs.attention == Attention.BACKLOG
    assert fs.ambiguity == Ambiguity.NONE  # never an author-facing ambiguity


def test_plain_not_extracted_is_blocked() -> None:
    fs = FieldState.from_record(_make(Status.NOT_EXTRACTED, reason="entity 'Foo' not declared"))
    assert fs.attention == Attention.BLOCKED


# --- ambiguity classifier (single derivation point) --------------------------------------------

@pytest.mark.parametrize(
    "reason,expected",
    [
        ("entity 'Foo' not declared", Ambiguity.UNRESOLVED_REFERENCE),
        ("Root 'Bar' unresolvable against declared entities", Ambiguity.UNRESOLVED_REFERENCE),
        ("'links' without 'X to Y' form: ...", Ambiguity.OUT_OF_GRAMMAR),
        ("Kind 'frobnicate' outside the published vocabulary", Ambiguity.OUT_OF_GRAMMAR),
        ("entity block has no field table", Ambiguity.MALFORMED_BLOCK),
        ("`enabled` must be a boolean (true/false), got 'maybe'", Ambiguity.INVALID_VALUE),
        ("duplicate import row for 'Widget' (first wins)", Ambiguity.DUPLICATE),
        ("some unrecognized situation entirely", Ambiguity.OTHER),
    ],
)
def test_classify_ambiguity_patterns(reason, expected) -> None:
    rec = ExtractionRecord(
        manifest="x", value_path="/p", status=Status.NOT_EXTRACTED, reason=reason
    )
    assert classify_ambiguity(rec) == expected


def test_classify_ambiguity_none_for_non_blocked() -> None:
    assert classify_ambiguity(_make(Status.EXTRACTED)) == Ambiguity.NONE
    assert classify_ambiguity(_make(Status.DEFAULTED, reason="x")) == Ambiguity.NONE


# --- source inventory (bounded read, R3-S4/R3-F7) ----------------------------------------------

def test_source_inventory_bounded_to_inspected_docs(result) -> None:
    inv = source_inventory(result)
    assert inv.docs_inspected == ("kickoff.md",)
    assert inv.docs_with_records == ("kickoff.md",)
    assert inv.ignored_docs == ()
    assert inv.record_counts_by_doc["kickoff.md"] > 0


def test_source_inventory_flags_ignored_doc() -> None:
    docs = {
        "kickoff.md": FIXTURE.read_text(encoding="utf-8"),
        "UNRELATED.md": "# just prose\n\nNothing the grammar anchors on here.\n",
    }
    result = extract_manifests(docs)
    inv = source_inventory(result)
    assert "UNRELATED.md" in inv.docs_inspected
    # The unrelated doc produced no sourced records -> reported as ignored, not silently dropped.
    assert "UNRELATED.md" in inv.ignored_docs


# --- canonical serializer = single parity oracle (R1-S7) ---------------------------------------

def test_to_dict_is_deterministic_and_byte_stable() -> None:
    docs = {"kickoff.md": FIXTURE.read_text(encoding="utf-8")}
    a = build_kickoff_state(docs).to_dict()
    b = build_kickoff_state(docs).to_dict()
    assert a == b


def test_field_to_dict_carries_source_and_derived_labels(state) -> None:
    extracted = [f for f in state.fields if f.attention == Attention.OK and f.source_doc]
    assert extracted, "expected at least one sourced extracted field"
    d = extracted[0].to_dict()
    assert d["status"] == Status.EXTRACTED
    assert d["attention"] == Attention.OK
    assert d["ambiguity"] == Ambiguity.NONE
    assert d["source"]["doc"] == "kickoff.md"


def test_blocked_fields_are_the_worklist(state) -> None:
    blocked = state.blocked_fields()
    assert blocked
    assert all(f.attention == Attention.BLOCKED for f in blocked)
    # Each blocked field carries a derived ambiguity sub-label (never NONE).
    assert all(f.ambiguity != Ambiguity.NONE for f in blocked)


def test_source_ref_round_trips_into_field_state() -> None:
    rec = ExtractionRecord(
        manifest="views.yaml",
        value_path="/views/0/route",
        status=Status.EXTRACTED,
        value="/dashboard",
        source=SourceRef(doc="PLAN.md", heading_path=("Views", "Dashboard"), row_index=2),
    )
    fs = FieldState.from_record(rec)
    d = fs.to_dict()
    assert d["source"] == {
        "doc": "PLAN.md",
        "heading_path": ["Views", "Dashboard"],
        "row_index": 2,
    }
