"""F-1: Node model, derive_status, default_confidence, field-compat golden."""

from __future__ import annotations

from startd8.navigator.models import (
    NODE_SHARED_FIELDS,
    Node,
    NodeEvidence,
    NodeStatus,
    default_confidence,
    derive_status,
    node_field_names,
)


def test_derive_status_beta_with_code_is_built():
    assert derive_status(has_code_evidence=True, maturity="beta") == NodeStatus.BUILT


def test_derive_status_alpha_with_code_is_thin():
    assert derive_status(has_code_evidence=True, maturity="alpha") == NodeStatus.THIN


def test_derive_status_no_code_is_spec():
    assert derive_status(has_code_evidence=False, maturity="stable") == NodeStatus.SPEC


def test_default_confidence_rubric():
    code_test = (
        NodeEvidence(type="code", ref="a.py"),
        NodeEvidence(type="test", ref="t.py"),
    )
    assert default_confidence(code_test) == 0.9
    assert default_confidence((NodeEvidence(type="code", ref="a.py"),)) == 0.6
    assert default_confidence(()) == 0.4


def test_field_compat_golden_shared_names():
    """FR-1: Node fields match NODE_SHARED_FIELDS (CC / NODE-SCHEMA cite) — no contextcore import."""
    names = set(node_field_names())
    assert set(NODE_SHARED_FIELDS) <= names
    # Construct with typed lives
    n = Node(
        key="FR-1",
        does="x",
        lives=(NodeEvidence(type="code", ref="git:" + "a" * 40 + ":src/x.py"),),
        confidence=0.9,
    )
    assert n.key == "FR-1"
    assert n.lives[0].type == "code"
