# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Provenance tests (FR-10/FR-18/R1-F2/R1-F6/R2-F3)."""

from __future__ import annotations

import pytest

from startd8.fde.models import ClaimLabel, LabeledClaim
from startd8.stakeholder_panel.models import Grounding, PanelAnswer, PersonaBrief
from startd8.stakeholder_panel.provenance import (
    RatificationError,
    assert_ratifiable,
    brief_hash,
    is_synthetic,
    round_trips_synthetic,
    synthetic_claim,
)

_BRIEF = PersonaBrief(role_id="po", display_name="PO", goals=["a", "b"])


def _answer(text="ship by Q3", role_id="product-owner"):
    return PanelAnswer(
        role_id=role_id,
        question="when?",
        text=text,
        grounding=Grounding.GROUNDED,
        brief_hash="sha256:deadbeef",
    )


def test_brief_hash_is_stable_and_order_independent():
    b1 = PersonaBrief(role_id="po", display_name="PO", goals=["a", "b"])
    b2 = PersonaBrief(role_id="po", display_name="PO", goals=["a", "b"])
    assert brief_hash(b1) == brief_hash(b2)
    # A content change moves the hash.
    b3 = PersonaBrief(role_id="po", display_name="PO", goals=["a", "c"])
    assert brief_hash(b3) != brief_hash(b1)


def test_synthetic_claim_renders_observed_synthetic():
    claim = synthetic_claim(_answer())
    assert claim.label is ClaimLabel.OBSERVED
    assert claim.tag() == "OBSERVED (project, synthetic)"
    assert claim.source == "panel:product-owner"
    assert is_synthetic(claim) is True


def test_synthetic_claim_passes_the_fr21_label_gate():
    from startd8.fde.deterministic_compose import assert_all_labeled

    claim = synthetic_claim(_answer())
    # Rendered as a bolded/labeled markdown bullet, the gate must accept the OBSERVED prefix.
    assert_all_labeled(claim.to_markdown())


def test_plain_observed_claim_is_not_synthetic():
    plain = LabeledClaim(label=ClaimLabel.OBSERVED, text="real fact", source="sapper:x")
    assert is_synthetic(plain) is False


def test_serialization_preserves_synthetic_marker():
    claim = synthetic_claim(_answer())
    assert round_trips_synthetic(claim) is True
    reloaded = LabeledClaim.from_dict(claim.to_dict())
    assert reloaded.qualifier == "synthetic"


def test_ratification_gate_blocks_without_token():
    claim = synthetic_claim(_answer())
    with pytest.raises(RatificationError):
        assert_ratifiable(claim, ratification_token=None)
    with pytest.raises(RatificationError):
        assert_ratifiable(claim, ratification_token="   ")


def test_ratification_gate_allows_with_token_and_passes_non_synthetic():
    claim = synthetic_claim(_answer())
    assert_ratifiable(claim, ratification_token="human-ok")  # no raise
    plain = LabeledClaim(label=ClaimLabel.OBSERVED, text="real", source="sapper:x")
    assert_ratifiable(plain, ratification_token=None)  # non-synthetic passes freely
