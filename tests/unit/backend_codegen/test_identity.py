"""P1a — FR-IMP-2 identity-key resolution (pure; no ai_layer dependency).

Covers the closed vocabulary, the declared > legacy > default precedence, the explicit-conflict
fail-loud, and the IdentityKey invariants. This is the shared seam both the AI persist path and the
from_json import path consume.
"""

from __future__ import annotations

import pytest

from startd8.backend_codegen.identity import (
    IdentityKey,
    NAME_KEY,
    NONE_KEY,
    parse_declared_identity,
    resolve_identity,
)


# --------------------------------------------------------------------------- #
# IdentityKey invariants
# --------------------------------------------------------------------------- #

def test_source_requires_provenance():
    with pytest.raises(ValueError):
        IdentityKey(kind="source")


def test_source_rejects_fields():
    with pytest.raises(ValueError):
        IdentityKey(kind="source", fields=("x",), provenance="p")


def test_none_carries_nothing():
    assert NONE_KEY.kind == "none"
    with pytest.raises(ValueError):
        IdentityKey(kind="none", fields=("x",))


def test_composite_requires_two_fields():
    with pytest.raises(ValueError):
        IdentityKey(kind="composite", fields=("only",))
    ok = IdentityKey(kind="composite", fields=("a", "b"))
    assert ok.fields == ("a", "b")


def test_field_requires_exactly_one():
    with pytest.raises(ValueError):
        IdentityKey(kind="field", fields=())


def test_non_source_rejects_provenance():
    with pytest.raises(ValueError):
        IdentityKey(kind="field", fields=("x",), provenance="p")


# --------------------------------------------------------------------------- #
# introspection
# --------------------------------------------------------------------------- #

def test_is_row_dedup_vs_source_scope():
    assert NAME_KEY.is_row_dedup is True
    assert NAME_KEY.is_source_scope is False
    src = IdentityKey(kind="source", provenance="srcId")
    assert src.is_source_scope is True
    assert src.is_row_dedup is False
    assert NONE_KEY.is_row_dedup is False


def test_dedup_field():
    assert IdentityKey(kind="field", fields=("kind",)).dedup_field == "kind"
    assert NAME_KEY.dedup_field == "name"
    assert IdentityKey(kind="composite", fields=("a", "b")).dedup_field is None
    assert IdentityKey(kind="source", provenance="p").dedup_field is None


def test_describe_is_stable():
    assert NAME_KEY.describe() == "name:name"
    assert NONE_KEY.describe() == "none"
    assert IdentityKey(kind="source", provenance="srcId").describe() == "source:srcId"
    assert IdentityKey(kind="composite", fields=("a", "b")).describe() == "composite:a,b"
    assert IdentityKey(kind="id", fields=("id",)).describe() == "id:id"


# --------------------------------------------------------------------------- #
# parse_declared_identity — the closed vocabulary
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "declared, id_field, expected_kind, expected_fields, expected_prov",
    [
        ("id", "id", "id", ("id",), None),
        ("id", None, "id", (), None),
        ("name", None, "name", ("name",), None),
        ("none", None, "none", (), None),
        ("source:srcId", None, "source", (), "srcId"),
        ("kind", None, "field", ("kind",), None),
        ("a,b", None, "composite", ("a", "b"), None),
        (["a", "b", "c"], None, "composite", ("a", "b", "c"), None),
        (["solo"], None, "field", ("solo",), None),
    ],
)
def test_parse_declared_vocabulary(declared, id_field, expected_kind, expected_fields, expected_prov):
    key = parse_declared_identity(declared, id_field=id_field)
    assert key is not None
    assert key.kind == expected_kind
    assert key.fields == expected_fields
    assert key.provenance == expected_prov


def test_parse_declared_none_input_returns_none():
    assert parse_declared_identity(None) is None
    assert parse_declared_identity("") is None
    assert parse_declared_identity("   ") is None
    assert parse_declared_identity([]) is None


def test_parse_declared_bare_source_is_loud():
    with pytest.raises(ValueError):
        parse_declared_identity("source")
    with pytest.raises(ValueError):
        parse_declared_identity("source:")


def test_parse_declared_is_case_insensitive_for_keywords():
    assert parse_declared_identity("ID", id_field="id").kind == "id"
    assert parse_declared_identity("None").kind == "none"
    assert parse_declared_identity("Name").kind == "name"


# --------------------------------------------------------------------------- #
# resolve_identity — precedence
# --------------------------------------------------------------------------- #

def test_default_is_name():
    # The byte-identity anchor: no keys → name (today's _PERSIST_HELPER behavior).
    assert resolve_identity() == NAME_KEY


def test_dedup_by_maps_to_field():
    key = resolve_identity(dedup_by="kind")
    assert key.kind == "field" and key.fields == ("kind",)


def test_source_binding_maps_to_source():
    key = resolve_identity(source_binding="sourceProofPointId")
    assert key.kind == "source" and key.provenance == "sourceProofPointId"


def test_declared_overrides_legacy_without_conflict():
    # declared wins even when a legacy key is also present — no error.
    key = resolve_identity(declared="none", source_binding="x")
    assert key == NONE_KEY
    key2 = resolve_identity(declared="name", dedup_by="kind")
    assert key2 == NAME_KEY


def test_both_legacy_keys_is_a_conflict():
    with pytest.raises(ValueError):
        resolve_identity(source_binding="srcId", dedup_by="kind")


def test_source_binding_none_already_collapsed_falls_to_name():
    # effective_source_binding(...) returns None for `source_binding: none`; resolver then defaults.
    assert resolve_identity(source_binding=None, dedup_by=None) == NAME_KEY


def test_whitespace_is_stripped():
    assert resolve_identity(dedup_by="  kind  ").fields == ("kind",)
    assert resolve_identity(source_binding="  srcId ").provenance == "srcId"
