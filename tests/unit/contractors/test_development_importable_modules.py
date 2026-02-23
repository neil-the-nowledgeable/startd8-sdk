"""Tests for ``_build_importable_modules()`` in ``LeadContractorChunkExecutor`` (AR-150).

Validates that the IMPLEMENT prompt enrichment lists ground-truth importable
modules for each package directory containing a target file.
"""

from __future__ import annotations

import os
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest


@dataclass
class _FakeChunk:
    """Minimal stand-in for ``DevelopmentChunk``."""

    chunk_id: str = "test-chunk"
    description: str = "test"
    dependencies: List[str] = field(default_factory=list)
    file_targets: List[str] = field(default_factory=list)
    implementation_prompt: str = ""
    test_commands: List[str] = field(default_factory=list)
    max_retries: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)


def _make_executor(project_root: Path):
    """Create a ``LeadContractorChunkExecutor`` with mock agents."""
    from startd8.contractors.artisan_phases.development import (
        LeadContractorChunkExecutor,
    )

    return LeadContractorChunkExecutor(
        lead_agent="mock:mock-model",
        drafter_agent="mock:mock-model",
        project_root=project_root,
    )


class TestBuildImportableModules:
    """Tests for ``LeadContractorChunkExecutor._build_importable_modules``."""

    def test_no_project_root_returns_empty(self):
        """When project_root is None, returns []."""
        from startd8.contractors.artisan_phases.development import (
            LeadContractorChunkExecutor,
        )

        executor = LeadContractorChunkExecutor(
            lead_agent="mock:mock-model",
            drafter_agent="mock:mock-model",
            project_root=None,
        )
        chunk = _FakeChunk(file_targets=["src/mypkg/foo.py"])
        result = executor._build_importable_modules(chunk)
        assert result == []

    def test_no_python_targets_returns_empty(self, tmp_path: Path):
        """When no .py files in targets, returns []."""
        executor = _make_executor(tmp_path)
        chunk = _FakeChunk(file_targets=["config.yaml", "README.md"])
        result = executor._build_importable_modules(chunk)
        assert result == []

    def test_lists_sibling_modules(self, tmp_path: Path):
        """Lists .py modules in the target's parent package directory."""
        src = tmp_path / "src" / "mypkg" / "contractors"
        src.mkdir(parents=True)
        (tmp_path / "src" / "mypkg" / "__init__.py").touch()
        (src / "__init__.py").touch()
        (src / "prime_contractor.py").write_text("x = 1\n", encoding="utf-8")
        (src / "artisan_contractor.py").write_text("y = 2\n", encoding="utf-8")
        (src / "helpers.py").write_text("z = 3\n", encoding="utf-8")

        executor = _make_executor(tmp_path)
        chunk = _FakeChunk(
            file_targets=["src/mypkg/contractors/new_module.py"]
        )
        result = executor._build_importable_modules(chunk)
        joined = "\n".join(result)
        assert "artisan_contractor" in joined
        assert "prime_contractor" in joined
        assert "helpers" in joined
        assert "Importable Modules" in joined

    def test_excludes_init_py(self, tmp_path: Path):
        """__init__.py is not listed as an importable module."""
        src = tmp_path / "src" / "mypkg"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("# init\n", encoding="utf-8")
        (src / "real.py").write_text("x = 1\n", encoding="utf-8")

        executor = _make_executor(tmp_path)
        chunk = _FakeChunk(file_targets=["src/mypkg/new.py"])
        result = executor._build_importable_modules(chunk)
        joined = "\n".join(result)
        assert "__init__" not in joined
        assert "real" in joined

    def test_includes_sub_packages(self, tmp_path: Path):
        """Sub-packages (dirs with __init__.py) are listed with (package) hint."""
        src = tmp_path / "src" / "mypkg"
        src.mkdir(parents=True)
        (src / "__init__.py").touch()
        sub = src / "subpkg"
        sub.mkdir()
        (sub / "__init__.py").touch()
        (src / "module_a.py").write_text("x = 1\n", encoding="utf-8")

        executor = _make_executor(tmp_path)
        chunk = _FakeChunk(file_targets=["src/mypkg/new.py"])
        result = executor._build_importable_modules(chunk)
        joined = "\n".join(result)
        assert "subpkg" in joined
        assert "(package)" in joined

    def test_nonexistent_package_dir_returns_empty(self, tmp_path: Path):
        """When target's parent dir doesn't exist, returns []."""
        # No src/ or package dirs created
        executor = _make_executor(tmp_path)
        chunk = _FakeChunk(
            file_targets=["src/nonexistent/pkg/module.py"]
        )
        result = executor._build_importable_modules(chunk)
        assert result == []

    def test_cap_at_max_modules(self, tmp_path: Path):
        """Module list is capped at _MAX_IMPORTABLE_MODULES."""
        src = tmp_path / "src" / "bigpkg"
        src.mkdir(parents=True)
        (src / "__init__.py").touch()
        # Create 60 modules (exceeds cap of 50)
        for i in range(60):
            (src / f"mod_{i:03d}.py").write_text(f"x = {i}\n", encoding="utf-8")

        executor = _make_executor(tmp_path)
        chunk = _FakeChunk(file_targets=["src/bigpkg/new.py"])
        result = executor._build_importable_modules(chunk)
        joined = "\n".join(result)
        # Count module entries
        module_lines = [l for l in joined.split("\n") if l.startswith("- `")]
        assert len(module_lines) <= 50

    def test_deduplicates_package_dirs(self, tmp_path: Path):
        """Multiple targets in the same package only list modules once."""
        src = tmp_path / "src" / "mypkg"
        src.mkdir(parents=True)
        (src / "__init__.py").touch()
        (src / "existing.py").write_text("x = 1\n", encoding="utf-8")

        executor = _make_executor(tmp_path)
        chunk = _FakeChunk(
            file_targets=["src/mypkg/new_a.py", "src/mypkg/new_b.py"]
        )
        result = executor._build_importable_modules(chunk)
        joined = "\n".join(result)
        # "existing" should appear exactly once
        assert joined.count("existing") == 1

    def test_root_level_target_skipped(self, tmp_path: Path):
        """Target files at the root level (no parent package) are skipped."""
        (tmp_path / "src").mkdir()
        executor = _make_executor(tmp_path)
        chunk = _FakeChunk(file_targets=["setup.py"])
        result = executor._build_importable_modules(chunk)
        assert result == []
