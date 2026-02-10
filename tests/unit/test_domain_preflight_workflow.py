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
        assert d["all_importable_count"] == 3


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

    def test_test_constraints(self, tmp_path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()

        enrichment = DomainPreflightWorkflow._build_enrichment(
            "PI-003", TaskDomain.PYTHON_TEST,
            "Test file", "tests/test_models.py",
            tmp_path, self._make_deps(), [],
        )
        assert any("pytest" in c.lower() for c in enrichment.prompt_constraints)
        assert "imports_resolve" in enrichment.post_generation_validators
        assert "test_naming" in enrichment.post_generation_validators

    def test_config_constraints(self, tmp_path):
        enrichment = DomainPreflightWorkflow._build_enrichment(
            "PI-004", TaskDomain.CONFIG_TOML,
            "Config file", "pyproject.toml",
            tmp_path, self._make_deps(), [],
        )
        assert any("Preserve" in c for c in enrichment.prompt_constraints)
        assert "valid_format" in enrichment.post_generation_validators

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
        assert enriched["_preflight"]["workflow_version"] == "1.0.0"
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
        assert meta.version == "1.0.0"

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
