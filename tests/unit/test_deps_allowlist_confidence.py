"""Tests for dependency allowlist confidence + fallback parsers.

Covers:
- parse_requirements_txt  (6 tests)
- parse_setup_cfg_deps    (4 tests)
- extract_top_level_imports (5 tests)
- scan_task_description_packages (5 tests)
- AvailableDeps source/confidence (5 tests)
- _validate_deps_available confidence (3 tests)
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from startd8.workflows.builtin.preflight_rules._helpers import (
    extract_top_level_imports,
    parse_requirements_txt,
    parse_setup_cfg_deps,
    scan_task_description_packages,
)
from startd8.workflows.builtin.domain_preflight_models import AvailableDeps


# =====================================================================
# TestRequirementsTxtParser
# =====================================================================


class TestRequirementsTxtParser:
    """Tests for parse_requirements_txt."""

    def test_basic_deps(self, tmp_path: Path):
        req = tmp_path / "requirements.txt"
        req.write_text("requests\nflask>=2.0\nhttpx\n")
        result = parse_requirements_txt(req)
        assert result == ["requests", "flask", "httpx"]

    def test_comments_and_blanks(self, tmp_path: Path):
        req = tmp_path / "requirements.txt"
        req.write_text("# comment\nrequests\n\n# another\nflask\n")
        result = parse_requirements_txt(req)
        assert result == ["requests", "flask"]

    def test_flags_skipped(self, tmp_path: Path):
        req = tmp_path / "requirements.txt"
        req.write_text("-r base.txt\n-e .\n--index-url https://example.com\nrequests\n")
        result = parse_requirements_txt(req)
        assert result == ["requests"]

    def test_inline_comments(self, tmp_path: Path):
        req = tmp_path / "requirements.txt"
        req.write_text("requests # HTTP library\nflask # web framework\n")
        result = parse_requirements_txt(req)
        assert result == ["requests", "flask"]

    def test_environment_markers(self, tmp_path: Path):
        req = tmp_path / "requirements.txt"
        req.write_text('requests; python_version >= "3.8"\nflask\n')
        result = parse_requirements_txt(req)
        assert result == ["requests", "flask"]

    def test_missing_file(self, tmp_path: Path):
        missing = tmp_path / "requirements.txt"
        result = parse_requirements_txt(missing)
        assert result == []


# =====================================================================
# TestSetupCfgParser
# =====================================================================


class TestSetupCfgParser:
    """Tests for parse_setup_cfg_deps."""

    def test_basic_deps(self, tmp_path: Path):
        cfg = tmp_path / "setup.cfg"
        cfg.write_text(textwrap.dedent("""\
            [options]
            install_requires =
                requests
                flask>=2.0
        """))
        result = parse_setup_cfg_deps(cfg)
        assert result == ["requests", "flask"]

    def test_multiline(self, tmp_path: Path):
        cfg = tmp_path / "setup.cfg"
        cfg.write_text(textwrap.dedent("""\
            [options]
            install_requires =
                numpy>=1.20
                pandas
                scipy
        """))
        result = parse_setup_cfg_deps(cfg)
        assert result == ["numpy", "pandas", "scipy"]

    def test_missing_section(self, tmp_path: Path):
        cfg = tmp_path / "setup.cfg"
        cfg.write_text("[metadata]\nname = myproject\n")
        result = parse_setup_cfg_deps(cfg)
        assert result == []

    def test_missing_file(self, tmp_path: Path):
        missing = tmp_path / "setup.cfg"
        result = parse_setup_cfg_deps(missing)
        assert result == []


# =====================================================================
# TestExtractTopLevelImports
# =====================================================================


class TestExtractTopLevelImports:
    """Tests for extract_top_level_imports."""

    def test_standard_imports(self, tmp_path: Path):
        py = tmp_path / "example.py"
        py.write_text("import os\nimport json\nimport requests\n")
        result = extract_top_level_imports(py)
        assert result == {"os", "json", "requests"}

    def test_from_imports(self, tmp_path: Path):
        py = tmp_path / "example.py"
        py.write_text("from pathlib import Path\nfrom flask.views import View\n")
        result = extract_top_level_imports(py)
        assert result == {"pathlib", "flask"}

    def test_relative_imports_excluded(self, tmp_path: Path):
        py = tmp_path / "example.py"
        py.write_text("from . import sibling\nfrom ..parent import mod\nimport os\n")
        result = extract_top_level_imports(py)
        assert result == {"os"}

    def test_syntax_error(self, tmp_path: Path):
        py = tmp_path / "bad.py"
        py.write_text("import os\ndef broken(\n")
        result = extract_top_level_imports(py)
        assert result == set()

    def test_missing_file(self, tmp_path: Path):
        missing = tmp_path / "nope.py"
        result = extract_top_level_imports(missing)
        assert result == set()


# =====================================================================
# TestScanTaskDescriptionPackages
# =====================================================================


class TestScanTaskDescriptionPackages:
    """Tests for scan_task_description_packages."""

    def test_finds_packages(self):
        desc = "Build a REST API with flask and use requests for HTTP calls"
        result = scan_task_description_packages(desc)
        assert "flask" in result
        assert "requests" in result

    def test_word_boundary(self):
        desc = "Use torchvision for image processing"
        result = scan_task_description_packages(desc)
        # "torch" should NOT match because "torchvision" != "torch"
        assert "torch" not in result

    def test_case_insensitive(self):
        desc = "Install Flask and use NumPy for computation"
        result = scan_task_description_packages(desc)
        assert "flask" in result
        assert "numpy" in result

    def test_empty_description(self):
        result = scan_task_description_packages("")
        assert result == set()

    def test_returns_import_names(self):
        desc = "Use scikit-learn for ML and pillow for image processing"
        result = scan_task_description_packages(desc)
        assert "sklearn" in result
        assert "PIL" in result
        # Should NOT contain PyPI names
        assert "scikit-learn" not in result
        assert "pillow" not in result


# =====================================================================
# TestAvailableDepsSource
# =====================================================================


class TestAvailableDepsSource:
    """Tests for AvailableDeps source and confidence."""

    def test_default_source(self):
        deps = AvailableDeps()
        assert deps.source == "stdlib_only"
        assert deps.confidence == 0.2

    def test_confidence_mapping(self):
        for source, expected in [
            ("pyproject", 1.0),
            ("requirements_txt", 0.85),
            ("setup_cfg", 0.85),
            ("venv_only", 0.5),
            ("stdlib_only", 0.2),
        ]:
            deps = AvailableDeps(source=source)
            assert deps.confidence == expected, f"source={source}"

    def test_to_dict_includes_new_fields(self):
        deps = AvailableDeps(
            source="pyproject",
            blessed_imports={"os", "json"},
            hinted_packages={"flask"},
        )
        d = deps.to_dict()
        assert d["source"] == "pyproject"
        assert d["confidence"] == 1.0
        assert d["blessed_imports"] == ["json", "os"]
        assert d["hinted_packages"] == ["flask"]

    def test_blessed_in_all_importable(self):
        deps = AvailableDeps(
            blessed_imports={"custom_pkg"},
        )
        assert "custom_pkg" in deps.all_importable

    def test_hinted_in_all_importable(self):
        deps = AvailableDeps(
            hinted_packages={"flask"},
        )
        assert "flask" in deps.all_importable


# =====================================================================
# TestDepsAvailableConfidence
# =====================================================================


class TestDepsAvailableConfidence:
    """Tests for confidence in _validate_deps_available issue dicts."""

    def test_issue_includes_confidence(self):
        from startd8.workflows.builtin.preflight_rules.rules_validators import (
            _validate_deps_available,
        )

        class FakeEnrichment:
            prompt_constraints = ["Only import from: os, sys"]
            deps_source = "stdlib_only"

        code = "import flask\n"
        issues = _validate_deps_available(code, FakeEnrichment())
        assert len(issues) == 1
        assert issues[0]["confidence"] == 0.2

    def test_high_confidence_with_pyproject(self):
        from startd8.workflows.builtin.preflight_rules.rules_validators import (
            _validate_deps_available,
        )

        class FakeEnrichment:
            prompt_constraints = ["Only import from: os, sys"]
            deps_source = "pyproject"

        code = "import flask\n"
        issues = _validate_deps_available(code, FakeEnrichment())
        assert len(issues) == 1
        assert issues[0]["confidence"] == 1.0

    def test_no_deps_source_defaults_high(self):
        from startd8.workflows.builtin.preflight_rules.rules_validators import (
            _validate_deps_available,
        )

        class FakeEnrichment:
            prompt_constraints = ["Only import from: os, sys"]

        code = "import flask\n"
        issues = _validate_deps_available(code, FakeEnrichment())
        assert len(issues) == 1
        # No deps_source → backward-compatible default of 1.0
        assert issues[0]["confidence"] == 1.0
