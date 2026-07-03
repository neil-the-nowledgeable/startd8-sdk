# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Kickoff orchestrator tests (FR-KO-1) — the read-only guided plan over the advisor playbook."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from startd8.cli_kickoff import kickoff_app
from startd8.kickoff_experience.orchestrator import build_kickoff_plan, cost_tag

runner = CliRunner()


def _greenfield(tmp_path):
    proj = tmp_path.resolve()
    (proj / "prisma").mkdir(parents=True, exist_ok=True)
    (proj / "prisma" / "schema.prisma").write_text(
        "model Order { id String @id\n name String\n}", encoding="utf-8"
    )
    return proj


def test_cost_tag_mapping():
    assert cost_tag("startd8 generate backend") == "$0"
    assert cost_tag("startd8 wireframe") == "$0"
    assert (
        cost_tag("startd8 screens suggest") == "$0+paid"
    )  # $0 baseline, optional --roles
    assert cost_tag("startd8 kickoff red-carpet --agent") == "paid"
    assert cost_tag(None) == "gate"  # a command-less step is a human gate
    assert cost_tag("startd8 something-unknown") == "step"


def test_build_plan_greenfield_has_ranked_cost_labeled_steps(tmp_path):
    plan = build_kickoff_plan(_greenfield(tmp_path))
    assert plan.cascade_offerable is False
    assert plan.steps, "a greenfield project should have next steps"
    # ranks are 1..N and every step carries a known cost tag
    assert [s.rank for s in plan.steps] == list(range(1, len(plan.steps) + 1))
    assert all(s.cost in {"$0", "paid", "$0+paid", "gate", "step"} for s in plan.steps)
    # FR-MS-8: the screens gap is surfaced as a $0+paid step pointing at the suggester
    assert any(s.command == "startd8 screens suggest" for s in plan.steps)


def test_plan_render_and_json_are_consistent(tmp_path):
    plan = build_kickoff_plan(_greenfield(tmp_path))
    text = plan.render()
    assert "guided greenfield path" in text
    assert "read-only map" in text  # it never spends/writes
    d = plan.to_dict()
    assert d["steps"] and d["steps"][0]["rank"] == 1
    assert plan.next_step is plan.steps[0]


def test_build_plan_missing_project_degrades_gracefully(tmp_path):
    # no schema at all → the advisor degrades; the plan is still a valid structure (never raises).
    plan = build_kickoff_plan(tmp_path.resolve())
    assert isinstance(plan.to_dict()["steps"], list)


# ── CLI: startd8 kickoff plan / next ─────────────────────────────────────────


def test_cli_kickoff_plan(tmp_path):
    proj = _greenfield(tmp_path)
    r = runner.invoke(kickoff_app, ["plan", "--project", str(proj)])
    assert r.exit_code == 0
    assert "guided greenfield path" in r.stdout
    assert "screens suggest" in r.stdout  # the FR-MS-8 step is in the plan


def test_cli_kickoff_plan_json(tmp_path):
    proj = _greenfield(tmp_path)
    r = runner.invoke(kickoff_app, ["plan", "--project", str(proj), "--json"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert "steps" in data and data["steps"][0]["cost"] in {
        "$0",
        "paid",
        "$0+paid",
        "gate",
        "step",
    }


def test_cli_kickoff_next(tmp_path):
    proj = _greenfield(tmp_path)
    r = runner.invoke(kickoff_app, ["next", "--project", str(proj)])
    assert r.exit_code == 0
    assert "next:" in r.stdout
