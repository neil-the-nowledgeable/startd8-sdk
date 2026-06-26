"""FR-FH-9 — the wireframe surfaces form-help coverage (the form WORDS layer).

The Forms section indicates which fields carry authored help (`help: N/M[, intro]`), and form help
joins the unified `content_completeness` rollup beside page bodies / view copy / AI prompts. Mirrors
the `view_prose` precedent: a Words layer that only annotates coverage — absent ⇒ today's bare forms
(byte-stable), present ⇒ additive coverage; a dangling target is caught (INVALID) the same way a
malformed manifest is, but never gates the build.

Golden fixture: Profile (writable: name, bio), Metric (label, kind, profileId, value), Note (title,
body) → 8 writable form fields; no `form_prose.yaml` → form help 0/8.
"""

from __future__ import annotations

import json
from pathlib import Path

from startd8.wireframe import CoverageStat, build_wireframe_plan, load_assembly_inputs
from startd8.wireframe.plan import Status
from startd8.wireframe.render import canonical_json


def _plan(root: Path, **kw):
    return build_wireframe_plan(load_assembly_inputs(project_root=root), **kw)


def _forms(plan):
    return next(s for s in plan.sections if s.key == "forms")


def _write_form_prose(root: Path, body: str) -> None:
    (root / "prisma" / "form_prose.yaml").write_text(body, encoding="utf-8")


# --------------------------------------------------------------------------- absent ⇒ no markers


def test_absent_form_prose_shows_no_help_markers(golden_root: Path) -> None:
    forms = _forms(_plan(golden_root))
    assert forms.status == Status.PLANNED
    assert all("help:" not in it.detail for it in forms.items)


def test_absent_form_help_rollup_is_zero_over_surface(golden_root: Path) -> None:
    assert _plan(golden_root).content_coverage.form_help == CoverageStat(0, 8)


# --------------------------------------------------------------------------- present ⇒ coverage


def test_forms_section_surfaces_help_and_intro(golden_copy: Path) -> None:
    _write_form_prose(
        golden_copy,
        "forms:\n  Profile:\n    intro: Tell us about yourself.\n"
        "    fields:\n      name: {help: 'Your full name.', placeholder: 'Ada'}\n",
    )
    profile = next(i for i in _forms(_plan(golden_copy)).items if i.label.startswith("Profile"))
    assert "help: 1/2, intro" in profile.detail
    # placeholder-only / unhelped fields do not inflate the count
    assert "help: 1/2" in profile.detail


def test_form_help_moves_the_rollup(golden_copy: Path) -> None:
    assert _plan(golden_copy).content_coverage.form_help == CoverageStat(0, 8)
    _write_form_prose(
        golden_copy,
        "forms:\n  Profile:\n    fields:\n      name: {help: 'Your full name.'}\n"
        "      bio: {help: 'A short blurb.'}\n",
    )
    cov = _plan(golden_copy).content_coverage
    assert cov.form_help == CoverageStat(2, 8)
    assert cov.overall == CoverageStat(4, 12)   # +2 authored surfaces roll up (2→4)


def test_json_carries_form_help_block(golden_copy: Path) -> None:
    _write_form_prose(
        golden_copy,
        "forms:\n  Note:\n    fields:\n      title: {help: 'A short title.'}\n",
    )
    body = json.loads(canonical_json(_plan(golden_copy)))
    assert body["content_completeness"]["form_help"] == {"authored": 1, "total": 8, "ratio": 0.125}


# --------------------------------------------------------------------------- dangling target ⇒ INVALID


def test_unknown_field_makes_form_prose_invalid(golden_copy: Path) -> None:
    # A help target that names no writable field is the dangling-target guard (consumer parity with
    # `generate backend`): the form_prose state is INVALID, so help is not surfaced (parsed is None).
    _write_form_prose(
        golden_copy,
        "forms:\n  Profile:\n    fields:\n      ghostField: {help: 'nope'}\n",
    )
    plan = _plan(golden_copy)
    # The Forms section itself still renders (advisory layer); coverage falls back to un-authored.
    assert plan.content_coverage.form_help == CoverageStat(0, 8)
    assert all("help:" not in it.detail for it in _forms(plan).items)


def test_unknown_entity_makes_form_prose_invalid(golden_copy: Path) -> None:
    _write_form_prose(golden_copy, "forms:\n  Ghost:\n    intro: x\n")
    # no crash; the words layer simply contributes nothing (INVALID → parsed None → 0 authored)
    assert _plan(golden_copy).content_coverage.form_help == CoverageStat(0, 8)
