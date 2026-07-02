# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""M0 kickoff wiring: instantiate projects the roster template, the download manifest exposes it,
and assess reports the domain with the authored-vs-consumable distinction (FR-1/FR-3/FR-4, R2-S5).
"""

from __future__ import annotations

import yaml

import startd8.stakeholder_panel as sp
from startd8.concierge.core import _assess_kickoff_inputs
from startd8.concierge.writes import (
    build_instantiate_plan,
    kickoff_template_manifest,
)

_DEST = "docs/kickoff/inputs/stakeholders.yaml"


def _instantiate_to_disk(tmp_path):
    plan = build_instantiate_plan(tmp_path, "prototype")
    for w in plan["writes"]:
        target = tmp_path / w["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(w["content"], encoding="utf-8")
    return plan


# ── FR-3: projection ────────────────────────────────────────────────────────────


def test_instantiate_projects_stakeholders_template(tmp_path):
    plan = build_instantiate_plan(tmp_path, "prototype")
    dests = {w["path"] for w in plan["writes"]}
    assert _DEST in dests


def test_projected_template_is_a_valid_parsable_roster(tmp_path):
    # The shipped template must parse as YAML and declare the stakeholders domain (its placeholder
    # personas are guidance, so it is not expected to pass content validation).
    plan = build_instantiate_plan(tmp_path, "prototype")
    content = next(w["content"] for w in plan["writes"] if w["path"] == _DEST)
    data = yaml.safe_load(content)
    assert data["domain"] == "stakeholders"
    assert isinstance(data["personas"], list) and len(data["personas"]) >= 1


def test_download_manifest_exposes_stakeholders_key():
    keys = {e.key for e in kickoff_template_manifest()}
    assert "stakeholders" in keys  # auto-derived from the dest basename, no drift


# ── FR-4 + R2-S5: assess ─────────────────────────────────────────────────────────


def test_assess_absent_when_not_instantiated(tmp_path):
    domains = _assess_kickoff_inputs(tmp_path)["domains"]
    assert domains["stakeholders"]["status"] == "absent"


def test_assess_reports_authored_and_consumable_for_valid_roster(tmp_path):
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "stakeholders.yaml").write_text(
        "domain: stakeholders\n"
        "personas:\n"
        "  - role_id: product-owner\n"
        "    display_name: Product Owner\n"
        "    goals: ['ship']\n",
        encoding="utf-8",
    )
    got = _assess_kickoff_inputs(tmp_path)["domains"]["stakeholders"]
    assert got["status"] == "present"
    assert got["authored"] is True
    # M1 ships the live panel, so a valid roster is now consumable (R2-S5).
    assert got["consumable"] is sp.PANEL_CONSUMABLE is True
    # The "later increment" note only appears while authored-but-not-consumable.
    assert "note" not in got


def test_assess_invalid_roster_surfaces_issues(tmp_path):
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "stakeholders.yaml").write_text(
        "domain: stakeholders\n", encoding="utf-8"
    )
    got = _assess_kickoff_inputs(tmp_path)["domains"]["stakeholders"]
    assert got["status"] == "invalid"
    assert got["authored"] is False
