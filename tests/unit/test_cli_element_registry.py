"""Tests for the element-registry CLI sub-commands (REQ-MP-1109)."""

import json
from pathlib import Path

from typer.testing import CliRunner

from startd8.cli import element_registry_app
from startd8.element_registry import ElementEntry, ElementRegistry

runner = CliRunner()


def _seed_registry(state_dir: Path) -> ElementRegistry:
    """Create and populate a registry with sample entries."""
    reg = ElementRegistry(state_dir=state_dir)
    reg.put(
        ElementEntry(
            element_id="pkg.mod.MyClass",
            kind="class",
            name="MyClass",
            file_path="src/pkg/mod.py",
            line=10,
        )
    )
    reg.put(
        ElementEntry(
            element_id="pkg.mod.my_func",
            kind="function",
            name="my_func",
            file_path="src/pkg/mod.py",
            line=50,
        )
    )
    reg.put(
        ElementEntry(
            element_id="pkg.util.CONST",
            kind="constant",
            name="CONST",
            file_path="src/pkg/util.py",
        )
    )
    # Add phase status to one entry
    reg.set_phase_status("pkg.mod.MyClass", phase="extraction", status="complete")
    reg.set_phase_status("pkg.mod.my_func", phase="extraction", status="complete")
    reg.set_phase_status("pkg.mod.my_func", phase="generation", status="complete")
    return reg


# ── list ──────────────────────────────────────────────────────────────────


def test_list_empty_registry(tmp_path: Path):
    """list with empty registry shows empty table."""
    result = runner.invoke(
        element_registry_app, ["list", "--state-dir", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "No elements registered" in result.stdout


def test_list_with_entries(tmp_path: Path):
    """list with entries shows table with correct columns."""
    _seed_registry(tmp_path)
    result = runner.invoke(
        element_registry_app, ["list", "--state-dir", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "pkg.mod.MyClass" in result.stdout
    assert "pkg.mod.my_func" in result.stdout
    assert "pkg.util.CONST" in result.stdout
    assert "class" in result.stdout
    assert "function" in result.stdout
    assert "constant" in result.stdout


# ── show ──────────────────────────────────────────────────────────────────


def test_show_valid_id(tmp_path: Path):
    """show with valid ID displays details."""
    _seed_registry(tmp_path)
    result = runner.invoke(
        element_registry_app,
        ["show", "pkg.mod.MyClass", "--state-dir", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "pkg.mod.MyClass" in result.stdout
    assert "class" in result.stdout
    assert "MyClass" in result.stdout
    assert "src/pkg/mod.py" in result.stdout


def test_show_unknown_id(tmp_path: Path):
    """show with unknown ID prints error."""
    _seed_registry(tmp_path)
    result = runner.invoke(
        element_registry_app,
        ["show", "nonexistent.id", "--state-dir", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "element not found" in result.stdout


# ── stats ─────────────────────────────────────────────────────────────────


def test_stats_valid_json(tmp_path: Path):
    """stats outputs valid JSON with expected keys."""
    _seed_registry(tmp_path)
    result = runner.invoke(
        element_registry_app, ["stats", "--state-dir", str(tmp_path)]
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["total_entries"] == 3
    assert data["entries_by_kind"]["class"] == 1
    assert data["entries_by_kind"]["function"] == 1
    assert data["entries_by_kind"]["constant"] == 1
    assert data["files_covered"] == 2
    assert "extraction" in data["by_phase_status"]
    assert data["by_phase_status"]["extraction"]["complete"] == 2


def test_stats_empty_registry(tmp_path: Path):
    """stats on empty registry returns zeroes."""
    result = runner.invoke(
        element_registry_app, ["stats", "--state-dir", str(tmp_path)]
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["total_entries"] == 0
    assert data["entries_by_kind"] == {}
    assert data["files_covered"] == 0


# ── clear ─────────────────────────────────────────────────────────────────


def test_clear_empties_registry(tmp_path: Path):
    """clear with --yes removes all entries."""
    _seed_registry(tmp_path)
    result = runner.invoke(
        element_registry_app,
        ["clear", "--state-dir", str(tmp_path), "--yes"],
    )
    assert result.exit_code == 0
    assert "Cleared 3 element(s)" in result.stdout

    # Verify registry is empty
    reg = ElementRegistry(state_dir=tmp_path)
    assert len(reg) == 0


def test_clear_empty_registry(tmp_path: Path):
    """clear on already empty registry reports it."""
    result = runner.invoke(
        element_registry_app,
        ["clear", "--state-dir", str(tmp_path), "--yes"],
    )
    assert result.exit_code == 0
    assert "already empty" in result.stdout
