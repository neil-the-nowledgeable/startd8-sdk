"""M0 unit tests for the deploy-harness discovery layer (FR-1/2/3). No live process."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.deploy_harness import (
    DEP_FLOOR,
    MODE_DEPLOYED,
    MODE_INSTALLED,
    MODE_UNKNOWN,
    detect_deps,
    detect_entrypoint,
    detect_mode,
)

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- entry point (FR-1)


def _make_pkg(root: Path, filename: str = "main.py") -> None:
    pkg = root / "app"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / filename).write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8"
    )


def test_entrypoint_canonical_app_main(tmp_path: Path) -> None:
    _make_pkg(tmp_path, "main.py")
    ep, devs = detect_entrypoint(tmp_path)
    assert ep.target == "app.main:app"
    assert ep.matched_by == "app-package-default"
    assert not [d for d in devs if d.code.startswith("entrypoint")]


def test_entrypoint_manifest_marks_matched_by_manifest(tmp_path: Path) -> None:
    _make_pkg(tmp_path, "main.py")
    (tmp_path / "app.yaml").write_text("name: demo\npackage: app\n", encoding="utf-8")
    ep, _ = detect_entrypoint(tmp_path)
    assert ep.target == "app.main:app"
    assert ep.matched_by == "manifest"


def test_entrypoint_server_variant_is_noncanonical_deviation(tmp_path: Path) -> None:
    _make_pkg(tmp_path, "server.py")
    ep, devs = detect_entrypoint(tmp_path)
    assert ep.target == "app.server:app"
    assert any(d.code == "entrypoint-noncanonical" for d in devs)


def test_entrypoint_root_level_main_is_candidate(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8"
    )
    ep, devs = detect_entrypoint(tmp_path)
    assert ep.target == "main:app"
    assert ep.matched_by == "candidate"
    assert any(d.code == "entrypoint-noncanonical" for d in devs)


def test_entrypoint_bounded_scan_finds_nonstandard_module(tmp_path: Path) -> None:
    weird = tmp_path / "src" / "service"
    weird.mkdir(parents=True)
    (weird / "boot.py").write_text(
        "from fastapi import FastAPI\nserver = FastAPI()\n", encoding="utf-8"
    )
    ep, _ = detect_entrypoint(tmp_path)
    assert ep.target == "src.service.boot:server"
    assert ep.matched_by == "scan"


def test_entrypoint_scan_ambiguity_is_recorded(tmp_path: Path) -> None:
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    b.write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    ep, devs = detect_entrypoint(tmp_path)
    assert ep.matched_by == "scan"
    assert ep.target == "a:app"  # deterministic: sorted-path first
    assert any(d.code == "entrypoint-ambiguous" for d in devs)


def test_entrypoint_none_when_no_app(tmp_path: Path) -> None:
    (tmp_path / "readme.txt").write_text("nothing here", encoding="utf-8")
    ep, devs = detect_entrypoint(tmp_path)
    assert ep.target is None
    assert ep.matched_by == "none"
    assert any(d.code == "entrypoint-missing" for d in devs)


# --------------------------------------------------------------------------- dependencies (FR-2)


def test_deps_requirements_txt_pinned(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text(
        "# comment\nfastapi==0.110.0\nsqlmodel==0.0.16\n-r other.txt\n",
        encoding="utf-8",
    )
    dep, devs = detect_deps(tmp_path)
    assert dep.source == "requirements.txt"
    assert dep.packages == ["fastapi==0.110.0", "sqlmodel==0.0.16"]
    assert dep.pinned is True
    assert not devs


def test_deps_requirements_unpinned(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\n", encoding="utf-8")
    dep, _ = detect_deps(tmp_path)
    assert dep.pinned is False


def test_deps_pyproject_project_table(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["fastapi", "sqlmodel>=0.0.16"]\n',
        encoding="utf-8",
    )
    dep, _ = detect_deps(tmp_path)
    assert dep.source == "pyproject:project"
    assert "fastapi" in dep.packages and "sqlmodel>=0.0.16" in dep.packages


def test_deps_missing_falls_back_to_floor_with_deviation(tmp_path: Path) -> None:
    dep, devs = detect_deps(tmp_path)
    assert dep.source == "dep_floor"
    assert dep.packages == list(DEP_FLOOR)
    assert any(d.code == "deps-missing" for d in devs)


# --------------------------------------------------------------------------- mode (FR-3)


def _write_settings(root: Path, header: str) -> None:
    pkg = root / "app"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "settings.py").write_text(
        header + "\nDEPLOYMENT_MODE = 'x'\n", encoding="utf-8"
    )


def test_mode_absent_settings_is_installed_default(tmp_path: Path) -> None:
    # installed mode emits NO settings.py — absence is the expected installed case, not ambiguity.
    (tmp_path / "app").mkdir()
    mode, deriv, devs = detect_mode(tmp_path)
    assert (mode, deriv) == (MODE_INSTALLED, "default")
    assert not devs


def test_mode_deployed_header(tmp_path: Path) -> None:
    _write_settings(tmp_path, "# startd8-mode: deployed")
    mode, deriv, devs = detect_mode(tmp_path)
    assert (mode, deriv) == (MODE_DEPLOYED, "header")
    assert not devs


def test_mode_installed_header(tmp_path: Path) -> None:
    _write_settings(tmp_path, "# startd8-mode: installed")
    mode, deriv, _ = detect_mode(tmp_path)
    assert (mode, deriv) == (MODE_INSTALLED, "header")


def test_mode_garbled_settings_is_unknown_not_silent_installed(tmp_path: Path) -> None:
    # present-but-headerless settings.py is genuinely ambiguous → unknown + deviation (CRP R1-F8).
    _write_settings(tmp_path, "# no mode header here")
    mode, deriv, devs = detect_mode(tmp_path)
    assert mode == MODE_UNKNOWN
    assert deriv == "ambiguous"
    assert any(d.code == "mode-ambiguous" for d in devs)


def test_deps_strips_inline_comments(tmp_path: Path) -> None:
    # pip rejects 'startd8  # comment' as a CLI arg — the inline comment must be stripped.
    (tmp_path / "requirements.txt").write_text(
        "fastapi\nstartd8  # AI-layer runtime: install startd8[gemini]\n",
        encoding="utf-8",
    )
    dep, _ = detect_deps(tmp_path)
    assert dep.packages == ["fastapi", "startd8"]


def test_deps_preserves_url_fragment(tmp_path: Path) -> None:
    # '#egg=' has no preceding whitespace — must NOT be treated as a comment.
    (tmp_path / "requirements.txt").write_text(
        "pkg @ git+https://example.com/x.git#egg=pkg\n", encoding="utf-8"
    )
    dep, _ = detect_deps(tmp_path)
    assert dep.packages == ["pkg @ git+https://example.com/x.git#egg=pkg"]
