# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Kickoff content contract — the experience surfaces the intro/instructional content it prescribes.

Covers the KICKOFF_CONTENT_CONTRACT feature:
  * FR-2 — bare `startd8 kickoff` ORIENTS (intro + subcommand list) and exits 0, not "Missing command".
  * FR-5 — `kickoff explain` renders the intro + the What/Why/Who inputs explainer at runtime ($0).
  * FR-6 — single source: rendered bytes derive from the packaged doc via `load_experience_doc`.
  * FR-1/FR-4/FR-9 — the guided view-model carries `intro` + `posture` (information only).
  * FR-10 — intro is `full` on a first run, `brief` once inputs exist or under `--brief` (read-only).
  * R3 — the render-only experience intro is NEVER in the write/download manifest or instantiate plan.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from startd8.cli import app
from startd8.concierge import load_experience_doc
from startd8.concierge.core import (
    KICKOFF_INPUT_DOMAINS,
    KICKOFF_INPUT_REGISTRY,
    _load_inputs_explained,
    explain_input_domain,
)
from startd8.concierge.writes import build_instantiate_plan, kickoff_template_manifest
from startd8.kickoff_experience.concierge_view import build_guided_view
from startd8.kickoff_experience.web import _render_guided

runner = CliRunner()


def _make_project(tmp_path, *, with_inputs=False):
    root = tmp_path / "proj"
    (root / "docs" / "kickoff" / "inputs").mkdir(parents=True, exist_ok=True)
    (root / "REQUIREMENTS_app.md").write_text("# Reqs\n## Entities\n", encoding="utf-8")
    if with_inputs:
        (root / "docs" / "kickoff" / "inputs" / "conventions.yaml").write_text(
            "language: python\nprovenance_default: templated\n", encoding="utf-8"
        )
    return root


# ── FR-2: bare `kickoff` orients instead of erroring ─────────────────────────────────────────────


def test_bare_kickoff_orients_and_exits_zero():
    res = runner.invoke(app, ["kickoff"])
    assert res.exit_code == 0, res.stdout
    # intro content present …
    assert "Machines draft and translate" in res.stdout
    # … and the subcommand list still shows (the help was appended).
    assert "instantiate" in res.stdout and "explain" in res.stdout


# ── FR-5 / FR-6: the explain surface, single-sourced from the packaged docs ───────────────────────


def test_explain_intro_renders_single_sourced_content():
    res = runner.invoke(app, ["kickoff", "explain", "--intro"])
    assert res.exit_code == 0, res.stdout
    assert 'What "kickoff" is' in res.stdout  # a body heading only the full doc has
    # FR-6 — the JSON payload is the packaged doc verbatim.
    j = runner.invoke(app, ["kickoff", "explain", "--intro", "--json"])
    doc = json.loads(j.stdout)
    assert doc["schema"] == "kickoff.explain.v1"
    assert doc["doc"] == "kickoff-experience-intro"
    assert doc["content"] == load_experience_doc("intro")


def test_explain_inputs_renders_whatwhywhy_without_template_banner():
    j = runner.invoke(app, ["kickoff", "explain", "--json"])
    doc = json.loads(j.stdout)
    assert doc["doc"] == "kickoff-inputs-explained"
    # clause E present …
    assert "What we ask" in doc["content"] and "Why" in doc["content"]
    # … clauses G + H reachable …
    assert "do NOT ask" in doc["content"] and "fictional" in doc["content"]
    # … and the instantiate-only TEMPLATE banner is stripped for display.
    assert "instantiate per project" not in doc["content"]


# ── FR-1/FR-4/FR-9: the guided view-model carries intro + posture ────────────────────────────────


def test_guided_view_carries_intro_and_posture(tmp_path):
    root = _make_project(tmp_path)
    view = build_guided_view(root, load_deepen=False)
    assert set(("intro", "posture")).issubset(view)
    assert view["posture"]["actionable_hint"] == (
        "startd8 kickoff instantiate --posture <prototype|production>"
    )
    modes = {o["posture"]: o["deployment_mode"] for o in view["posture"]["options"]}
    assert modes == {"prototype": "installed", "production": "deployed"}


def test_guided_json_equals_view_model(tmp_path):
    """FR-9 parity — the CLI `--json` is a pure function of build_guided_view, new keys included."""
    root = _make_project(tmp_path)
    res = runner.invoke(app, ["kickoff", "guided", str(root), "--json"])
    assert res.exit_code == 0, res.stdout
    assert json.loads(res.stdout) == json.loads(json.dumps(build_guided_view(root, load_deepen=True)))


# ── FR-10: read-only full/brief heuristic + flag ─────────────────────────────────────────────────


def test_intro_full_on_first_run(tmp_path):
    root = _make_project(tmp_path, with_inputs=False)
    assert build_guided_view(root, load_deepen=False)["intro"]["mode"] == "full"


def test_intro_brief_when_inputs_present(tmp_path):
    root = _make_project(tmp_path, with_inputs=True)
    view = build_guided_view(root, load_deepen=False)
    assert view["intro"]["mode"] == "brief"
    assert "kickoff explain --intro" in view["intro"]["text"]


def test_brief_flag_forces_short_form(tmp_path):
    root = _make_project(tmp_path, with_inputs=False)
    assert build_guided_view(root, load_deepen=False, brief=True)["intro"]["mode"] == "brief"


# ── R3: the render-only intro never joins the write/download inventory ────────────────────────────


def test_experience_intro_absent_from_manifest_and_instantiate(tmp_path):
    keys = {e.key for e in kickoff_template_manifest()}
    assert "kickoff-experience-intro" not in keys
    plan = build_instantiate_plan(_make_project(tmp_path), "prototype")
    assert "KICKOFF_EXPERIENCE_INTRO.md" not in json.dumps(plan)


# ── Follow-up 1 (NR-5): the SERVED surface renders intro + posture (parity) ───────────────────────


def test_served_guided_renders_intro_and_posture(tmp_path):
    view = build_guided_view(_make_project(tmp_path), load_deepen=False)
    html = _render_guided(view, "")
    assert "Machines draft and translate" in html            # intro (clause A)
    # posture hint (clause B) — present, HTML-escaped (`<…>` → `&lt;…&gt;`).
    assert "instantiate --posture" in html and "&lt;prototype|production&gt;" in html
    # the digest oracle now carries intro/posture so parity is enforceable across surfaces.
    from startd8.kickoff_experience.concierge_view import guided_parity_digest

    digest = guided_parity_digest(view)
    assert digest["intro_mode"] == view["intro"]["mode"]
    assert digest["posture_hint"] == view["posture"]["actionable_hint"]


# ── Follow-up 2 (OQ-7): the per-domain registry + `kickoff explain <domain>` ──────────────────────


def test_registry_slugs_match_canonical_domains():
    # single-source: the registry is keyed by exactly the canonical slug tuple (no drift).
    assert tuple(KICKOFF_INPUT_REGISTRY) == KICKOFF_INPUT_DOMAINS


def test_registry_label_and_ordinal_align_with_explainer():
    # drift guard: each registry (ordinal,label) matches the explainer's `## N. <label>` heading.
    explained = _load_inputs_explained()
    for meta in KICKOFF_INPUT_REGISTRY.values():
        assert f"## {meta.ordinal}. {meta.label}" in explained, meta.slug


def test_explain_domain_returns_sliced_prose():
    d = explain_input_domain("observability")
    assert d["label"] == "Observability"
    assert d["who"] == "operations owner + business owner"
    # the sliced section is that domain's block — What/Why present, next domain's heading absent.
    assert "What we ask" in d["prose"] and "Why" in d["prose"]
    assert "## 3. Technology conventions" not in d["prose"]


def test_explain_domain_cli_and_json():
    res = runner.invoke(app, ["kickoff", "explain", "conventions"])
    assert res.exit_code == 0, res.stdout
    assert "Technology conventions" in res.stdout and "architect" in res.stdout
    j = runner.invoke(app, ["kickoff", "explain", "conventions", "--json"])
    doc = json.loads(j.stdout)
    assert doc["doc"] == "domain:conventions"
    assert doc["slug"] == "conventions" and doc["file"].endswith("conventions.yaml")


def test_explain_unknown_domain_exits_nonzero():
    res = runner.invoke(app, ["kickoff", "explain", "not-a-domain"])
    assert res.exit_code == 2
    assert "unknown kickoff input domain" in res.stdout
