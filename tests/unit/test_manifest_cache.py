"""Tests for startd8.utils.manifest_cache — batch generation and caching."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from startd8.utils.manifest_cache import (
    check_manifests_fresh,
    generate_project_manifests,
    _scan_python_files,
    _should_skip_dir,
    _load_index,
    _save_index,
)


# ═══════════════════════════════════════════════════════════════════════════
# Skip pattern tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSkipPatterns:
    def test_skip_pycache(self):
        assert _should_skip_dir("__pycache__")

    def test_skip_venv(self):
        assert _should_skip_dir(".venv")
        assert _should_skip_dir("venv")

    def test_skip_git(self):
        assert _should_skip_dir(".git")

    def test_skip_egg_info(self):
        assert _should_skip_dir(".egg-info")
        assert _should_skip_dir("mypackage.egg-info")

    def test_skip_node_modules(self):
        assert _should_skip_dir("node_modules")

    def test_allow_normal_dir(self):
        assert not _should_skip_dir("src")
        assert not _should_skip_dir("utils")


# ═══════════════════════════════════════════════════════════════════════════
# File scanning tests
# ═══════════════════════════════════════════════════════════════════════════

class TestFileScanning:
    def test_scan_finds_py_files(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("x = 1")
        (tmp_path / "b.py").write_text("y = 2")
        (tmp_path / "c.txt").write_text("not python")
        files = _scan_python_files(tmp_path)
        assert len(files) == 2
        assert all(f.suffix == ".py" for f in files)

    def test_scan_skips_pycache(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("x = 1")
        cache_dir = tmp_path / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "cached.py").write_text("# cached")
        files = _scan_python_files(tmp_path)
        assert len(files) == 1

    def test_scan_recursive(self, tmp_path: Path):
        sub = tmp_path / "pkg"
        sub.mkdir()
        (tmp_path / "a.py").write_text("x = 1")
        (sub / "b.py").write_text("y = 2")
        files = _scan_python_files(tmp_path)
        assert len(files) == 2

    def test_scan_empty_dir(self, tmp_path: Path):
        files = _scan_python_files(tmp_path)
        assert files == []


# ═══════════════════════════════════════════════════════════════════════════
# Index round-trip tests
# ═══════════════════════════════════════════════════════════════════════════

class TestIndexRoundTrip:
    def test_save_and_load(self, tmp_path: Path):
        index = {"src/a.py": "sha256:abc123", "src/b.py": "sha256:def456"}
        _save_index(tmp_path, index)
        loaded = _load_index(tmp_path)
        assert loaded == index

    def test_save_includes_meta(self, tmp_path: Path):
        """Saved index contains _meta with schema and python versions."""
        _save_index(tmp_path, {"a.py": "sha256:abc"})
        raw = json.loads((tmp_path / "_index.json").read_text())
        assert "_meta" in raw
        assert "schema_version" in raw["_meta"]
        assert "python_version" in raw["_meta"]

    def test_load_nonexistent(self, tmp_path: Path):
        loaded = _load_index(tmp_path)
        assert loaded == {}

    def test_load_corrupt(self, tmp_path: Path):
        (tmp_path / "_index.json").write_text("not valid json{{{")
        loaded = _load_index(tmp_path)
        assert loaded == {}

    def test_load_missing_meta(self, tmp_path: Path):
        """Legacy index without _meta is treated as stale."""
        (tmp_path / "_index.json").write_text(
            json.dumps({"src/a.py": "sha256:abc123"})
        )
        loaded = _load_index(tmp_path)
        assert loaded == {}


# ═══════════════════════════════════════════════════════════════════════════
# Batch generation tests
# ═══════════════════════════════════════════════════════════════════════════

def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal project structure for testing."""
    project_root = tmp_path / "project"
    src = project_root / "src" / "mypkg"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text('"""Init."""\n')
    (src / "module_a.py").write_text(
        'def func_a() -> int:\n    """Function A."""\n    return 1\n'
    )
    (src / "module_b.py").write_text(
        'class ClassB:\n    """Class B."""\n    pass\n'
    )
    return project_root


class TestBatchGeneration:
    def test_generates_all_files(self, tmp_path: Path):
        project_root = _setup_project(tmp_path)
        manifests = generate_project_manifests(project_root)
        assert len(manifests) == 3  # __init__.py, module_a.py, module_b.py

    def test_cache_hit_on_second_run(self, tmp_path: Path):
        project_root = _setup_project(tmp_path)
        # First run — generates fresh
        m1 = generate_project_manifests(project_root)
        # Second run — should hit cache
        m2 = generate_project_manifests(project_root)
        assert len(m1) == len(m2)
        # Verify digests match
        for key in m1:
            assert m1[key].digest == m2[key].digest

    def test_cache_invalidation_on_change(self, tmp_path: Path):
        project_root = _setup_project(tmp_path)
        m1 = generate_project_manifests(project_root)

        # Modify a file
        mod_a = project_root / "src" / "mypkg" / "module_a.py"
        mod_a.write_text(
            'def func_a() -> int:\n    """Modified."""\n    return 2\n'
        )

        m2 = generate_project_manifests(project_root)
        rel_key = next(k for k in m2 if "module_a" in k)
        assert m1[rel_key].digest != m2[rel_key].digest

    def test_custom_cache_dir(self, tmp_path: Path):
        project_root = _setup_project(tmp_path)
        cache_dir = tmp_path / "custom_cache"
        generate_project_manifests(project_root, cache_dir=cache_dir)
        assert cache_dir.exists()
        assert any(cache_dir.iterdir())


# ═══════════════════════════════════════════════════════════════════════════
# Staleness detection tests
# ═══════════════════════════════════════════════════════════════════════════

class TestStalenessDetection:
    def test_fresh_after_generation(self, tmp_path: Path):
        project_root = _setup_project(tmp_path)
        generate_project_manifests(project_root)
        fresh, stale = check_manifests_fresh(project_root)
        assert fresh is True
        assert stale == []

    def test_stale_after_modification(self, tmp_path: Path):
        project_root = _setup_project(tmp_path)
        generate_project_manifests(project_root)

        # Modify a file
        mod_a = project_root / "src" / "mypkg" / "module_a.py"
        mod_a.write_text('def func_a() -> str:\n    return "changed"\n')

        fresh, stale = check_manifests_fresh(project_root)
        assert fresh is False
        assert len(stale) >= 1
        assert any("module_a" in f for f in stale)

    def test_stale_new_file(self, tmp_path: Path):
        project_root = _setup_project(tmp_path)
        generate_project_manifests(project_root)

        # Add a new file
        (project_root / "src" / "mypkg" / "new_module.py").write_text("x = 1\n")

        fresh, stale = check_manifests_fresh(project_root)
        assert fresh is False
        assert any("new_module" in f for f in stale)

    def test_stale_no_cache(self, tmp_path: Path):
        project_root = _setup_project(tmp_path)
        fresh, stale = check_manifests_fresh(project_root)
        assert fresh is False
        assert len(stale) == 3


# ═══════════════════════════════════════════════════════════════════════════
# Phase 3: Schema version cache invalidation (AC-C1, AC-C2)
# ═══════════════════════════════════════════════════════════════════════════

class TestSchemaVersionCache:
    def test_schema_upgrade_invalidates_cache(self, tmp_path: Path):
        """AC-C1: Phase 1 cache entries regenerated on first Phase 3 run."""
        from unittest.mock import patch

        project_root = _setup_project(tmp_path)
        # First run generates fresh manifests
        m1 = generate_project_manifests(project_root)
        assert len(m1) == 3

        # Simulate schema upgrade: patch SCHEMA_VERSION to a new value
        with patch("startd8.utils.manifest_cache.SCHEMA_VERSION", "99.0.0"):
            m2 = generate_project_manifests(project_root)

        # Same files, same content, but schema version changed → cache miss → regenerated
        assert len(m2) == 3
        # Digests should match (same source content)
        for key in m1:
            assert m1[key].digest == m2[key].digest

    def test_python_version_change_invalidates_cache(self, tmp_path: Path):
        """Cache entries regenerated when Python interpreter version changes."""
        from unittest.mock import patch

        project_root = _setup_project(tmp_path)
        m1 = generate_project_manifests(project_root)
        assert len(m1) == 3

        # Simulate interpreter upgrade: change _PYTHON_VERSION_TAG
        with patch("startd8.utils.manifest_cache._PYTHON_VERSION_TAG", "2.7"):
            m2 = generate_project_manifests(project_root)

        # Same files, same content, but Python version changed → cache miss → regenerated
        assert len(m2) == 3
        for key in m1:
            assert m1[key].digest == m2[key].digest

    def test_phase1_manifest_loads_in_phase3(self, tmp_path: Path):
        """AC-C2: Phase 1 manifests load in Phase 3 — symbol_info defaults to None."""
        from startd8.utils.code_manifest import FileManifest

        # Create a Phase 1 manifest (no symbol_info field)
        phase1_data = {
            "schema_version": "1.0.0",
            "file": "src/pkg/mod.py",
            "module": "pkg.mod",
            "digest": "sha256:abc123",
            "python_version": "3.9",
            "elements": [
                {
                    "kind": "function",
                    "name": "my_func",
                    "fqn": "pkg.mod.my_func",
                    "span": {"start_line": 1, "start_col": 0, "end_line": 2, "end_col": 0},
                    "signature": {"params": [], "return_annotation": None},
                }
            ],
            "imports": [],
            "dependencies": {},
            "errors": [],
            "generated_at": "2026-01-01T00:00:00Z",
        }
        loaded = FileManifest.model_validate(phase1_data)
        assert loaded.schema_version == "1.0.0"
        assert loaded.elements[0].symbol_info is None


# ═══════════════════════════════════════════════════════════════════════════
# Batch performance benchmark (Gap 6)
# ═══════════════════════════════════════════════════════════════════════════

class TestBatchPerformance:
    @pytest.mark.slow
    def test_real_project_under_10s(self):
        """Verify generate_project_manifests() on real src/startd8/ completes in <10s."""
        project_root = Path(__file__).resolve().parents[2]  # repo root
        src_dir = project_root / "src" / "startd8"
        if not src_dir.exists():
            pytest.skip("Source tree not found — running outside repo")

        start = time.perf_counter()
        manifests = generate_project_manifests(project_root)
        elapsed = time.perf_counter() - start

        assert len(manifests) > 0, "Should find Python files"
        assert elapsed < 10.0, f"Batch generation took {elapsed:.2f}s (budget: 10s)"
