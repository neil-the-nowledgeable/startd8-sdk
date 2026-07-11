# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Shared paid-pass runner tests (FR-KO-4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.persona_drafting import PaidPassError, run_paid_pass

_ROSTER_REL = Path("docs") / "kickoff" / "inputs" / "stakeholders.yaml"


async def _noop(panel):
    # a $0 pass: touch the live panel's surface but never .ask (no LLM), return a sentinel
    assert panel.briefs is not None
    return "ok"


def test_run_paid_pass_no_roster(tmp_path):
    with pytest.raises(PaidPassError) as exc:
        run_paid_pass(tmp_path, roster_rel=_ROSTER_REL, run=_noop)
    assert exc.value.kind == "no_roster"


def test_run_paid_pass_invalid_roster(tmp_path):
    p = tmp_path / _ROSTER_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "not: a valid roster\n", encoding="utf-8"
    )  # missing domain: stakeholders / personas
    with pytest.raises(PaidPassError) as exc:
        run_paid_pass(tmp_path, roster_rel=_ROSTER_REL, run=_noop)
    assert exc.value.kind in {"invalid_roster"}


def test_run_paid_pass_success_builds_panel_and_closes(tmp_path):
    # A valid default roster → a live panel is built, the $0 run() executes, the panel is closed.
    from startd8.requirements_panel import install_default_roster

    install_default_roster(tmp_path)  # writes the default stakeholders.yaml
    # mock model → the panel builds without a real API key (the $0 run never calls .ask anyway)
    result = run_paid_pass(
        tmp_path, roster_rel=_ROSTER_REL, run=_noop, model="mock:mock-model"
    )
    assert result == "ok"


def test_run_paid_pass_wraps_run_failure(tmp_path):
    from startd8.requirements_panel import install_default_roster

    install_default_roster(tmp_path)

    async def _boom(panel):
        raise RuntimeError("provider down")

    with pytest.raises(PaidPassError) as exc:
        run_paid_pass(
            tmp_path, roster_rel=_ROSTER_REL, run=_boom, model="mock:mock-model"
        )
    assert exc.value.kind == "failed" and "provider down" in str(exc.value)
