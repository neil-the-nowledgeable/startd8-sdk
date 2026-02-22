"""Shared fixtures for contract validation tests.

Provides:
- ContextCore availability skip marker
- Contract loading fixtures
- Context builder functions that simulate each phase's output
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pytest

# ---------------------------------------------------------------------------
# Graceful ContextCore import
# ---------------------------------------------------------------------------

try:
    from contextcore.contracts.propagation import (
        BoundaryValidator,
        ContractLoader,
        PropagationTracker,
    )
    from contextcore.contracts.propagation.schema import ContextContract
    from contextcore.contracts.types import ChainStatus, ConstraintSeverity, PropagationStatus

    CONTEXTCORE_AVAILABLE = True
except ImportError:
    CONTEXTCORE_AVAILABLE = False

requires_contextcore = pytest.mark.skipif(
    not CONTEXTCORE_AVAILABLE,
    reason="contextcore.contracts.propagation not installed",
)

def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply contract_validation marker and contextcore skip to all tests in this package."""
    for item in items:
        if "contract_validation" in str(item.fspath):
            item.add_marker(pytest.mark.contract_validation)
            if not CONTEXTCORE_AVAILABLE:
                item.add_marker(requires_contextcore)


# ---------------------------------------------------------------------------
# FakeSeedTask — mirrors the real SeedTask dataclass
# ---------------------------------------------------------------------------


@dataclass
class FakeSeedTask:
    """SeedTask stand-in for contract tests.

    Mirrors all fields on the real ``SeedTask`` so handler methods that
    access any attribute will find it here.
    """

    task_id: str = "T1"
    title: str = "Generate widget"
    task_type: str = "task"
    story_points: int = 3
    priority: str = "P1"
    labels: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    description: str = "Generate a widget module"
    target_files: list[str] = field(default_factory=list)
    estimated_loc: int = 100
    feature_id: str = "F-1"
    domain: str = "backend"
    domain_reasoning: str = ""
    environment_checks: list[dict] = field(default_factory=list)
    prompt_constraints: list[str] = field(default_factory=list)
    post_generation_validators: list[str] = field(
        default_factory=lambda: ["python_syntax"]
    )
    available_siblings: list[str] = field(default_factory=list)
    existing_content_hash: Optional[str] = None
    design_doc_sections: list[str] = field(default_factory=list)
    artifact_types_addressed: list[str] = field(default_factory=list)
    file_scope: dict[str, str] = field(default_factory=dict)
    requirements_text: str = ""
    api_signatures: list[str] = field(default_factory=list)
    protocol: str = ""
    runtime_dependencies: list[str] = field(default_factory=list)
    negative_scope: list[str] = field(default_factory=list)
    wave_index: Optional[int] = None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CONTRACT_YAML_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "startd8"
    / "contractors"
    / "contracts"
    / "artisan-pipeline.contract.yaml"
)


@pytest.fixture
def contract_path() -> Path:
    """Absolute path to the artisan pipeline contract YAML."""
    assert CONTRACT_YAML_PATH.exists(), f"Contract YAML not found: {CONTRACT_YAML_PATH}"
    return CONTRACT_YAML_PATH


@pytest.fixture
def loaded_contract(contract_path: Path) -> ContextContract:
    """Load the contract fresh (cache cleared) for test isolation."""
    ContractLoader.clear_cache()
    return ContractLoader().load(contract_path)


@pytest.fixture
def validator() -> BoundaryValidator:
    return BoundaryValidator()


@pytest.fixture
def tracker() -> PropagationTracker:
    return PropagationTracker()


# ---------------------------------------------------------------------------
# Context builders — each adds the keys its phase would produce
# ---------------------------------------------------------------------------


def _make_tasks() -> tuple[list[FakeSeedTask], dict[str, FakeSeedTask]]:
    """Create 2 FakeSeedTasks and a task_index dict."""
    t1 = FakeSeedTask(
        task_id="T1",
        title="Add user authentication",
        target_files=["src/auth/login.py"],
        estimated_loc=80,
        feature_id="F-AUTH-001",
        domain="backend",
        post_generation_validators=["ruff", "mypy"],
    )
    t2 = FakeSeedTask(
        task_id="T2",
        title="Create dashboard component",
        target_files=["src/ui/dashboard.py"],
        estimated_loc=120,
        feature_id="F-DASH-001",
        domain="frontend",
        depends_on=["T1"],
        post_generation_validators=["ruff"],
    )
    tasks = [t1, t2]
    task_index = {t.task_id: t for t in tasks}
    return tasks, task_index


def build_plan_exit_context(tmp_path: Path) -> dict[str, Any]:
    """Context after the PLAN phase completes."""
    tasks, task_index = _make_tasks()
    return {
        "project_root": str(tmp_path),
        "enriched_seed_path": str(tmp_path / "enriched-seed.json"),
        "tasks": tasks,
        "task_index": task_index,
        "plan_title": "Test Contract Validation Plan",
        "plan_goals": ["Validate contract propagation"],
        "domain_summary": {
            "domain": "web_application",
            "prompt_constraints": ["Use type hints"],
            "post_generation_validators": ["ruff", "mypy"],
        },
        "preflight_summary": {"pass": 2, "fail": 0, "warn": 0},
        "total_estimated_loc": 200,
        "architectural_context": {"objectives": ["auth", "dashboard"]},
        "design_calibration": {"max_output_tokens": 4096},
        "example_artifacts": {},
        "service_metadata": {"protocol": "REST", "dependencies": ["flask"]},
    }


def build_scaffold_exit_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Add SCAFFOLD phase output to context."""
    ctx["scaffold"] = {
        "directories_needed": ["src/auth", "src/ui"],
        "directories_created": ["src/auth", "src/ui"],
        "directories_exist": ["src/auth", "src/ui"],
        "project_root": ctx["project_root"],
        "existing_target_files": ["src/auth/__init__.py"],
    }
    return ctx


def build_design_exit_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Add DESIGN phase output to context."""
    # Build a multi-line design doc with multiple sections for quality checks.
    design_doc = "\n".join(
        [
            "# Architecture",
            "## Authentication Module",
            "JWT-based auth with bcrypt password hashing.",
            "## API Endpoints",
            "/login, /logout, /refresh",
            "## Error Handling",
            "Custom exception hierarchy.",
        ]
        + [f"Line {i}: implementation detail" for i in range(60)]
    )
    ctx["design_results"] = {
        "T1": {
            "status": "completed",
            "domain": "backend",
            "design_doc": design_doc,
            "design_mode": "create",
        },
        "T2": {
            "status": "completed",
            "domain": "frontend",
            "design_doc": design_doc,
            "design_mode": "update",
        },
    }
    # Derived summary for chain 5 (design_mode_to_implement)
    ctx["design_mode_summary"] = {"T1": "create", "T2": "create"}
    return ctx


def build_implement_exit_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Add IMPLEMENT phase output to context."""
    gen_code = "\n".join([f"# line {i}" for i in range(20)])
    ctx["implementation"] = {
        "task_reports": {"T1": {"status": "ok"}, "T2": {"status": "ok"}},
        "tasks_processed": 2,
        "total_cost": 0.05,
        "metadata": {
            "design_mode_summary": ctx.get("design_mode_summary", {}),
            "service_metadata": ctx.get("service_metadata"),
        },
    }
    ctx["generation_results"] = {
        "T1": {"code": gen_code, "file_path": "src/auth/login.py", "lines": 20},
        "T2": {"code": gen_code, "file_path": "src/ui/dashboard.py", "lines": 20},
    }
    ctx["truncation_flags"] = {"T1": False, "T2": False}
    return ctx


def build_integrate_exit_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Add INTEGRATE phase output to context."""
    ctx["integration_results"] = {
        "T1": {"success": True, "integrated_files": ["src/auth/login.py"], "errors": []},
        "T2": {"success": True, "integrated_files": ["src/ui/dashboard.py"], "errors": []},
    }
    return ctx


def build_test_exit_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Add TEST phase output to context."""
    ctx["test_results"] = {
        "test_plan": [
            {"task_id": "T1", "status": "passed", "validators": ["ruff", "mypy"]},
            {"task_id": "T2", "status": "passed", "validators": ["ruff"]},
        ],
        "total_passed": 2,
        "total_failed": 0,
        "per_task": {
            "T1": {"passed": True, "validators_run": ["ruff", "mypy"]},
            "T2": {"passed": True, "validators_run": ["ruff"]},
        },
        "unique_validators": ["ruff", "mypy"],
    }
    return ctx


def build_review_exit_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Add REVIEW phase output to context."""
    ctx["review_results"] = {
        "review_items": [
            {"task_id": "T1", "review_status": "approved", "score": 85},
            {"task_id": "T2", "review_status": "approved", "score": 90},
        ],
        "total_passed": 2,
        "total_failed": 0,
        "per_task": {
            "T1": {"passed": True, "score": 85},
            "T2": {"passed": True, "score": 90},
        },
        "constraint_coverage": {"T1": 1.0, "T2": 1.0},
        "total_cost": 0.02,
    }
    return ctx


def build_finalize_exit_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Add FINALIZE phase output to context."""
    ctx["workflow_summary"] = {
        "plan_title": ctx.get("plan_title", "Test Plan"),
        "task_count": len(ctx.get("tasks", [])),
        "status": "success",
        "cost_summary": {
            "implementation_cost": 0.05,
            "test_cost": 0.0,
            "review_cost": 0.02,
            "total_cost": 0.07,
            "currency": "USD",
        },
        "domain_summary": ctx.get("domain_summary", {}),
        "scaffold_summary": ctx.get("scaffold", {}),
        "implementation_summary": ctx.get("implementation", {}),
        "test_summary": ctx.get("test_results", {}),
        "review_summary": ctx.get("review_results", {}),
    }
    return ctx


def build_full_pipeline_context(tmp_path: Path) -> dict[str, Any]:
    """Build context as if all 8 phases executed successfully."""
    ctx = build_plan_exit_context(tmp_path)
    build_scaffold_exit_context(ctx)
    build_design_exit_context(ctx)
    build_implement_exit_context(ctx)
    build_integrate_exit_context(ctx)
    build_test_exit_context(ctx)
    build_review_exit_context(ctx)
    build_finalize_exit_context(ctx)
    return ctx
