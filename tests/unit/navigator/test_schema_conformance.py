"""REQ-16 FR-2 + REQ-17 FR-3 — the schema self-conformance gate (the schema-as-Node self-check).

``models.Node``'s runtime field set must equal the canonical documented field manifest
(``NODE_FIELD_MANIFEST``) that lives INSIDE the SDK. Adding a Node field in code without documenting it
here fails the gate — the drift class that left ``dev-os/NODE-SCHEMA.md`` §1 stale (it omitted
category/orientation/status_facets/child_keys/attributes the code already carried). REQ-17's three
promoted fields (``verify``/``approve``/``was``) register in the same manifest so the parity gate covers
them too (REQ-17 FR-3).
"""

from __future__ import annotations

from startd8.navigator.models import (
    NODE_FIELD_MANIFEST,
    field_parity_drift,
    node_field_names,
)


def _manifest_names():
    return tuple(name for name, _ in NODE_FIELD_MANIFEST)


def test_node_field_set_equals_documented_manifest():
    """FR-2: the Node code field set equals the canonical manifest — parity holds, zero drift."""
    assert node_field_names() == _manifest_names()
    assert field_parity_drift(node_field_names(), _manifest_names()) == []


def test_manifest_has_no_duplicate_or_undocumented_entries():
    """Each field is documented exactly once with a non-empty meaning (the manifest is the doc)."""
    names = _manifest_names()
    assert len(names) == len(set(names)), "duplicate field in NODE_FIELD_MANIFEST"
    assert all(doc.strip() for _, doc in NODE_FIELD_MANIFEST), "a manifest field has an empty meaning"


def test_synthetic_field_in_code_fails_parity_with_named_drift():
    """FR-2: a Node field present in code but absent from the manifest fails with a NAMED drift message."""
    drift = field_parity_drift(node_field_names() + ("synthetic_field",), _manifest_names())
    assert drift, "adding an un-manifested field must produce drift"
    assert any("synthetic_field" in m and "absent from NODE_FIELD_MANIFEST" in m for m in drift)


def test_reliability_fields_are_registered_in_the_manifest():
    """REQ-17 FR-3: verify/approve/was register in REQ-16's manifest so the gate covers them."""
    names = set(_manifest_names())
    assert {"verify", "approve", "was"} <= names
    # And the derivation edge (REQ-16 FR-1) is registered too — the co-churned 0.4.0 delta.
    assert "derivation" in names


def test_removing_a_promoted_field_from_manifest_fails_parity():
    """REQ-17 FR-3: dropping a promoted field from the manifest while it exists in code = named drift."""
    for dropped in ("verify", "approve", "was", "derivation"):
        reduced = tuple(n for n in _manifest_names() if n != dropped)
        drift = field_parity_drift(node_field_names(), reduced)
        assert any(dropped in m and "absent from Node code" not in m for m in drift), (
            f"dropping {dropped!r} from the manifest should flag it present-in-code / un-manifested"
        )
