"""Concierge Mode foundation — view-model (M-CM0), applier (M-CM1), serve package-less (M-CM2)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from startd8.concierge.writes import build_friction_entry, build_instantiate_plan
from startd8.kickoff_experience.concierge_apply import (
    ConciergeInputError,
    ConciergeWriteCode,
    apply_concierge_plan,
    validate_friction,
    validate_posture,
)
from startd8.kickoff_experience.concierge_view import (
    PACKAGE_COMPLETE,
    PACKAGE_MISSING,
    PACKAGE_PARTIAL,
    build_concierge_view,
)
from startd8.kickoff_experience.serve import Mode, preflight

CONVENTIONS = "domain: conventions\nprovenance_default: authored\nlanguage: python\n"


# --- M-CM2: package-less serve (R1-S1) ---------------------------------------------------------

def test_preflight_passes_for_package_less_project_in_write_mode(tmp_path: Path) -> None:
    # No docs/kickoff/inputs/ at all — must still be serveable (FR-CM-6 reachability).
    pf = preflight(tmp_path, mode=Mode.WRITE)
    assert pf.ok, [c.to_dict() for c in pf.checks if not c.ok]
    # inputs_dir + inputs_writable are advisory, not blocking.
    by_name = {c.name: c for c in pf.checks}
    assert by_name["inputs_dir"].blocking is False
    assert by_name["inputs_writable"].blocking is False


# --- M-CM1: applier typed outcomes (R1-F2/S3) --------------------------------------------------

def _proj(tmp_path: Path) -> Path:
    return tmp_path


def test_apply_instantiate_writes_then_skips_on_retry(tmp_path: Path) -> None:
    plan = build_instantiate_plan(tmp_path, "prototype")
    r1 = apply_concierge_plan(tmp_path, plan)
    assert r1.code == ConciergeWriteCode.OK
    assert r1.written and not r1.skipped
    # Re-plan against the now-populated project; every file exists → no-clobber SKIPPED no-op.
    plan2 = build_instantiate_plan(tmp_path, "prototype")
    r2 = apply_concierge_plan(tmp_path, plan2)
    assert r2.code == ConciergeWriteCode.SKIPPED
    assert not r2.written and r2.skipped


def test_apply_partial_when_some_files_preexist(tmp_path: Path) -> None:
    # Pre-create one target so a fresh instantiate writes the rest and skips this one.
    intro = tmp_path / "docs" / "kickoff" / "KICKOFF_INTRO.md"
    intro.parent.mkdir(parents=True)
    intro.write_text("pre-existing", encoding="utf-8")
    plan = build_instantiate_plan(tmp_path, "prototype")
    r = apply_concierge_plan(tmp_path, plan)
    assert r.code == ConciergeWriteCode.PARTIAL
    assert r.written and r.skipped
    assert intro.read_text() == "pre-existing"  # no-clobber preserved the existing file


def test_apply_friction_append(tmp_path: Path) -> None:
    plan = build_friction_entry(
        tmp_path, friction="grammar rejected my PRD", what_happened="reformat needed",
        implication="need F-4 path", timestamp="2026-06-26T00:00:00+00:00",
    )
    r = apply_concierge_plan(tmp_path, plan)
    assert r.code == ConciergeWriteCode.OK
    log = (tmp_path / "concierge-friction.jsonl").read_text()
    assert "grammar rejected my PRD" in log
    assert '"ts": "2026-06-26T00:00:00+00:00"' in log  # surface-stamped timestamp survived


def test_apply_result_envelope_serializes(tmp_path: Path) -> None:
    plan = build_instantiate_plan(tmp_path, "prototype")
    d = apply_concierge_plan(tmp_path, plan).to_dict()
    assert d["code"] == "ok"
    assert d["written_count"] > 0 and d["skipped_count"] == 0


# --- M-CM1: validation (R2-F5) -----------------------------------------------------------------

def test_validate_friction_rejects_blank_and_oversized() -> None:
    with pytest.raises(ConciergeInputError) as ei:
        validate_friction("", "x", "y")
    assert ei.value.code == ConciergeWriteCode.MISSING_REQUIRED_FIELD
    with pytest.raises(ConciergeInputError) as ei2:
        validate_friction("a" * 5000, "x", "y")
    assert ei2.value.code == ConciergeWriteCode.INPUT_TOO_LARGE


def test_validate_posture() -> None:
    validate_posture("prototype")
    with pytest.raises(ConciergeInputError) as ei:
        validate_posture("bogus")
    assert ei.value.code == ConciergeWriteCode.INVALID_POSTURE


# --- M-CM0: view-model + package_state (R5-F1) -------------------------------------------------

def test_view_package_state_missing(tmp_path: Path) -> None:
    view = build_concierge_view(str(tmp_path))
    assert view["schema_version"] == 1
    assert view["instantiate_offer"]["package_state"] == PACKAGE_MISSING
    assert view["instantiate_offer"]["needed"] is True
    assert view["next_action"]["kind"] == "instantiate"
    # The aggregator carries write-affordance metadata (NOT the MCP surface).
    assert "friction_form" in view and "instantiate_offer" in view


def test_view_package_state_partial(tmp_path: Path) -> None:
    (tmp_path / "docs" / "kickoff" / "KICKOFF_INTRO.md").parent.mkdir(parents=True)
    (tmp_path / "docs" / "kickoff" / "KICKOFF_INTRO.md").write_text("x", encoding="utf-8")
    view = build_concierge_view(str(tmp_path))
    assert view["instantiate_offer"]["package_state"] == PACKAGE_PARTIAL


def test_view_package_state_complete_after_instantiate(tmp_path: Path) -> None:
    apply_concierge_plan(tmp_path, build_instantiate_plan(tmp_path, "prototype"))
    view = build_concierge_view(str(tmp_path))
    assert view["instantiate_offer"]["package_state"] == PACKAGE_COMPLETE
    assert view["instantiate_offer"]["needed"] is False


def test_view_survey_is_memoized(tmp_path: Path) -> None:
    # Two calls with a frozen clock → build_survey runs once (cache hit).
    from startd8.kickoff_experience import concierge_view as cv

    calls = {"n": 0}
    import startd8.concierge as concierge_pkg
    real = concierge_pkg.build_survey

    def counting(root):
        calls["n"] += 1
        return real(root)

    concierge_pkg.build_survey = counting
    cv._survey_cache.clear()
    try:
        clock = lambda: 1000.0  # noqa: E731 — frozen
        cv.cached_survey(str(tmp_path), clock=clock)
        cv.cached_survey(str(tmp_path), clock=clock)
        assert calls["n"] == 1
    finally:
        concierge_pkg.build_survey = real
        cv._survey_cache.clear()
