"""Tests for DomainChecklist adapter and post-generation validators."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock

import pytest

from startd8.contractors.artisan_phases.domain_checklist import (
    DomainChecklist,
    PostValidationIssue,
    PostValidationResult,
    validate_generated_code,
)
from startd8.workflows.builtin.domain_preflight_models import (
    AvailableDeps,
    CheckStatus,
    EnvironmentCheck,
    TaskDomain,
    TaskEnrichment,
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_enrichment() -> TaskEnrichment:
    """A TaskEnrichment with single-module domain."""
    return TaskEnrichment(
        task_id="chunk-1",
        domain=TaskDomain.PYTHON_SINGLE_MODULE,
        domain_reasoning="Single Python module",
        environment_checks=[
            EnvironmentCheck(
                check_name="parent_dir_exists",
                status=CheckStatus.PASS,
                message="Parent exists",
            ),
        ],
        prompt_constraints=[
            "Output a single Python module -- not a package",
            "Do not use relative imports (from .module import ...)",
            "Only import from: os, sys, json, pathlib, typing",
            "Define utility functions before classes that reference them",
        ],
        post_generation_validators=[
            "no_relative_imports",
            "deps_available",
            "definition_ordering",
        ],
    )


@pytest.fixture
def enriched_seed_path(tmp_path: Path) -> Path:
    """Create an enriched seed JSON file."""
    seed = {
        "version": "1.0.0",
        "tasks": [
            {
                "task_id": "task-A",
                "config": {"context": {"target_files": ["src/pkg/module_a.py"]}},
                "_enrichment": {
                    "task_id": "task-A",
                    "domain": "python-package-module",
                    "domain_reasoning": "Package module",
                    "environment_checks": [
                        {
                            "check_name": "init_py_exists",
                            "status": "pass",
                            "message": "__init__.py exists",
                        }
                    ],
                    "prompt_constraints": [
                        "This file is part of the pkg package",
                        "Use relative imports for siblings: utils",
                    ],
                    "post_generation_validators": [
                        "relative_imports_valid",
                        "deps_available",
                    ],
                    "available_siblings": ["utils"],
                    "existing_content_hash": "abcd1234",
                },
            },
            {
                "task_id": "task-B",
                "config": {"context": {"target_files": ["tests/test_module.py"]}},
                "_enrichment": {
                    "task_id": "task-B",
                    "domain": "python-test",
                    "domain_reasoning": "Test file",
                    "environment_checks": [],
                    "prompt_constraints": [
                        "Use pytest conventions",
                    ],
                    "post_generation_validators": ["test_naming"],
                    "available_siblings": [],
                },
            },
        ],
    }
    path = tmp_path / "artisan-context-seed-enriched.json"
    path.write_text(json.dumps(seed), encoding="utf-8")
    return path


@pytest.fixture
def project_fixture(tmp_path: Path) -> Path:
    """Create a minimal project structure for inline computation."""
    # pyproject.toml
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "demo"\ndependencies = ["httpx", "pydantic"]\n',
        encoding="utf-8",
    )

    # src/demo/__init__.py
    src = tmp_path / "src" / "demo"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "core.py").write_text("# core module\n", encoding="utf-8")

    # tests/
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_core.py").write_text("# tests\n", encoding="utf-8")

    return tmp_path


# ============================================================================
# TestDomainChecklistFromSeed
# ============================================================================


class TestDomainChecklistFromSeed:
    """Load enrichments from enriched seed JSON."""

    def test_known_task_returns_enrichment(self, enriched_seed_path: Path):
        checklist = DomainChecklist(enriched_seed_path=enriched_seed_path)
        enrichment = checklist.get_enrichment("task-A", ["src/pkg/module_a.py"])

        assert enrichment is not None
        assert enrichment.task_id == "task-A"
        assert enrichment.domain == TaskDomain.PYTHON_PACKAGE_MODULE
        assert "This file is part of the pkg package" in enrichment.prompt_constraints
        assert enrichment.available_siblings == ["utils"]
        assert enrichment.existing_content_hash == "abcd1234"

    def test_second_task_returns_enrichment(self, enriched_seed_path: Path):
        checklist = DomainChecklist(enriched_seed_path=enriched_seed_path)
        enrichment = checklist.get_enrichment("task-B", ["tests/test_module.py"])

        assert enrichment is not None
        assert enrichment.domain == TaskDomain.PYTHON_TEST

    def test_unknown_task_returns_none(self, enriched_seed_path: Path):
        checklist = DomainChecklist(enriched_seed_path=enriched_seed_path)
        enrichment = checklist.get_enrichment("task-UNKNOWN", ["some/file.py"])

        assert enrichment is None

    def test_missing_seed_file_returns_none(self, tmp_path: Path):
        checklist = DomainChecklist(
            enriched_seed_path=tmp_path / "nonexistent.json"
        )
        enrichment = checklist.get_enrichment("task-A", ["file.py"])

        assert enrichment is None

    def test_corrupted_seed_returns_none(self, tmp_path: Path):
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("not valid json{{{", encoding="utf-8")

        checklist = DomainChecklist(enriched_seed_path=bad_json)
        enrichment = checklist.get_enrichment("task-A", ["file.py"])

        assert enrichment is None

    def test_seed_loaded_only_once(self, enriched_seed_path: Path):
        checklist = DomainChecklist(enriched_seed_path=enriched_seed_path)

        # First call loads the seed
        checklist.get_enrichment("task-A", ["file.py"])
        assert checklist._seed_loaded is True

        # Overwrite the file — should not reload
        enriched_seed_path.write_text("{}", encoding="utf-8")
        enrichment = checklist.get_enrichment("task-A", ["file.py"])

        # Still returns the original data since seed was cached
        assert enrichment is not None
        assert enrichment.task_id == "task-A"


# ============================================================================
# TestDomainChecklistInline
# ============================================================================


class TestDomainChecklistInline:
    """Compute enrichments inline with project_root."""

    def test_package_module_detection(self, project_fixture: Path):
        checklist = DomainChecklist(project_root=project_fixture)
        enrichment = checklist.get_enrichment(
            "chunk-pkg", ["src/demo/core.py"]
        )

        assert enrichment is not None
        assert enrichment.domain == TaskDomain.PYTHON_PACKAGE_MODULE
        assert any("demo" in c for c in enrichment.prompt_constraints)

    def test_test_file_detection(self, project_fixture: Path):
        checklist = DomainChecklist(project_root=project_fixture)
        enrichment = checklist.get_enrichment(
            "chunk-test", ["tests/test_core.py"]
        )

        assert enrichment is not None
        assert enrichment.domain == TaskDomain.PYTHON_TEST

    def test_config_file_detection(self, project_fixture: Path):
        checklist = DomainChecklist(project_root=project_fixture)
        enrichment = checklist.get_enrichment(
            "chunk-cfg", ["pyproject.toml"]
        )

        assert enrichment is not None
        assert enrichment.domain == TaskDomain.CONFIG_TOML

    def test_deps_cached_across_calls(self, project_fixture: Path):
        checklist = DomainChecklist(project_root=project_fixture)

        deps1 = checklist.scan_deps()
        deps2 = checklist.scan_deps()

        assert deps1 is deps2  # Same object

    def test_deps_include_project_packages(self, project_fixture: Path):
        checklist = DomainChecklist(project_root=project_fixture)
        deps = checklist.scan_deps()

        assert deps is not None
        assert "demo" in deps.project


# ============================================================================
# TestDomainChecklistGraceful
# ============================================================================


class TestDomainChecklistGraceful:
    """Verify graceful None returns."""

    def test_no_project_root_no_seed(self):
        checklist = DomainChecklist()
        enrichment = checklist.get_enrichment("chunk-1", ["some/file.py"])

        assert enrichment is None

    def test_no_file_targets(self, project_fixture: Path):
        checklist = DomainChecklist(project_root=project_fixture)
        enrichment = checklist.get_enrichment("chunk-1", [])

        assert enrichment is None

    def test_scan_deps_without_project_root(self):
        checklist = DomainChecklist()
        deps = checklist.scan_deps()

        assert deps is None

    def test_seed_preferred_over_inline(
        self, enriched_seed_path: Path, project_fixture: Path
    ):
        """Enriched seed takes priority over inline computation."""
        checklist = DomainChecklist(
            project_root=project_fixture,
            enriched_seed_path=enriched_seed_path,
        )
        enrichment = checklist.get_enrichment("task-A", ["src/pkg/module_a.py"])

        # Should get the seed version (package-module), not inline
        assert enrichment is not None
        assert enrichment.domain == TaskDomain.PYTHON_PACKAGE_MODULE
        assert enrichment.existing_content_hash == "abcd1234"


# ============================================================================
# TestPostValidation
# ============================================================================


class TestPostValidation:

    def test_clean_code_passes(self, sample_enrichment: TaskEnrichment):
        code = (
            "import os\n"
            "import sys\n"
            "\n"
            "def helper():\n"
            "    return 42\n"
            "\n"
            "class MyClass:\n"
            "    pass\n"
        )
        result = validate_generated_code(code, sample_enrichment)

        assert result.passed is True
        assert result.issues == []

    def test_relative_import_flagged(self, sample_enrichment: TaskEnrichment):
        code = "from .sibling import helper\nimport os\n"
        result = validate_generated_code(code, sample_enrichment)

        assert result.passed is False
        assert any(
            i.validator == "no_relative_imports" for i in result.issues
        )

    def test_unavailable_dep_flagged(self, sample_enrichment: TaskEnrichment):
        code = "import requests\nimport os\n"
        result = validate_generated_code(code, sample_enrichment)

        assert result.passed is False
        dep_issues = [i for i in result.issues if i.validator == "deps_available"]
        assert len(dep_issues) >= 1
        assert "requests" in dep_issues[0].message

    def test_available_dep_passes(self, sample_enrichment: TaskEnrichment):
        code = "import os\nimport json\n"
        result = validate_generated_code(code, sample_enrichment)

        # Only deps_available and definition_ordering — both should pass
        dep_issues = [i for i in result.issues if i.validator == "deps_available"]
        assert dep_issues == []

    def test_definition_ordering_flagged(self, sample_enrichment: TaskEnrichment):
        code = (
            "from dataclasses import dataclass, field\n"
            "\n"
            "@dataclass\n"
            "class Config:\n"
            "    items: list = field(default_factory=make_items)\n"
            "\n"
            "def make_items():\n"
            "    return []\n"
        )
        result = validate_generated_code(code, sample_enrichment)

        assert result.passed is False
        order_issues = [
            i for i in result.issues if i.validator == "definition_ordering"
        ]
        assert len(order_issues) >= 1
        assert "make_items" in order_issues[0].message

    def test_definition_ordering_passes_when_correct(
        self, sample_enrichment: TaskEnrichment
    ):
        code = (
            "from dataclasses import dataclass, field\n"
            "\n"
            "def make_items():\n"
            "    return []\n"
            "\n"
            "@dataclass\n"
            "class Config:\n"
            "    items: list = field(default_factory=make_items)\n"
        )
        result = validate_generated_code(code, sample_enrichment)

        order_issues = [
            i for i in result.issues if i.validator == "definition_ordering"
        ]
        assert order_issues == []

    def test_syntax_error_handled_gracefully(
        self, sample_enrichment: TaskEnrichment
    ):
        code = "def broken(\n  # incomplete"
        result = validate_generated_code(code, sample_enrichment)

        # Should not raise, just pass (no AST to validate)
        assert result.passed is True
        assert result.issues == []

    def test_unknown_validators_skipped(self):
        """Validators not in _POST_VALIDATORS are silently ignored."""
        enrichment = TaskEnrichment(
            task_id="x",
            domain=TaskDomain.PYTHON_TEST,
            domain_reasoning="test",
            post_generation_validators=["unknown_validator", "also_unknown"],
        )
        result = validate_generated_code("import os\n", enrichment)

        assert result.passed is True

    def test_from_import_unavailable(self, sample_enrichment: TaskEnrichment):
        code = "from requests.models import Response\n"
        result = validate_generated_code(code, sample_enrichment)

        dep_issues = [i for i in result.issues if i.validator == "deps_available"]
        assert len(dep_issues) >= 1
        assert "requests" in dep_issues[0].message


# ============================================================================
# TestContextIsolation
# ============================================================================


class TestContextIsolation:
    """Verify shallow copy in _execute_tier prevents cross-chunk contamination."""

    @pytest.mark.asyncio
    async def test_context_not_shared_between_chunks(self, project_fixture: Path):
        from startd8.contractors.artisan_phases.development import (
            ChunkExecutor,
            DevelopmentChunk,
            DevelopmentPhase,
            DevelopmentPlan,
            TestRunner,
        )

        captured_contexts: Dict[str, Dict[str, Any]] = {}

        class CapturingExecutor(ChunkExecutor):
            async def execute(
                self, chunk: DevelopmentChunk, context: Dict[str, Any]
            ) -> Tuple[bool, str]:
                # Record a snapshot of context for this chunk
                captured_contexts[chunk.chunk_id] = dict(context)
                # Mutate context to prove isolation
                context["mutated_by"] = chunk.chunk_id
                return True, "ok"

        class PassingTestRunner(TestRunner):
            async def run_tests(
                self, chunk: DevelopmentChunk, context: Dict[str, Any]
            ) -> Tuple[bool, str]:
                return True, "ok"

        checklist = DomainChecklist(project_root=project_fixture)
        plan = DevelopmentPlan(
            plan_id="isolation-test",
            chunks=[
                DevelopmentChunk(
                    chunk_id="A",
                    description="First chunk",
                    dependencies=[],
                    file_targets=["src/demo/core.py"],
                    implementation_prompt="do A",
                    test_commands=[],
                ),
                DevelopmentChunk(
                    chunk_id="B",
                    description="Second chunk",
                    dependencies=[],
                    file_targets=["tests/test_core.py"],
                    implementation_prompt="do B",
                    test_commands=[],
                ),
            ],
        )

        phase = DevelopmentPhase(
            executor=CapturingExecutor(),
            test_runner=PassingTestRunner(),
            max_parallel=2,
            domain_checklist=checklist,
        )

        result = await phase.run(plan)

        assert result.success is True
        assert len(captured_contexts) == 2

        # Each chunk should NOT see the other's mutation
        if "mutated_by" in captured_contexts.get("A", {}):
            assert captured_contexts["A"]["mutated_by"] == "A"
        if "mutated_by" in captured_contexts.get("B", {}):
            assert captured_contexts["B"]["mutated_by"] == "B"

        # Domain constraints should be injected
        assert "domain" in captured_contexts.get("A", {})
        assert "domain" in captured_contexts.get("B", {})

    @pytest.mark.asyncio
    async def test_domain_constraints_injected_per_chunk(self, project_fixture: Path):
        from startd8.contractors.artisan_phases.development import (
            ChunkExecutor,
            DevelopmentChunk,
            DevelopmentPhase,
            DevelopmentPlan,
            TestRunner,
        )

        captured_domains: Dict[str, str] = {}

        class CapturingExecutor(ChunkExecutor):
            async def execute(
                self, chunk: DevelopmentChunk, context: Dict[str, Any]
            ) -> Tuple[bool, str]:
                captured_domains[chunk.chunk_id] = context.get("domain", "")
                return True, "ok"

        class PassingTestRunner(TestRunner):
            async def run_tests(
                self, chunk: DevelopmentChunk, context: Dict[str, Any]
            ) -> Tuple[bool, str]:
                return True, "ok"

        checklist = DomainChecklist(project_root=project_fixture)
        plan = DevelopmentPlan(
            plan_id="domain-test",
            chunks=[
                DevelopmentChunk(
                    chunk_id="pkg",
                    description="Package module",
                    dependencies=[],
                    file_targets=["src/demo/core.py"],
                    implementation_prompt="do pkg",
                    test_commands=[],
                ),
                DevelopmentChunk(
                    chunk_id="test",
                    description="Test file",
                    dependencies=[],
                    file_targets=["tests/test_core.py"],
                    implementation_prompt="do test",
                    test_commands=[],
                ),
            ],
        )

        phase = DevelopmentPhase(
            executor=CapturingExecutor(),
            test_runner=PassingTestRunner(),
            max_parallel=2,
            domain_checklist=checklist,
        )

        result = await phase.run(plan)

        assert result.success is True
        # Package module and test file should get different domains
        assert captured_domains.get("pkg") == "python-package-module"
        assert captured_domains.get("test") == "python-test"
