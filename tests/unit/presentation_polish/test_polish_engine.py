"""Engine: apply writes the design system idempotently and non-destructively (FR-4, FR-15, FR-20)."""

import json

import pytest

from startd8.presentation_polish import PolishConfig, apply_polish
from startd8.presentation_polish.engine import (
    MANIFEST_RELPATH,
    STATIC_SETUP_RELPATH,
    STYLESHEET_RELPATH,
    FileStatus,
)

pytestmark = []


def _project(tmp_path):
    (tmp_path / "app").mkdir()
    return tmp_path


def test_apply_creates_files_and_manifest(tmp_path):
    root = _project(tmp_path)
    result = apply_polish(PolishConfig(project_root=root, theme="professional"))

    assert result.cost_usd == 0.0
    assert (root / STYLESHEET_RELPATH).is_file()
    assert (root / STATIC_SETUP_RELPATH).is_file()
    assert (root / MANIFEST_RELPATH).is_file()
    statuses = dict(result.files)
    assert statuses[STYLESHEET_RELPATH] == FileStatus.CREATED
    assert statuses[STATIC_SETUP_RELPATH] == FileStatus.CREATED

    manifest = json.loads((root / MANIFEST_RELPATH).read_text())
    assert manifest["theme"] == "professional"
    assert STYLESHEET_RELPATH in manifest["files"]


def test_apply_is_idempotent(tmp_path):
    root = _project(tmp_path)
    apply_polish(PolishConfig(project_root=root, theme="professional"))
    css_first = (root / STYLESHEET_RELPATH).read_text()
    manifest_first = (root / MANIFEST_RELPATH).read_text()

    result2 = apply_polish(PolishConfig(project_root=root, theme="professional"))
    assert all(s == FileStatus.UNCHANGED for _, s in result2.files)
    assert (root / STYLESHEET_RELPATH).read_text() == css_first
    assert (root / MANIFEST_RELPATH).read_text() == manifest_first  # manifest byte-stable too


def test_changing_theme_updates(tmp_path):
    root = _project(tmp_path)
    apply_polish(PolishConfig(project_root=root, theme="professional"))
    result = apply_polish(PolishConfig(project_root=root, theme="editorial"))
    assert dict(result.files)[STYLESHEET_RELPATH] == FileStatus.UPDATED
    assert "theme=editorial" in (root / STYLESHEET_RELPATH).read_text()


def test_non_destructive_to_user_files(tmp_path):
    root = _project(tmp_path)
    # user authored their own stylesheet at our path, WITHOUT the polish marker
    css_path = root / STYLESHEET_RELPATH
    css_path.parent.mkdir(parents=True, exist_ok=True)
    css_path.write_text("/* my own hand-written styles */\nbody { color: red; }\n")

    result = apply_polish(PolishConfig(project_root=root, theme="professional"))
    assert dict(result.files)[STYLESHEET_RELPATH] == FileStatus.SKIPPED_USER_OWNED
    assert css_path.read_text() == "/* my own hand-written styles */\nbody { color: red; }\n"
    assert STYLESHEET_RELPATH in result.skipped_user_owned


def test_check_mode_writes_nothing(tmp_path):
    root = _project(tmp_path)
    result = apply_polish(PolishConfig(project_root=root, theme="professional", check=True))
    assert not (root / STYLESHEET_RELPATH).exists()
    assert not (root / MANIFEST_RELPATH).exists()
    assert result.has_drift  # everything "missing"
    assert dict(result.files)[STYLESHEET_RELPATH] == FileStatus.MISSING


def test_check_mode_detects_in_sync_and_drift(tmp_path):
    root = _project(tmp_path)
    apply_polish(PolishConfig(project_root=root, theme="professional"))
    # in sync
    r = apply_polish(PolishConfig(project_root=root, theme="professional", check=True))
    assert not r.has_drift
    # hand-tamper a polish-owned file (keep the marker) → drift
    css = root / STYLESHEET_RELPATH
    css.write_text(css.read_text() + "\n/* tampered, still STARTD8-POLISH marked */\n")
    r2 = apply_polish(PolishConfig(project_root=root, theme="professional", check=True))
    assert dict(r2.files)[STYLESHEET_RELPATH] == FileStatus.DRIFT


def test_unknown_theme_raises(tmp_path):
    with pytest.raises(KeyError):
        apply_polish(PolishConfig(project_root=_project(tmp_path), theme="nope"))


def test_missing_project_root_raises(tmp_path):
    with pytest.raises(NotADirectoryError):
        apply_polish(PolishConfig(project_root=tmp_path / "does-not-exist", theme="professional"))
