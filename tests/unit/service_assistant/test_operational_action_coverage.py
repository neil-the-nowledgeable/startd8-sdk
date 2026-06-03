"""Coverage guard for CAUSE_TO_OPERATIONAL_ACTION (FR-10 / OQ-9).

Every RootCause member must resolve to a valid operational action so a new enum value
can never ship with a silently-missing recommendation.
"""

import pytest

from startd8.contractors.prime_postmortem import RootCause
from startd8.service_assistant.operational_actions import (
    CAUSE_TO_OPERATIONAL_ACTION,
    FALLBACK_ACTION,
    RE_RUN_STRATEGIES,
    SEVERITIES,
    resolve_operational_action,
)


def test_every_root_cause_is_mapped():
    missing = [rc for rc in RootCause if rc not in CAUSE_TO_OPERATIONAL_ACTION]
    assert not missing, f"Unmapped RootCause members: {[m.value for m in missing]}"


@pytest.mark.parametrize("root_cause", list(RootCause))
def test_actions_use_controlled_vocabulary(root_cause):
    action = CAUSE_TO_OPERATIONAL_ACTION[root_cause]
    assert action.severity in SEVERITIES
    assert action.re_run_strategy in RE_RUN_STRATEGIES
    assert action.action.strip()


def test_resolve_accepts_enum_and_string():
    by_enum = resolve_operational_action(RootCause.TIER_ESCALATION)
    by_str = resolve_operational_action("tier_escalation")
    assert by_enum == by_str
    assert by_enum.re_run_strategy == "split_element_or_increase_tier"


def test_unknown_string_falls_back():
    assert resolve_operational_action("not_a_real_cause") is FALLBACK_ACTION
    assert resolve_operational_action("unknown").re_run_strategy == "manual_review"
