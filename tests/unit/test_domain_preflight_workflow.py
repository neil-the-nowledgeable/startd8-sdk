"""
Tests for the DomainPreflightWorkflow.

Covers models, scanning, classification, environment checks,
enrichment, and end-to-end execution.
"""

import json
import os
import textwrap
from pathlib import Path

import pytest

from startd8.workflows.builtin.domain_preflight_models import (
    AvailableDeps,
    CheckStatus,
    DomainClassification,
    EnvironmentCheck,
    PreflightState,
    TaskDomain,
    TaskEnrichment,
)
from startd8.workflows.builtin.domain_preflight_workflow import (
    DomainPreflightWorkflow,
    _normalize_dep_name,
    _parse_relative_imports,
    _file_has_pattern,
    _scan_optional_dep_guards,
    _scan_patch_paths,
    _STANDALONE_SCRIPT_DIRS,
    _LOGGER_RESERVED_FIELDS,
)


# ===================================================================
# Model tests
# ===================================================================


class TestTaskDomainEnum:
    """All 8 TaskDomain values exist and have correct string values."""

    def test_all_values_exist(self):
        assert len(TaskDomain) == 8

    def test_python_single_module(self):
        assert TaskDomain.PYTHON_SINGLE_MODULE.value == "python-single-module"

    def test_python_package_module(self):
        assert TaskDomain.PYTHON_PACKAGE_MODULE.value == "python-package-module"

    def test_python_test(self):
        assert TaskDomain.PYTHON_TEST.value == "python-test"

    def test_config_toml(self):
        assert TaskDomain.CONFIG_TOML.value == "config-toml"

    def test_config_yaml(self):
        assert TaskDomain.CONFIG_YAML.value == "config-yaml"

    def test_config_json(self):
        assert TaskDomain.CONFIG_JSON.value == "config-json"

    def test_non_python(self):
        assert TaskDomain.NON_PYTHON.value == "non-python"

    def test_unknown(self):
        assert TaskDomain.UNKNOWN.value == "unknown"


class TestCheckStatusEnum:
    def test_all_values(self):
        assert CheckStatus.PASS.value == "pass"
        assert CheckStatus.WARN.value == "warn"
        assert CheckStatus.FAIL.value == "fail"
        assert CheckStatus.SKIP.value == "skip"


class TestAvailableDeps:
    def test_all_importable_is_union(self):
        deps = AvailableDeps(
            runtime={"httpx", "pydantic"},
            optional={"dev": {"pytest", "black"}},
            stdlib={"os", "sys"},
            project={"startd8"},
        )
        all_imp = deps.all_importable
        assert all_imp == {"httpx", "pydantic", "pytest", "black", "os", "sys", "startd8"}

    def test_empty_deps(self):
        deps = AvailableDeps()
        assert deps.all_importable == set()

    def test_to_dict(self):
        deps = AvailableDeps(
            runtime={"rich"},
            stdlib={"os"},
            project={"startd8"},
        )
        d = deps.to_dict()
        assert d["runtime"] == ["rich"]
        assert d["stdlib"] == ["os"]
        assert d["project"] == ["startd8"]
        assert d["installed"] == []
        assert d["all_importable_count"] == 3

    def test_to_dict_with_installed(self):
        deps = AvailableDeps(
            runtime={"rich"},
            stdlib={"os"},
            project={"startd8"},
            installed={"boto3", "requests"},
        )
        d = deps.to_dict()
        assert d["installed"] == ["boto3", "requests"]
        assert d["all_importable_count"] == 5


class TestPreflightState:
    def test_to_dict_roundtrip(self):
        state = PreflightState(
            current_phase="classify",
            seed_path="/tmp/seed.json",
            project_root="/tmp/project",
            task_count=5,
            enriched_count=3,
            check_summary={"pass": 10, "warn": 2, "fail": 1, "skip": 0},
        )
        d = state.to_dict()
        assert d["current_phase"] == "classify"
        assert d["task_count"] == 5
        assert d["check_summary"]["pass"] == 10

    def test_default_state(self):
        state = PreflightState()
        d = state.to_dict()
        assert d["current_phase"] == "load"
        assert d["error"] is None


class TestTaskEnrichment:
    def test_to_dict(self):
        enrichment = TaskEnrichment(
            task_id="PI-001",
            domain=TaskDomain.PYTHON_SINGLE_MODULE,
            domain_reasoning="Single module",
            prompt_constraints=["No relative imports"],
            post_generation_validators=["no_relative_imports"],
            available_siblings=["base", "utils"],
            existing_content_hash="abc123",
        )
        d = enrichment.to_dict()
        assert d["task_id"] == "PI-001"
        assert d["domain"] == "python-single-module"
        assert len(d["prompt_constraints"]) == 1
        assert d["existing_content_hash"] == "abc123"


class TestEnvironmentCheck:
    def test_to_dict_with_detail(self):
        check = EnvironmentCheck(
            check_name="parent_dir_exists",
            status=CheckStatus.PASS,
            message="Directory exists",
            detail="/some/path",
        )
        d = check.to_dict()
        assert d["status"] == "pass"
        assert d["detail"] == "/some/path"

    def test_to_dict_without_detail(self):
        check = EnvironmentCheck(
            check_name="test",
            status=CheckStatus.FAIL,
            message="Failed",
        )
        d = check.to_dict()
        assert "detail" not in d


class TestDomainClassification:
    def test_to_dict(self):
        cls = DomainClassification(
            task_id="PI-001",
            target_file="src/foo.py",
            domain=TaskDomain.PYTHON_SINGLE_MODULE,
            reasoning="Single module",
        )
        d = cls.to_dict()
        assert d["domain"] == "python-single-module"


# ===================================================================
# Utility tests
# ===================================================================


class TestNormalizeDepName:
    def test_basic(self):
        assert _normalize_dep_name("httpx") == "httpx"

    def test_strip_version(self):
        assert _normalize_dep_name("httpx>=0.25.0") == "httpx"

    def test_strip_extras(self):
        assert _normalize_dep_name("pydantic[email]>=2.0") == "pydantic"

    def test_dash_to_underscore(self):
        assert _normalize_dep_name("google-genai>=1.0") == "google_genai"

    def test_uppercase(self):
        assert _normalize_dep_name("PyYAML>=6.0") == "pyyaml"


# ===================================================================
# Helper function tests
# ===================================================================


class TestParseRelativeImports:
    def test_finds_relative_imports(self, tmp_path):
        f = tmp_path / "module.py"
        f.write_text("from .base import BaseClass\nfrom .utils import helper\nimport os\n")
        result = _parse_relative_imports(f)
        assert result == ["base", "utils"]

    def test_empty_on_no_relative_imports(self, tmp_path):
        f = tmp_path / "module.py"
        f.write_text("import os\nfrom pathlib import Path\n")
        assert _parse_relative_imports(f) == []

    def test_empty_on_missing_file(self, tmp_path):
        assert _parse_relative_imports(tmp_path / "nonexistent.py") == []


class TestFileHasPattern:
    def test_finds_pattern(self, tmp_path):
        f = tmp_path / "module.py"
        f.write_text("import threading\nclass Worker(threading.Thread): pass\n")
        assert _file_has_pattern(f, r"\bthreading\b") is True

    def test_no_match(self, tmp_path):
        f = tmp_path / "module.py"
        f.write_text("import os\n")
        assert _file_has_pattern(f, r"\bthreading\b") is False

    def test_missing_file(self, tmp_path):
        assert _file_has_pattern(tmp_path / "nonexistent.py", r"\bfoo\b") is False


class TestScanOptionalDepGuards:
    def test_finds_guarded_imports(self, tmp_path):
        f = tmp_path / "module.py"
        f.write_text(textwrap.dedent("""\
            try:
                import tiktoken
            except ImportError:
                tiktoken = None

            try:
                from opentelemetry import trace
            except ImportError:
                trace = None
        """))
        result = _scan_optional_dep_guards(f)
        assert "tiktoken" in result
        assert "opentelemetry" in result

    def test_empty_on_no_guards(self, tmp_path):
        f = tmp_path / "module.py"
        f.write_text("import os\nimport sys\n")
        assert _scan_optional_dep_guards(f) == []

    def test_empty_on_missing_file(self, tmp_path):
        assert _scan_optional_dep_guards(tmp_path / "nonexistent.py") == []


class TestScanPatchPaths:
    def test_finds_patch_decorators(self, tmp_path):
        f = tmp_path / "test_foo.py"
        f.write_text(textwrap.dedent("""\
            from unittest.mock import patch

            @patch("myapp.models.SomeClass.method")
            def test_something(mock_method):
                pass

            @patch("myapp.utils.helper")
            def test_other(mock_helper):
                pass
        """))
        result = _scan_patch_paths(f)
        assert "myapp.models.SomeClass.method" in result
        assert "myapp.utils.helper" in result

    def test_finds_mock_patch_call(self, tmp_path):
        f = tmp_path / "test_foo.py"
        f.write_text(textwrap.dedent("""\
            from unittest import mock

            def test_it():
                with mock.patch("myapp.service.run") as m:
                    pass
        """))
        result = _scan_patch_paths(f)
        assert "myapp.service.run" in result

    def test_empty_on_missing_file(self, tmp_path):
        assert _scan_patch_paths(tmp_path / "nonexistent.py") == []


class TestStandaloneScriptDirs:
    def test_known_dirs(self):
        assert "scripts" in _STANDALONE_SCRIPT_DIRS
        assert "bin" in _STANDALONE_SCRIPT_DIRS
        assert "tools" in _STANDALONE_SCRIPT_DIRS
        assert "examples" in _STANDALONE_SCRIPT_DIRS

    def test_src_not_included(self):
        assert "src" not in _STANDALONE_SCRIPT_DIRS


class TestLoggerReservedFields:
    def test_common_fields_present(self):
        assert "name" in _LOGGER_RESERVED_FIELDS
        assert "message" in _LOGGER_RESERVED_FIELDS
        assert "levelname" in _LOGGER_RESERVED_FIELDS
        assert "funcName" in _LOGGER_RESERVED_FIELDS


# ===================================================================
# Scan tests
# ===================================================================


class TestScanAvailableDeps:
    def test_scan_with_pyproject(self, tmp_path):
        """Mock pyproject.toml with deps, verify parsing."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(textwrap.dedent("""\
            [project]
            dependencies = [
                "rich>=13.0.0",
                "httpx>=0.25.0",
            ]

            [project.optional-dependencies]
            dev = ["pytest>=7.0.0"]
        """))

        # Create src/mypackage/__init__.py
        pkg_dir = tmp_path / "src" / "mypackage"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "__init__.py").touch()

        deps = DomainPreflightWorkflow._scan_available_deps(tmp_path)

        assert "rich" in deps.runtime
        assert "httpx" in deps.runtime
        assert "pytest" in deps.optional.get("dev", set())
        assert "mypackage" in deps.project
        assert len(deps.stdlib) > 50  # Should have stdlib modules

        # all_importable includes everything
        all_imp = deps.all_importable
        assert "rich" in all_imp
        assert "httpx" in all_imp
        assert "pytest" in all_imp
        assert "mypackage" in all_imp
        assert "os" in all_imp

    def test_scan_missing_pyproject(self, tmp_path):
        """Graceful fallback when pyproject.toml is missing."""
        deps = DomainPreflightWorkflow._scan_available_deps(tmp_path)
        assert len(deps.runtime) == 0
        assert len(deps.stdlib) > 50  # Still has stdlib


class TestVenvScanning:
    """Tests for .venv site-packages scanning in _scan_available_deps."""

    def test_scan_venv_packages(self, tmp_path):
        """Fake .venv with package dirs populates deps.installed."""
        site_pkgs = tmp_path / ".venv" / "lib" / "python3.11" / "site-packages"
        site_pkgs.mkdir(parents=True)

        # Create package directories
        (site_pkgs / "requests").mkdir()
        (site_pkgs / "requests" / "__init__.py").touch()
        (site_pkgs / "flask").mkdir()
        (site_pkgs / "flask" / "__init__.py").touch()
        (site_pkgs / "click").mkdir()
        (site_pkgs / "click" / "__init__.py").touch()

        deps = DomainPreflightWorkflow._scan_available_deps(tmp_path)

        assert "requests" in deps.installed
        assert "flask" in deps.installed
        assert "click" in deps.installed

    def test_scan_skips_dist_info(self, tmp_path):
        """Metadata directories (.dist-info, .egg-info) are excluded."""
        site_pkgs = tmp_path / ".venv" / "lib" / "python3.11" / "site-packages"
        site_pkgs.mkdir(parents=True)

        # Create metadata dirs that should be skipped
        (site_pkgs / "requests-2.31.0.dist-info").mkdir()
        (site_pkgs / "flask-3.0.0.dist-info").mkdir()
        (site_pkgs / "setuptools-69.0.0.egg-info").mkdir()
        # Create internal dirs that should be skipped
        (site_pkgs / "_distutils_hack").mkdir()
        (site_pkgs / "__pycache__").mkdir()
        # Create .pth files that should be skipped
        (site_pkgs / "easy_install.pth").touch()
        (site_pkgs / "distutils-precedence.pth").touch()
        # Create .py files that should be skipped
        (site_pkgs / "_virtualenv.py").touch()

        # Create one real package for contrast
        (site_pkgs / "requests").mkdir()
        (site_pkgs / "requests" / "__init__.py").touch()

        deps = DomainPreflightWorkflow._scan_available_deps(tmp_path)

        assert "requests" in deps.installed
        assert not any("dist-info" in name for name in deps.installed)
        assert not any("egg-info" in name for name in deps.installed)
        assert "_distutils_hack" not in deps.installed
        assert "__pycache__" not in deps.installed

    def test_scan_no_venv(self, tmp_path):
        """When no .venv exists, installed is empty."""
        deps = DomainPreflightWorkflow._scan_available_deps(tmp_path)
        assert deps.installed == set()

    def test_installed_in_all_importable(self, tmp_path):
        """Installed packages appear in all_importable."""
        site_pkgs = tmp_path / ".venv" / "lib" / "python3.11" / "site-packages"
        site_pkgs.mkdir(parents=True)

        (site_pkgs / "boto3").mkdir()
        (site_pkgs / "boto3" / "__init__.py").touch()

        deps = DomainPreflightWorkflow._scan_available_deps(tmp_path)

        assert "boto3" in deps.installed
        assert "boto3" in deps.all_importable

    def test_scan_extension_modules(self, tmp_path):
        """Single-file .so/.pyd extension modules are detected."""
        site_pkgs = tmp_path / ".venv" / "lib" / "python3.11" / "site-packages"
        site_pkgs.mkdir(parents=True)

        # Simulate compiled extension modules
        (site_pkgs / "_yaml.cpython-311-darwin.so").touch()
        (site_pkgs / "myext.pyd").touch()

        deps = DomainPreflightWorkflow._scan_available_deps(tmp_path)

        # .so files: stem is checked, but suffix must be exactly .so
        # _yaml.cpython-311-darwin.so has stem starting with _, so it's skipped
        assert "myext" in deps.installed

    def test_scan_namespace_packages(self, tmp_path):
        """Dirs without __init__.py (namespace packages) are included."""
        site_pkgs = tmp_path / ".venv" / "lib" / "python3.11" / "site-packages"
        site_pkgs.mkdir(parents=True)

        # Namespace package (no __init__.py)
        ns_pkg = site_pkgs / "google"
        ns_pkg.mkdir()
        (ns_pkg / "cloud").mkdir()

        deps = DomainPreflightWorkflow._scan_available_deps(tmp_path)

        assert "google" in deps.installed


# ===================================================================
# Classification tests
# ===================================================================


class TestClassifyDomain:
    def test_python_single_module(self, tmp_path):
        """Single .py file in a non-package directory."""
        target = "src/utils.py"
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "utils.py").touch()

        result = DomainPreflightWorkflow._classify_domain(target, tmp_path)
        assert result.domain == TaskDomain.PYTHON_SINGLE_MODULE

    def test_python_package_module(self, tmp_path):
        """Python file in a directory with __init__.py."""
        pkg_dir = tmp_path / "src" / "mypackage"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "__init__.py").touch()
        (pkg_dir / "models.py").touch()
        (pkg_dir / "utils.py").touch()

        result = DomainPreflightWorkflow._classify_domain(
            "src/mypackage/models.py", tmp_path,
        )
        assert result.domain == TaskDomain.PYTHON_PACKAGE_MODULE

    def test_python_test_by_name(self, tmp_path):
        """File starting with test_ is a test."""
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_models.py").touch()

        result = DomainPreflightWorkflow._classify_domain(
            "tests/test_models.py", tmp_path,
        )
        assert result.domain == TaskDomain.PYTHON_TEST

    def test_python_test_by_path(self, tmp_path):
        """File in a 'test' directory is a test."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "helpers.py").touch()

        result = DomainPreflightWorkflow._classify_domain(
            "test/helpers.py", tmp_path,
        )
        assert result.domain == TaskDomain.PYTHON_TEST

    def test_config_toml(self, tmp_path):
        result = DomainPreflightWorkflow._classify_domain("pyproject.toml", tmp_path)
        assert result.domain == TaskDomain.CONFIG_TOML

    def test_config_yaml(self, tmp_path):
        result = DomainPreflightWorkflow._classify_domain("config.yaml", tmp_path)
        assert result.domain == TaskDomain.CONFIG_YAML

    def test_config_yml(self, tmp_path):
        result = DomainPreflightWorkflow._classify_domain("config.yml", tmp_path)
        assert result.domain == TaskDomain.CONFIG_YAML

    def test_config_json(self, tmp_path):
        result = DomainPreflightWorkflow._classify_domain("data.json", tmp_path)
        assert result.domain == TaskDomain.CONFIG_JSON

    def test_non_python(self, tmp_path):
        result = DomainPreflightWorkflow._classify_domain("README.md", tmp_path)
        assert result.domain == TaskDomain.NON_PYTHON

    def test_unknown_no_extension(self, tmp_path):
        result = DomainPreflightWorkflow._classify_domain("Makefile", tmp_path)
        assert result.domain == TaskDomain.UNKNOWN

    def test_scripts_dir_is_single_module(self, tmp_path):
        """Files in scripts/ with many siblings but no __init__.py → single module."""
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "run_pipeline.py").touch()
        (scripts_dir / "setup_data.py").touch()
        (scripts_dir / "validate.py").touch()
        # No __init__.py

        result = DomainPreflightWorkflow._classify_domain(
            "scripts/run_pipeline.py", tmp_path,
        )
        assert result.domain == TaskDomain.PYTHON_SINGLE_MODULE
        assert "standalone script" in result.reasoning.lower()

    def test_scripts_dir_with_init_is_package(self, tmp_path):
        """If scripts/ has __init__.py, treat as package module."""
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "__init__.py").touch()
        (scripts_dir / "run_pipeline.py").touch()
        (scripts_dir / "setup_data.py").touch()

        result = DomainPreflightWorkflow._classify_domain(
            "scripts/run_pipeline.py", tmp_path,
        )
        assert result.domain == TaskDomain.PYTHON_PACKAGE_MODULE

    def test_examples_dir_is_single_module(self, tmp_path):
        """Examples dir also treated as standalone scripts."""
        examples_dir = tmp_path / "examples"
        examples_dir.mkdir()
        (examples_dir / "demo1.py").touch()
        (examples_dir / "demo2.py").touch()
        (examples_dir / "demo3.py").touch()

        result = DomainPreflightWorkflow._classify_domain(
            "examples/demo1.py", tmp_path,
        )
        assert result.domain == TaskDomain.PYTHON_SINGLE_MODULE

    def test_tools_dir_is_single_module(self, tmp_path):
        """Tools dir also treated as standalone scripts."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        (tools_dir / "lint.py").touch()
        (tools_dir / "format.py").touch()
        (tools_dir / "check.py").touch()

        result = DomainPreflightWorkflow._classify_domain(
            "tools/lint.py", tmp_path,
        )
        assert result.domain == TaskDomain.PYTHON_SINGLE_MODULE


# ===================================================================
# Environment check tests
# ===================================================================


class TestRunEnvironmentChecks:
    def _make_deps(self):
        return AvailableDeps(
            runtime={"rich", "httpx"},
            stdlib={"os", "sys"},
            project={"startd8"},
        )

    def test_parent_dir_exists(self, tmp_path):
        """All domains check for parent directory."""
        target_dir = tmp_path / "src"
        target_dir.mkdir()
        (target_dir / "foo.py").touch()

        checks = DomainPreflightWorkflow._run_environment_checks(
            TaskDomain.PYTHON_SINGLE_MODULE, "src/foo.py",
            tmp_path, self._make_deps(),
        )
        parent_check = next(c for c in checks if c.check_name == "parent_dir_exists")
        assert parent_check.status == CheckStatus.PASS

    def test_parent_dir_missing(self, tmp_path):
        checks = DomainPreflightWorkflow._run_environment_checks(
            TaskDomain.PYTHON_SINGLE_MODULE, "nonexistent/foo.py",
            tmp_path, self._make_deps(),
        )
        parent_check = next(c for c in checks if c.check_name == "parent_dir_exists")
        assert parent_check.status == CheckStatus.WARN

    def test_single_module_not_in_package(self, tmp_path):
        """Single module: verify not inside a package."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "foo.py").touch()

        checks = DomainPreflightWorkflow._run_environment_checks(
            TaskDomain.PYTHON_SINGLE_MODULE, "src/foo.py",
            tmp_path, self._make_deps(),
        )
        pkg_check = next(c for c in checks if c.check_name == "not_in_package")
        assert pkg_check.status == CheckStatus.PASS

    def test_single_module_in_package_warns(self, tmp_path):
        """Single module classified but dir has __init__.py → warn."""
        pkg_dir = tmp_path / "src"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").touch()
        (pkg_dir / "foo.py").touch()

        checks = DomainPreflightWorkflow._run_environment_checks(
            TaskDomain.PYTHON_SINGLE_MODULE, "src/foo.py",
            tmp_path, self._make_deps(),
        )
        pkg_check = next(c for c in checks if c.check_name == "not_in_package")
        assert pkg_check.status == CheckStatus.WARN

    def test_package_module_init_exists(self, tmp_path):
        pkg_dir = tmp_path / "src" / "pkg"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "__init__.py").touch()
        (pkg_dir / "module.py").touch()
        # Parent also needs __init__.py
        (tmp_path / "src" / "__init__.py").touch()

        checks = DomainPreflightWorkflow._run_environment_checks(
            TaskDomain.PYTHON_PACKAGE_MODULE, "src/pkg/module.py",
            tmp_path, self._make_deps(),
        )
        init_check = next(c for c in checks if c.check_name == "init_py_exists")
        assert init_check.status == CheckStatus.PASS

    def test_package_module_init_missing(self, tmp_path):
        pkg_dir = tmp_path / "src" / "pkg"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "module.py").touch()

        checks = DomainPreflightWorkflow._run_environment_checks(
            TaskDomain.PYTHON_PACKAGE_MODULE, "src/pkg/module.py",
            tmp_path, self._make_deps(),
        )
        init_check = next(c for c in checks if c.check_name == "init_py_exists")
        assert init_check.status == CheckStatus.FAIL

    def test_python_test_source_exists(self, tmp_path):
        # Create source module
        src_dir = tmp_path / "src" / "mylib"
        src_dir.mkdir(parents=True)
        (src_dir / "__init__.py").touch()
        (src_dir / "models.py").touch()

        # Create test dir
        test_dir = tmp_path / "tests"
        test_dir.mkdir()

        checks = DomainPreflightWorkflow._run_environment_checks(
            TaskDomain.PYTHON_TEST, "tests/test_models.py",
            tmp_path, self._make_deps(),
        )
        source_check = next(c for c in checks if c.check_name == "source_module_exists")
        assert source_check.status == CheckStatus.PASS

    def test_config_json_valid(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"key": "value"}')

        checks = DomainPreflightWorkflow._run_environment_checks(
            TaskDomain.CONFIG_JSON, "config.json",
            tmp_path, self._make_deps(),
        )
        exists_check = next(c for c in checks if c.check_name == "config_file_exists")
        assert exists_check.status == CheckStatus.PASS
        format_check = next(c for c in checks if c.check_name == "config_format_valid")
        assert format_check.status == CheckStatus.PASS

    def test_circular_import_detection(self, tmp_path):
        """Detect circular relative imports between siblings."""
        pkg_dir = tmp_path / "src" / "pkg"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "__init__.py").touch()
        # module_a imports from .module_b AND module_b imports from .module_a
        (pkg_dir / "module_a.py").write_text("from .module_b import foo\n")
        (pkg_dir / "module_b.py").write_text("from .module_a import bar\n")
        (tmp_path / "src" / "__init__.py").touch()

        checks = DomainPreflightWorkflow._run_environment_checks(
            TaskDomain.PYTHON_PACKAGE_MODULE, "src/pkg/module_a.py",
            tmp_path, self._make_deps(),
        )
        circ_checks = [c for c in checks if c.check_name == "circular_imports"]
        assert len(circ_checks) == 1
        assert circ_checks[0].status == CheckStatus.WARN
        assert "module_b" in circ_checks[0].message

    def test_no_circular_import_when_one_way(self, tmp_path):
        """One-way relative import is not circular."""
        pkg_dir = tmp_path / "src" / "pkg"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "__init__.py").touch()
        (pkg_dir / "module_a.py").write_text("from .module_b import foo\n")
        (pkg_dir / "module_b.py").write_text("import os\n")
        (tmp_path / "src" / "__init__.py").touch()

        checks = DomainPreflightWorkflow._run_environment_checks(
            TaskDomain.PYTHON_PACKAGE_MODULE, "src/pkg/module_a.py",
            tmp_path, self._make_deps(),
        )
        circ_checks = [c for c in checks if c.check_name == "circular_imports"]
        assert len(circ_checks) == 0

    def test_optional_dep_guard_detection(self, tmp_path):
        """Detect optional imports not in project deps."""
        (tmp_path / "src").mkdir()
        target = tmp_path / "src" / "module.py"
        target.write_text(textwrap.dedent("""\
            try:
                import tiktoken
            except ImportError:
                tiktoken = None
        """))

        deps = self._make_deps()
        checks = DomainPreflightWorkflow._run_environment_checks(
            TaskDomain.PYTHON_SINGLE_MODULE, "src/module.py",
            tmp_path, deps,
        )
        guard_checks = [c for c in checks if c.check_name == "optional_dep_guards"]
        assert len(guard_checks) == 1
        assert guard_checks[0].status == CheckStatus.WARN
        assert "tiktoken" in guard_checks[0].message

    def test_patch_path_validation(self, tmp_path):
        """Detect stale mock.patch targets."""
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        test_file = test_dir / "test_foo.py"
        test_file.write_text(textwrap.dedent("""\
            from unittest.mock import patch

            @patch("nonexistent.module.SomeClass")
            def test_something(mock_cls):
                pass
        """))

        checks = DomainPreflightWorkflow._run_environment_checks(
            TaskDomain.PYTHON_TEST, "tests/test_foo.py",
            tmp_path, self._make_deps(),
        )
        patch_checks = [c for c in checks if c.check_name == "patch_path_valid"]
        assert len(patch_checks) == 1
        assert patch_checks[0].status == CheckStatus.WARN

    def test_thread_aware_teardown(self, tmp_path):
        """Detect when source module uses threading."""
        src_dir = tmp_path / "src" / "mylib"
        src_dir.mkdir(parents=True)
        (src_dir / "__init__.py").touch()
        (src_dir / "worker.py").write_text("import threading\nclass Worker(threading.Thread): pass\n")

        test_dir = tmp_path / "tests"
        test_dir.mkdir()

        checks = DomainPreflightWorkflow._run_environment_checks(
            TaskDomain.PYTHON_TEST, "tests/test_worker.py",
            tmp_path, self._make_deps(),
        )
        thread_checks = [c for c in checks if c.check_name == "thread_aware_teardown"]
        assert len(thread_checks) == 1
        assert thread_checks[0].status == CheckStatus.WARN
        assert "threading" in thread_checks[0].message

    def test_entry_point_reinstall(self, tmp_path):
        """pyproject.toml gets entry point reinstall warning."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")

        checks = DomainPreflightWorkflow._run_environment_checks(
            TaskDomain.CONFIG_TOML, "pyproject.toml",
            tmp_path, self._make_deps(),
        )
        ep_checks = [c for c in checks if c.check_name == "entry_point_reinstall"]
        assert len(ep_checks) == 1
        assert ep_checks[0].status == CheckStatus.WARN
        assert "pip install" in ep_checks[0].message

    def test_logger_reserved_fields_check(self, tmp_path):
        """Python files using logging get reserved field constraint."""
        (tmp_path / "src").mkdir()
        target = tmp_path / "src" / "module.py"
        target.write_text("import logging\nlogger = logging.getLogger(__name__)\n")

        checks = DomainPreflightWorkflow._run_environment_checks(
            TaskDomain.PYTHON_SINGLE_MODULE, "src/module.py",
            tmp_path, self._make_deps(),
        )
        logger_checks = [c for c in checks if c.check_name == "logger_reserved_fields"]
        assert len(logger_checks) == 1
        assert logger_checks[0].status == CheckStatus.PASS


# ===================================================================
# Enrichment tests
# ===================================================================


class TestBuildEnrichment:
    def _make_deps(self):
        return AvailableDeps(
            runtime={"rich", "httpx"},
            stdlib={"os", "sys"},
            project={"startd8"},
        )

    def test_single_module_constraints(self, tmp_path):
        (tmp_path / "src").mkdir()
        enrichment = DomainPreflightWorkflow._build_enrichment(
            "PI-001", TaskDomain.PYTHON_SINGLE_MODULE,
            "Single module", "src/foo.py",
            tmp_path, self._make_deps(), [],
        )
        assert any("single Python module" in c for c in enrichment.prompt_constraints)
        assert any("relative imports" in c.lower() for c in enrichment.prompt_constraints)
        assert "no_relative_imports" in enrichment.post_generation_validators
        assert "deps_available" in enrichment.post_generation_validators
        assert "definition_ordering" in enrichment.post_generation_validators
        assert "no_markdown_fences" in enrichment.post_generation_validators

    def test_package_module_constraints(self, tmp_path):
        pkg_dir = tmp_path / "src" / "pkg"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "__init__.py").touch()
        (pkg_dir / "base.py").touch()
        (pkg_dir / "utils.py").touch()

        enrichment = DomainPreflightWorkflow._build_enrichment(
            "PI-002", TaskDomain.PYTHON_PACKAGE_MODULE,
            "Package module", "src/pkg/models.py",
            tmp_path, self._make_deps(), [],
        )
        assert any("pkg" in c for c in enrichment.prompt_constraints)
        assert "base" in enrichment.available_siblings
        assert "utils" in enrichment.available_siblings
        assert "relative_imports_valid" in enrichment.post_generation_validators
        assert "no_markdown_fences" in enrichment.post_generation_validators

    def test_package_module_pydantic_property_warning(self, tmp_path):
        """Sibling with @property triggers Pydantic confusion constraint."""
        pkg_dir = tmp_path / "src" / "pkg"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "__init__.py").touch()
        (pkg_dir / "base.py").write_text("class Base:\n    @property\n    def name(self): return self._name\n")
        (pkg_dir / "utils.py").touch()

        enrichment = DomainPreflightWorkflow._build_enrichment(
            "PI-002b", TaskDomain.PYTHON_PACKAGE_MODULE,
            "Package module", "src/pkg/models.py",
            tmp_path, self._make_deps(), [],
        )
        assert any("@property" in c and "Pydantic" in c for c in enrichment.prompt_constraints)

    def test_test_constraints(self, tmp_path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()

        enrichment = DomainPreflightWorkflow._build_enrichment(
            "PI-003", TaskDomain.PYTHON_TEST,
            "Test file", "tests/test_models.py",
            tmp_path, self._make_deps(), [],
        )
        assert any("pytest" in c.lower() for c in enrichment.prompt_constraints)
        assert any("==" in c and "tag" in c.lower() for c in enrichment.prompt_constraints)
        assert "imports_resolve" in enrichment.post_generation_validators
        assert "test_naming" in enrichment.post_generation_validators
        assert "no_markdown_fences" in enrichment.post_generation_validators
        assert "no_substring_tag_matching" in enrichment.post_generation_validators

    def test_config_constraints(self, tmp_path):
        enrichment = DomainPreflightWorkflow._build_enrichment(
            "PI-004", TaskDomain.CONFIG_TOML,
            "Config file", "pyproject.toml",
            tmp_path, self._make_deps(), [],
        )
        assert any("Preserve" in c for c in enrichment.prompt_constraints)
        assert "valid_format" in enrichment.post_generation_validators

    def test_config_toml_entry_point_constraint(self, tmp_path):
        """pyproject.toml gets entry point reinstall constraint."""
        enrichment = DomainPreflightWorkflow._build_enrichment(
            "PI-004b", TaskDomain.CONFIG_TOML,
            "Config file", "pyproject.toml",
            tmp_path, self._make_deps(), [],
        )
        assert any("pip install" in c for c in enrichment.prompt_constraints)

    def test_logger_reserved_fields_constraint(self, tmp_path):
        """Python file using logging gets reserved field constraint."""
        (tmp_path / "src").mkdir()
        target = tmp_path / "src" / "foo.py"
        target.write_text("import logging\nlogger = logging.getLogger(__name__)\n")

        enrichment = DomainPreflightWorkflow._build_enrichment(
            "PI-LR", TaskDomain.PYTHON_SINGLE_MODULE,
            "Module with logging", "src/foo.py",
            tmp_path, self._make_deps(), [],
        )
        assert any("LogRecord" in c and "reserved" in c.lower() for c in enrichment.prompt_constraints)

    def test_optional_dep_guard_constraint(self, tmp_path):
        """File with try/except import gets guard preservation constraint."""
        (tmp_path / "src").mkdir()
        target = tmp_path / "src" / "foo.py"
        target.write_text(textwrap.dedent("""\
            try:
                import tiktoken
            except ImportError:
                tiktoken = None
        """))

        enrichment = DomainPreflightWorkflow._build_enrichment(
            "PI-OD", TaskDomain.PYTHON_SINGLE_MODULE,
            "Module with optional dep", "src/foo.py",
            tmp_path, self._make_deps(), [],
        )
        assert any("optional dependency" in c.lower() and "tiktoken" in c for c in enrichment.prompt_constraints)

    def test_test_thread_teardown_constraint(self, tmp_path):
        """Test file for threaded source gets teardown constraint."""
        src_dir = tmp_path / "src" / "mylib"
        src_dir.mkdir(parents=True)
        (src_dir / "__init__.py").touch()
        (src_dir / "worker.py").write_text("import threading\nclass Worker(threading.Thread): pass\n")

        test_dir = tmp_path / "tests"
        test_dir.mkdir()

        enrichment = DomainPreflightWorkflow._build_enrichment(
            "PI-TT", TaskDomain.PYTHON_TEST,
            "Test for threaded module", "tests/test_worker.py",
            tmp_path, self._make_deps(), [],
        )
        assert any("threading" in c and "teardown" in c.lower() for c in enrichment.prompt_constraints)

    def test_existing_content_hash(self, tmp_path):
        target = tmp_path / "src" / "foo.py"
        target.parent.mkdir(parents=True)
        target.write_text("print('hello')")

        enrichment = DomainPreflightWorkflow._build_enrichment(
            "PI-005", TaskDomain.PYTHON_SINGLE_MODULE,
            "Existing file", "src/foo.py",
            tmp_path, self._make_deps(), [],
        )
        assert enrichment.existing_content_hash is not None
        assert len(enrichment.existing_content_hash) == 16

    def test_no_hash_when_file_missing(self, tmp_path):
        enrichment = DomainPreflightWorkflow._build_enrichment(
            "PI-006", TaskDomain.PYTHON_SINGLE_MODULE,
            "New file", "src/new.py",
            tmp_path, self._make_deps(), [],
        )
        assert enrichment.existing_content_hash is None


# ===================================================================
# End-to-end tests
# ===================================================================


class TestEndToEndDomainPreflight:
    def _create_project(self, tmp_path):
        """Create a minimal project structure with context seed."""
        # pyproject.toml
        (tmp_path / "pyproject.toml").write_text(textwrap.dedent("""\
            [project]
            dependencies = [
                "rich>=13.0.0",
                "httpx>=0.25.0",
                "pydantic>=2.0.0",
            ]

            [project.optional-dependencies]
            dev = ["pytest>=7.0.0"]
        """))

        # Source tree
        pkg_dir = tmp_path / "src" / "myapp"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "__init__.py").touch()
        (pkg_dir / "models.py").write_text("class Model: pass")
        (pkg_dir / "utils.py").write_text("def helper(): pass")

        # Test directory
        test_dir = tmp_path / "tests" / "unit"
        test_dir.mkdir(parents=True)
        (test_dir / "conftest.py").write_text(textwrap.dedent("""\
            import pytest

            @pytest.fixture()
            def sample_data():
                return {"key": "value"}
        """))

        # Context seed
        seed = {
            "version": "1.0.0",
            "generated_at": "2026-02-10T00:00:00Z",
            "generator": "plan-ingestion",
            "plan": {"title": "Test Plan"},
            "tasks": [
                {
                    "task_id": "PI-001",
                    "title": "Create models",
                    "config": {
                        "task_description": "Create data models",
                        "context": {
                            "target_files": ["src/myapp/models.py"],
                            "estimated_loc": 100,
                        },
                    },
                },
                {
                    "task_id": "PI-002",
                    "title": "Create new module",
                    "config": {
                        "task_description": "Create a standalone module",
                        "context": {
                            "target_files": ["src/standalone.py"],
                            "estimated_loc": 50,
                        },
                    },
                },
                {
                    "task_id": "PI-003",
                    "title": "Create tests",
                    "config": {
                        "task_description": "Create unit tests",
                        "context": {
                            "target_files": ["tests/unit/test_models.py"],
                            "estimated_loc": 80,
                        },
                    },
                },
                {
                    "task_id": "PI-004",
                    "title": "Update config",
                    "config": {
                        "task_description": "Update pyproject.toml",
                        "context": {
                            "target_files": ["pyproject.toml"],
                            "estimated_loc": 10,
                        },
                    },
                },
                {
                    "task_id": "PI-005",
                    "title": "No target files",
                    "config": {
                        "task_description": "Task with no target files",
                        "context": {},
                    },
                },
            ],
        }

        seed_path = tmp_path / "artisan-context-seed.json"
        seed_path.write_text(json.dumps(seed, indent=2))
        return seed_path

    def test_full_workflow(self, tmp_path):
        """Run full workflow and verify enriched JSON output."""
        seed_path = self._create_project(tmp_path)
        wf = DomainPreflightWorkflow()

        result = wf.run({
            "context_seed_path": str(seed_path),
            "project_root": str(tmp_path),
        })

        assert result.success, f"Workflow failed: {result.error}"
        assert result.output is not None

        output = result.output
        assert output["task_count"] == 5
        assert "domain_summary" in output
        assert "check_summary" in output
        assert output["available_deps_count"] > 0

        # Verify enriched file was written
        enriched_path = Path(output["enriched_seed_path"])
        assert enriched_path.exists()

        with open(enriched_path) as f:
            enriched = json.load(f)

        # Check structure
        assert enriched["version"] == "1.0.0"
        assert "_preflight" in enriched
        assert enriched["_preflight"]["workflow_version"] == "1.2.0"
        assert "check_summary" in enriched["_preflight"]

        # Check tasks have _enrichment
        tasks = enriched["tasks"]
        assert len(tasks) == 5

        # PI-001: package module (dir has __init__.py)
        t1 = tasks[0]
        assert "_enrichment" in t1
        assert t1["_enrichment"]["domain"] == "python-package-module"

        # PI-002: single module (standalone.py, src/ has __init__.py via myapp)
        t2 = tasks[1]
        assert "_enrichment" in t2
        assert t2["_enrichment"]["domain"] == "python-single-module"

        # PI-003: test
        t3 = tasks[2]
        assert "_enrichment" in t3
        assert t3["_enrichment"]["domain"] == "python-test"

        # PI-004: config toml
        t4 = tasks[3]
        assert "_enrichment" in t4
        assert t4["_enrichment"]["domain"] == "config-toml"

        # PI-005: unknown (no target files)
        t5 = tasks[4]
        assert "_enrichment" in t5
        assert t5["_enrichment"]["domain"] == "unknown"

    def test_schema_version_1_0_accepted(self, tmp_path):
        """Item 15: schema_version '1.0' is accepted alongside version '1.0.0'."""
        seed = {"schema_version": "1.0", "version": "1.0.0", "tasks": []}
        seed_path = tmp_path / "seed.json"
        seed_path.write_text(json.dumps(seed))
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "__init__.py").touch()
        (tmp_path / "src" / "foo.py").write_text("# foo")

        wf = DomainPreflightWorkflow()
        result = wf.run({
            "context_seed_path": str(seed_path),
            "project_root": str(tmp_path),
        })
        assert result.success

    def test_invalid_version_fails(self, tmp_path):
        seed = {"version": "2.0.0", "tasks": []}
        seed_path = tmp_path / "seed.json"
        seed_path.write_text(json.dumps(seed))

        wf = DomainPreflightWorkflow()
        result = wf.run({
            "context_seed_path": str(seed_path),
            "project_root": str(tmp_path),
        })
        assert not result.success
        assert "version" in result.error.lower()

    def test_missing_tasks_fails(self, tmp_path):
        seed = {"version": "1.0.0"}
        seed_path = tmp_path / "seed.json"
        seed_path.write_text(json.dumps(seed))

        wf = DomainPreflightWorkflow()
        result = wf.run({
            "context_seed_path": str(seed_path),
            "project_root": str(tmp_path),
        })
        assert not result.success
        assert "tasks" in result.error.lower()

    def test_validation_rejects_missing_seed(self):
        wf = DomainPreflightWorkflow()
        result = wf.validate_config({})
        assert not result.valid
        assert any("context_seed_path" in e for e in result.errors)

    def test_validation_rejects_nonexistent_file(self, tmp_path):
        wf = DomainPreflightWorkflow()
        result = wf.validate_config({
            "context_seed_path": str(tmp_path / "nonexistent.json"),
        })
        assert not result.valid

    def test_metadata(self):
        wf = DomainPreflightWorkflow()
        meta = wf.metadata
        assert meta.workflow_id == "domain-preflight"
        assert meta.requires_agents is False
        assert meta.version == "1.2.0"

    def test_progress_callback(self, tmp_path):
        """Progress callback is called for each phase."""
        seed_path = self._create_project(tmp_path)
        wf = DomainPreflightWorkflow()

        progress_calls = []

        def on_progress(current, total, message):
            progress_calls.append((current, total, message))

        result = wf.run(
            {
                "context_seed_path": str(seed_path),
                "project_root": str(tmp_path),
            },
            on_progress=on_progress,
        )

        assert result.success
        assert len(progress_calls) == 5
        assert progress_calls[0][2] == "Loading context seed"
        assert progress_calls[-1][2] == "Writing enriched seed"

    def test_steps_recorded(self, tmp_path):
        """Verify step results are populated."""
        seed_path = self._create_project(tmp_path)
        wf = DomainPreflightWorkflow()

        result = wf.run({
            "context_seed_path": str(seed_path),
            "project_root": str(tmp_path),
        })

        assert result.success
        step_names = [s.step_name for s in result.steps]
        assert "load" in step_names
        assert "scan" in step_names
        assert "classify_check_enrich" in step_names
        assert "enrich" in step_names


# ===================================================================
# Multi-file risk checks (Layer A defense-in-depth)
# ===================================================================


class TestMultiFileChecks:
    """Tests for DomainPreflightWorkflow._multi_file_checks.

    Layer A detection: fires at seed-enrichment time (before any LLM
    calls) to surface multi-file generation risks in preflight reports.
    """

    def test_single_file_no_checks(self):
        """Single-file tasks produce no multi-file checks."""
        checks = DomainPreflightWorkflow._multi_file_checks(
            ["src/pkg/module.py"]
        )
        assert checks == []

    def test_empty_files_no_checks(self):
        """Empty target list produces no checks."""
        checks = DomainPreflightWorkflow._multi_file_checks([])
        assert checks == []

    def test_multi_file_split_risk(self):
        """Two+ target files produce a split-risk warning."""
        targets = ["src/pkg/__init__.py", "src/pkg/module.py"]
        checks = DomainPreflightWorkflow._multi_file_checks(targets)
        names = [c.check_name for c in checks]
        assert "multi_file_split_risk" in names
        risk = next(c for c in checks if c.check_name == "multi_file_split_risk")
        assert risk.status == CheckStatus.WARN
        assert "2 files" in risk.message

    def test_init_py_warning(self):
        """__init__.py among targets triggers a dedicated warning."""
        targets = ["src/pkg/__init__.py", "src/pkg/module.py"]
        checks = DomainPreflightWorkflow._multi_file_checks(targets)
        names = [c.check_name for c in checks]
        assert "init_py_in_multi_file" in names
        init_check = next(
            c for c in checks if c.check_name == "init_py_in_multi_file"
        )
        assert init_check.status == CheckStatus.WARN
        assert "__init__.py" in init_check.message

    def test_no_init_py_no_init_warning(self):
        """Multi-file task without __init__.py omits the init-specific check."""
        targets = ["src/pkg/foo.py", "src/pkg/bar.py"]
        checks = DomainPreflightWorkflow._multi_file_checks(targets)
        names = [c.check_name for c in checks]
        assert "multi_file_split_risk" in names
        assert "init_py_in_multi_file" not in names

    def test_high_loc_warning(self):
        """High estimated LOC on multi-file tasks triggers truncation warning."""
        targets = ["src/pkg/__init__.py", "src/pkg/module.py"]
        checks = DomainPreflightWorkflow._multi_file_checks(
            targets, estimated_loc=300,
        )
        names = [c.check_name for c in checks]
        assert "multi_file_high_loc" in names
        loc_check = next(
            c for c in checks if c.check_name == "multi_file_high_loc"
        )
        assert "300" in loc_check.message

    def test_low_loc_no_high_loc_warning(self):
        """Low estimated LOC does not trigger high-LOC check."""
        targets = ["src/pkg/__init__.py", "src/pkg/module.py"]
        checks = DomainPreflightWorkflow._multi_file_checks(
            targets, estimated_loc=100,
        )
        names = [c.check_name for c in checks]
        assert "multi_file_high_loc" not in names

    def test_none_loc_no_high_loc_warning(self):
        """No estimated_loc (None) does not trigger high-LOC check."""
        targets = ["src/pkg/__init__.py", "src/pkg/module.py"]
        checks = DomainPreflightWorkflow._multi_file_checks(targets)
        names = [c.check_name for c in checks]
        assert "multi_file_high_loc" not in names
