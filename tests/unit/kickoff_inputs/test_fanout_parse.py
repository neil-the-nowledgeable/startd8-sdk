"""FR-VIP-2 — strict round-trip parsers for the value-input fan-out (build-preferences, business-targets).

Each is the canonical schema authority for its value YAML: a well-formed sheet parses; unknown
top-level keys, a wrong domain, and per-class structure errors all loud-fail with a clear message.
"""

from __future__ import annotations

import pytest

from startd8.kickoff_inputs import (
    BuildPreferencesManifest,
    BusinessTargetsManifest,
    Target,
    parse_build_preferences,
    parse_business_targets,
)

# --------------------------------------------------------------------------- build-preferences

BP_GOOD = """
domain: build-preferences
provenance_default: config-default
budgets: {per_pipeline_run: "$5.00", llm_monthly: "$25"}
model_routing: {lead_tier: anthropic-flagship, note: "prefer re-route over invention"}
generation: {profile: full, language: python}
unattended: {question_answers: q.yaml, non_interactive: false}
"""


def test_build_preferences_parses():
    m = parse_build_preferences(BP_GOOD)
    assert isinstance(m, BuildPreferencesManifest)
    assert m.budgets == {"per_pipeline_run": "$5.00", "llm_monthly": "$25"}
    assert m.model_routing["lead_tier"] == "anthropic-flagship"
    assert m.generation["language"] == "python"
    assert m.unattended["non_interactive"] is False  # the one bool field
    assert m.unattended["question_answers"] == "q.yaml"


@pytest.mark.parametrize(
    "bad, msg",
    [
        ("domain: build-preferences\nbogus: x\n", "unknown top-level keys"),
        ("domain: views\n", "`domain` must be 'build-preferences'"),
        ("budgets: [a]\n", "`budgets` must be a mapping"),
        ("unattended: {non_interactive: 'maybe'}\n", "must be a boolean"),
        ("generation: {nested: {a: 1}}\n", "must be a scalar value"),
    ],
)
def test_build_preferences_loud_fail(bad, msg):
    with pytest.raises(ValueError) as exc:
        parse_build_preferences(bad)
    assert msg in str(exc.value)


# --------------------------------------------------------------------------- business-targets

BT_GOOD = """
domain: business-targets
provenance_default: estimate
product_funnel:
  on_time_rate: {target: "95%", why: "core outcome"}
  missed_events: {target: 0, why: "zero tolerance"}
traction:
  weekly_active: {target: 3}
monetization: {mode_now: not-applicable, conversion_rate: {target: "N/A", status: not-applicable}}
per_role_top_goals: {member: "log in 10 seconds"}
"""


def test_business_targets_parses_and_preserves_target_types():
    m = parse_business_targets(BT_GOOD)
    assert isinstance(m, BusinessTargetsManifest)
    assert m.product_funnel["on_time_rate"] == Target(target="95%", why="core outcome")
    assert m.product_funnel["missed_events"].target == 0  # bare integer kept numeric
    assert m.traction["weekly_active"] == Target(target=3, why=None)
    assert m.monetization["mode_now"] == "not-applicable"
    assert m.per_role_top_goals == {"member": "log in 10 seconds"}


@pytest.mark.parametrize(
    "bad, msg",
    [
        ("domain: business-targets\nbogus: x\n", "unknown top-level keys"),
        ("domain: views\n", "`domain` must be 'business-targets'"),
        ("product_funnel: {m: {target: {nested: 1}}}\n", "must be a string or integer"),
        ("product_funnel: {m: {target: 1, extra: y}}\n", "unknown keys"),
        ("monetization: {bogus: 1}\n", "unknown keys"),
        ("per_role_top_goals: {r: 5}\n", "must be a mapping of role -> string"),
    ],
)
def test_business_targets_loud_fail(bad, msg):
    with pytest.raises(ValueError) as exc:
        parse_business_targets(bad)
    assert msg in str(exc.value)
