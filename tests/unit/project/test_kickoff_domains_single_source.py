# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Regression guard: the four kickoff/value-input domains have exactly ONE source of truth.

`concierge.core.KICKOFF_INPUT_DOMAINS` is the canonical tuple. `project.init` (shape triage) and
`kickoff_experience.red_carpet_advisor` (value-input diagnosis) must *import* it, not re-declare it —
so the "which inputs count" set cannot drift across the three consumers. Asserting object identity
(`is`) means any re-introduced literal copy fails this test immediately.

Note: `stakeholder_panel.input_domains` is deliberately a DIFFERENT set (3 domains, no `observability`)
and must NOT be unified with this one — this test guards against accidental *coupling* as well as
accidental *duplication*.
"""

from startd8.concierge.core import KICKOFF_INPUT_DOMAINS
from startd8.kickoff_experience import red_carpet_advisor
from startd8.project import init as project_init


def test_single_canonical_tuple():
    assert KICKOFF_INPUT_DOMAINS == (
        "business-targets",
        "observability",
        "conventions",
        "build-preferences",
    )


def test_project_init_imports_the_canonical_tuple():
    assert project_init.KICKOFF_INPUT_DOMAINS is KICKOFF_INPUT_DOMAINS


def test_red_carpet_advisor_imports_the_canonical_tuple():
    assert red_carpet_advisor._VALUE_DOMAINS is KICKOFF_INPUT_DOMAINS


def test_stakeholder_domains_are_intentionally_distinct():
    # Different concept: stakeholder-authored inputs exclude `observability`. Guard against a future
    # well-meaning "dedup" that would wrongly couple them.
    from startd8.stakeholder_panel.input_domains import DOMAINS

    assert "observability" not in DOMAINS
    assert "observability" in KICKOFF_INPUT_DOMAINS
