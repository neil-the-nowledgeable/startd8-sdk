"""Tests for the Workbook project-start generation (WORKBOOK_PROJECT_START_REQUIREMENTS v0.4).

Covers the shared helper (FR-1/FR-10), toolchain degradation (FR-6 absent+broken), non-fatal isolation
(FR-7), the 1:1 slug + reserved `index` (FR-5), the portfolio index + NR-6 guard (FR-11), and the
instantiate wiring (FR-2 default-ON, `--no-portal`, preview side-effect-free, fault-injection isolation).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from startd8.cli_concierge import kickoff_kernel_app
from startd8.kickoff_experience import portal_build
from startd8.kickoff_experience.portal_build import (
    build_and_maybe_provision,
    build_index,
)
from startd8.kickoff_experience.portal_spec import (
    INDEX_UID,
    WORKBOOK_TAG,
    WorkbookSlugError,
    build_workbook_index_spec,
    slugify_project,
    workbook_uid,
)

pytestmark = pytest.mark.unit
runner = CliRunner()


def _proj() -> Path:
    # resolve_confined_root rejects a symlinked root (macOS /var → /private/var).
    return Path(os.path.realpath(tempfile.mkdtemp()))


def _instantiate(proj: Path, *args: str):
    return runner.invoke(
        kickoff_kernel_app, ["instantiate", str(proj), "--apply", *args]
    )


# --------------------------------------------------------------------------- FR-5 slug / UID


def test_slug_is_deterministic_and_1to1():
    assert slugify_project("My App") == "my-app"
    assert slugify_project("my_app") == "my-app"
    assert workbook_uid("My App") == "cc-portal-kickoff-my-app"


def test_reserved_index_slug_is_rejected():
    with pytest.raises(WorkbookSlugError):
        workbook_uid("Index")  # would collide with the portfolio-index UID
    with pytest.raises(WorkbookSlugError):
        workbook_uid("!!!")  # slugifies to empty


def test_helper_skips_on_reserved_slug():
    proj = _proj()
    (proj / "docs" / "kickoff").mkdir(parents=True)
    res = build_and_maybe_provision(proj, "index")
    assert res.skipped_reason and "reserved" in res.skipped_reason
    assert res.json_path is None


# --------------------------------------------------------------------------- FR-6 toolchain degrade


def test_absent_toolchain_degrades_not_raises(monkeypatch):
    proj = _proj()
    (proj / "docs" / "kickoff").mkdir(parents=True)

    def _raise():
        from startd8.dashboard_creator.discovery import ConfigurationError

        raise ConfigurationError("no toolchain")

    monkeypatch.setattr("startd8.dashboard_creator.discovery.detect_toolchain", _raise)
    res = build_and_maybe_provision(proj, "demo")
    assert res.skipped_reason and "jsonnet toolchain" in res.skipped_reason
    assert res.json_path is None  # nothing generated, no exception


def test_broken_toolchain_degrades(monkeypatch):
    proj = _proj()
    _instantiate(proj, "--no-portal")  # scaffold the package
    # Simulate a present-but-broken toolchain: the compile step raises mid-run.
    monkeypatch.setattr(
        portal_build,
        "_run_workflow",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    res = build_and_maybe_provision(proj, "demo")
    assert res.skipped_reason and "generation failed" in res.skipped_reason


def test_no_kickoff_package_skips():
    res = build_and_maybe_provision(_proj(), "demo")
    assert res.skipped_reason and "no kickoff package" in res.skipped_reason


# --------------------------------------------------------------------------- FR-2 / FR-4 happy path


def test_helper_generates_skeleton_on_fresh_project():
    proj = _proj()
    _instantiate(proj, "--no-portal")  # package exists, no authoring yet
    res = build_and_maybe_provision(proj, "demo")
    assert res.ok and res.skipped_reason is None
    assert res.uid == "cc-portal-kickoff-demo"
    d = json.loads(Path(res.json_path).read_text())
    assert d["uid"] == "cc-portal-kickoff-demo"
    assert WORKBOOK_TAG in d["tags"]  # FR-11 tag contract
    assert "templating" in d  # FR-4 empty-state renders as a valid dashboard


def test_instantiate_generates_workbook_by_default():
    proj = _proj()
    out = _instantiate(proj)
    assert out.exit_code == 0
    dash = proj / ".startd8" / "dashboards"
    assert dash.is_dir() and list(dash.glob("cc-portal-kickoff-*.json"))
    assert any("Workbook:" in ln for ln in out.stdout.splitlines())


def test_no_portal_skips_generation():
    proj = _proj()
    out = _instantiate(proj, "--no-portal")
    assert out.exit_code == 0
    assert not (proj / ".startd8" / "dashboards").exists()
    assert any("skipped (--no-portal)" in ln for ln in out.stdout.splitlines())


def test_preview_is_side_effect_free():
    proj = _proj()
    out = runner.invoke(kickoff_kernel_app, ["instantiate", str(proj)])  # no --apply
    assert not (proj / ".startd8" / "dashboards").exists()
    assert not any("Workbook" in ln for ln in out.stdout.splitlines())


# --------------------------------------------------------------------------- FR-7 non-fatal isolation


def test_generation_failure_never_changes_instantiate_exit(monkeypatch):
    proj = _proj()
    # Force the helper to blow up entirely; instantiate must still exit 0 (the write succeeded).
    monkeypatch.setattr(
        portal_build,
        "build_and_maybe_provision",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("catastrophic")),
    )
    out = _instantiate(proj)
    assert (
        out.exit_code == 0
    )  # FR-7: dashboard failure never fails the source-of-record write
    assert (
        proj / "docs" / "kickoff" / "inputs" / "conventions.yaml"
    ).is_file()  # scaffold intact


# --------------------------------------------------------------------------- FR-11 portfolio index


def test_index_spec_is_a_dashlist_by_workbook_tag():
    spec = build_workbook_index_spec()
    assert spec["uid"] == INDEX_UID
    p = spec["panels"][0]
    assert p["type"] == "dashlist" and p["options"]["tags"] == [WORKBOOK_TAG]


def test_index_compiles_empty_portfolio():
    res = build_index(_proj())  # zero Workbooks anywhere — must still render
    assert res.ok, res.skipped_reason
    d = json.loads(Path(res.json_path).read_text())
    assert d["uid"] == INDEX_UID and d["panels"][0]["type"] == "dashlist"


def test_index_provision_to_shared_url_needs_confirmation():
    # NR-6: a non-loopback provision URL for the global index requires confirm_shared.
    blocked = build_index(_proj(), provision_url="http://grafana.example.com:3000")
    assert blocked.skipped_reason and "confirmation" in blocked.skipped_reason
    # loopback is fine without confirmation (generation still $0; provisioning would need a live server)
    assert portal_build._is_loopback("http://localhost:3000")
    assert not portal_build._is_loopback("http://grafana.example.com:3000")
