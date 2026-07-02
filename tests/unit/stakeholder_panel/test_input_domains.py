# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""M0 tests for the Teian supported-domain registry, field enumeration, and bounded routing."""

from __future__ import annotations

import pytest

from startd8.stakeholder_panel.input_domains import (
    SUPPORTED_DOMAINS,
    enumerate_fields,
    get_domain,
    is_placeholder,
    resolve_owner,
    unfilled_fields,
)
from startd8.stakeholder_panel.models import PersonaBrief

# A realistic partially-instantiated business-targets YAML: metric NAMES chosen by the author,
# TARGET values still placeholders (the drafting candidates), one row already filled.
BT_YAML = """
domain: business-targets
provenance_default: estimate

product_funnel:
  signup_rate:
    target: "<NN%>"
    why: <core funnel KPI>
  activation_rate:
    target: "60%"          # already filled by a human
    why: users who reach value

traction:
  monthly_actives:
    target: <N>
    why: MAU at current stage

monetization:
  mode_now: <free-during-demo | live>
  conversion:
    target: "<N%>"
    status: dormant

per_role_top_goals:
  founder: "<one-line goal>"
"""

CONVENTIONS_YAML = """
domain: conventions
provenance_default: estimate
language: python
stack:
  web: "<framework>"
  orm: sqlmodel
data_model:
  money: "<minor-units | decimal>"
"""

BUILD_PREFS_YAML = """
domain: build-preferences
provenance_default: estimate
budgets:
  llm_monthly_ceiling_usd: "<N>"
model_routing:
  default_tier: cheap
"""


def test_supported_domains_excludes_observability():
    assert set(SUPPORTED_DOMAINS) == {
        "business-targets",
        "conventions",
        "build-preferences",
    }
    assert get_domain("observability") is None
    assert get_domain("business-targets") is not None


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, True),
        ("", True),
        ("   ", True),
        ("<NN%>", True),
        ("<= $<N>", True),
        ("60%", False),
        ("python", False),
        (5, False),
        (True, False),
    ],
)
def test_is_placeholder(value, expected):
    assert is_placeholder(value) is expected


def test_business_targets_metric_rows_are_composite_one_slot_each():
    spec = get_domain("business-targets")
    fields = enumerate_fields(spec, BT_YAML)
    by_path = {f.value_path: f for f in fields}

    # One slot per metric row (not two per {target, why}) — R4-F1.
    assert "product_funnel.signup_rate" in by_path
    signup = by_path["product_funnel.signup_rate"]
    assert signup.is_composite
    assert signup.composite_keys == ("target", "why")
    assert signup.scalar_paths() == [
        "product_funnel.signup_rate.target",
        "product_funnel.signup_rate.why",
    ]

    # meta keys are never fields
    assert "domain" not in by_path
    assert "provenance_default" not in by_path


def test_business_targets_unfilled_detection():
    spec = get_domain("business-targets")
    unfilled = {f.value_path for f in unfilled_fields(spec, BT_YAML)}
    # placeholder targets are unfilled candidates ...
    assert "product_funnel.signup_rate" in unfilled
    assert "traction.monthly_actives" in unfilled
    assert "monetization.mode_now" in unfilled
    assert "monetization.conversion" in unfilled
    assert "per_role_top_goals.founder" in unfilled
    # ... the human-filled row is NOT a candidate (never overwrite a real value)
    assert "product_funnel.activation_rate" not in unfilled


def test_conventions_and_build_prefs_scalar_enumeration():
    conv = get_domain("conventions")
    conv_unfilled = {f.value_path for f in unfilled_fields(conv, CONVENTIONS_YAML)}
    assert "stack.web" in conv_unfilled  # placeholder
    assert "data_model.money" in conv_unfilled
    assert "language" not in conv_unfilled  # 'python' is filled
    assert "stack.orm" not in conv_unfilled  # 'sqlmodel' is filled

    bp = get_domain("build-preferences")
    bp_unfilled = {f.value_path for f in unfilled_fields(bp, BUILD_PREFS_YAML)}
    assert "budgets.llm_monthly_ceiling_usd" in bp_unfilled
    assert "model_routing.default_tier" not in bp_unfilled


def test_enumerate_handles_malformed_or_empty():
    spec = get_domain("business-targets")
    assert enumerate_fields(spec, "") == []
    assert enumerate_fields(spec, "just a string") == []
    assert enumerate_fields(spec, ": : bad yaml :") == []


# --- bounded routing (FR-KIR-3 / R3-F1) ------------------------------------------------


def _brief(role_id, answers_for=None, goals=("g",)):
    return PersonaBrief(
        role_id=role_id,
        display_name=role_id.title(),
        goals=list(goals),
        answers_for=list(answers_for or []),
    )


def test_resolve_owner_default_role_present():
    briefs = [_brief("product-owner"), _brief("architect"), _brief("pm")]
    assert resolve_owner("business-targets", briefs) == "product-owner"
    assert resolve_owner("conventions", briefs) == "architect"
    assert resolve_owner("build-preferences", briefs) == "pm"


def test_resolve_owner_high_confidence_answers_for_fallback():
    # No 'product-owner', but a persona explicitly answers_for business-targets.
    briefs = [_brief("founder", answers_for=["business-targets", "pricing"])]
    assert resolve_owner("business-targets", briefs) == "founder"
    # head-token form also counts as high-confidence
    briefs2 = [_brief("ceo", answers_for=["business"])]
    assert resolve_owner("business-targets", briefs2) == "ceo"


def test_resolve_owner_skips_on_no_confident_owner():
    # A persona whose answers_for matches unrelated FIELD paths (not the domain) does NOT own it.
    briefs = [_brief("backend-eng", answers_for=["Order.*", "signup_rate"])]
    assert resolve_owner("business-targets", briefs) is None
    # empty roster → skip
    assert resolve_owner("conventions", []) is None
    # unknown domain → skip
    assert resolve_owner("observability", briefs) is None
