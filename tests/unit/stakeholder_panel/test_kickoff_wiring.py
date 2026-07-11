# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""M0 kickoff wiring: instantiate projects the roster template and the download manifest exposes it
(FR-1/FR-3). The authoring surface (roster template) is retained for reuse by the later guided
experience; the panel-in-assess edge (the unconditional ``stakeholders`` assess domain) was cut in
M2 (FR-13/FR-15) — kernel ``assess`` no longer reports a ``stakeholders`` domain, so those assertions
moved out (see ``tests/unit/concierge/test_concierge_core.py`` for the byte-identity guarantee).
"""

from __future__ import annotations

import yaml

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
