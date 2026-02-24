"""AR-821: SCAFFOLD module inventory collection tests.

Verifies that _collect_module_inventory() correctly discovers
importable Python packages from the project directory structure.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def project_with_src(tmp_path):
    """Create a project with src/ layout containing packages."""
    src = tmp_path / "src"
    # pkg_a with subpackage
    (src / "pkg_a").mkdir(parents=True)
    (src / "pkg_a" / "__init__.py").write_text("")
    (src / "pkg_a" / "sub").mkdir()
    (src / "pkg_a" / "sub" / "__init__.py").write_text("")

    # pkg_b flat package
    (src / "pkg_b").mkdir()
    (src / "pkg_b" / "__init__.py").write_text("")

    return tmp_path


@pytest.fixture
def project_no_src(tmp_path):
    """Create a project without src/ layout."""
    (tmp_path / "mylib").mkdir()
    (tmp_path / "mylib" / "__init__.py").write_text("")
    (tmp_path / "mylib" / "utils").mkdir()
    (tmp_path / "mylib" / "utils" / "__init__.py").write_text("")
    return tmp_path


@pytest.fixture
def empty_project(tmp_path):
    """Create a project with no Python packages."""
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text("# Empty")
    return tmp_path


@pytest.mark.unit
class TestCollectModuleInventory:
    """Test ScaffoldPhaseHandler._collect_module_inventory()."""

    def test_collects_packages_from_src(self, project_with_src):
        """Should find packages under src/ directory."""
        from startd8.contractors.context_seed_handlers import ScaffoldPhaseHandler

        modules = ScaffoldPhaseHandler._collect_module_inventory(project_with_src)

        assert "pkg_a" in modules
        assert "pkg_a.sub" in modules
        assert "pkg_b" in modules

    def test_nested_packages(self, project_with_src):
        """Should return dotted paths for nested packages."""
        from startd8.contractors.context_seed_handlers import ScaffoldPhaseHandler

        modules = ScaffoldPhaseHandler._collect_module_inventory(project_with_src)

        # Verify dotted notation
        nested = [m for m in modules if "." in m]
        assert len(nested) >= 1
        assert "pkg_a.sub" in nested

    def test_empty_project(self, empty_project):
        """Should return empty list when no __init__.py found."""
        from startd8.contractors.context_seed_handlers import ScaffoldPhaseHandler

        modules = ScaffoldPhaseHandler._collect_module_inventory(empty_project)
        assert modules == []

    def test_no_src_dir_falls_back_to_root(self, project_no_src):
        """Should scan project root when src/ doesn't exist."""
        from startd8.contractors.context_seed_handlers import ScaffoldPhaseHandler

        modules = ScaffoldPhaseHandler._collect_module_inventory(project_no_src)

        assert "mylib" in modules
        assert "mylib.utils" in modules

    def test_returns_sorted_unique(self, project_with_src):
        """Results should be sorted and deduplicated."""
        from startd8.contractors.context_seed_handlers import ScaffoldPhaseHandler

        modules = ScaffoldPhaseHandler._collect_module_inventory(project_with_src)

        assert modules == sorted(modules)
        assert len(modules) == len(set(modules))

    def test_nonexistent_path_returns_empty(self, tmp_path):
        """Should handle nonexistent paths gracefully."""
        from startd8.contractors.context_seed_handlers import ScaffoldPhaseHandler

        modules = ScaffoldPhaseHandler._collect_module_inventory(
            tmp_path / "nonexistent"
        )
        assert modules == []
