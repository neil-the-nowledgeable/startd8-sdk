"""
Data models for the DomainPreflightWorkflow.

Defines enums, intermediate results, and output structures for the
domain preflight pipeline: load → scan → classify → check → enrich.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


__all__ = [
    "TaskDomain",
    "CheckStatus",
    "AvailableDeps",
    "DomainClassification",
    "EnvironmentCheck",
    "TaskEnrichment",
    "PreflightState",
]


class TaskDomain(str, Enum):
    """Domain classification for a task's target file."""
    PYTHON_SINGLE_MODULE = "python-single-module"
    PYTHON_PACKAGE_MODULE = "python-package-module"
    PYTHON_TEST = "python-test"
    CONFIG_TOML = "config-toml"
    CONFIG_YAML = "config-yaml"
    CONFIG_JSON = "config-json"
    NON_PYTHON = "non-python"
    UNKNOWN = "unknown"


class CheckStatus(str, Enum):
    """Status of an environment readiness check."""
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class AvailableDeps:
    """Available dependencies discovered from the project environment."""
    runtime: Set[str] = field(default_factory=set)
    optional: Dict[str, Set[str]] = field(default_factory=dict)
    stdlib: Set[str] = field(default_factory=set)
    project: Set[str] = field(default_factory=set)
    installed: Set[str] = field(default_factory=set)

    @property
    def all_importable(self) -> Set[str]:
        """Union of all importable package names."""
        result = (
            set(self.runtime)
            | set(self.stdlib)
            | set(self.project)
            | set(self.installed)
        )
        for group in self.optional.values():
            result |= group
        return result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "runtime": sorted(self.runtime),
            "optional": {k: sorted(v) for k, v in self.optional.items()},
            "stdlib": sorted(self.stdlib),
            "project": sorted(self.project),
            "installed": sorted(self.installed),
            "all_importable_count": len(self.all_importable),
        }


@dataclass
class DomainClassification:
    """Domain classification result for a single task target file."""
    task_id: str
    target_file: str
    domain: TaskDomain
    reasoning: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "target_file": self.target_file,
            "domain": self.domain.value,
            "reasoning": self.reasoning,
        }


@dataclass
class EnvironmentCheck:
    """Result of a single environment readiness check."""
    check_name: str
    status: CheckStatus
    message: str
    detail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "check_name": self.check_name,
            "status": self.status.value,
            "message": self.message,
        }
        if self.detail is not None:
            d["detail"] = self.detail
        return d


@dataclass
class TaskEnrichment:
    """Enrichment data computed for a single task."""
    task_id: str
    domain: TaskDomain
    domain_reasoning: str
    environment_checks: List[EnvironmentCheck] = field(default_factory=list)
    prompt_constraints: List[str] = field(default_factory=list)
    post_generation_validators: List[str] = field(default_factory=list)
    available_siblings: List[str] = field(default_factory=list)
    existing_content_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "domain": self.domain.value,
            "domain_reasoning": self.domain_reasoning,
            "environment_checks": [c.to_dict() for c in self.environment_checks],
            "prompt_constraints": list(self.prompt_constraints),
            "post_generation_validators": list(self.post_generation_validators),
            "available_siblings": list(self.available_siblings),
            "existing_content_hash": self.existing_content_hash,
        }


@dataclass
class PreflightState:
    """Mutable workflow state for debugging and checkpointing."""
    current_phase: str = "load"
    seed_path: Optional[str] = None
    project_root: Optional[str] = None
    task_count: int = 0
    enriched_count: int = 0
    check_summary: Dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_phase": self.current_phase,
            "seed_path": self.seed_path,
            "project_root": self.project_root,
            "task_count": self.task_count,
            "enriched_count": self.enriched_count,
            "check_summary": dict(self.check_summary),
            "error": self.error,
        }
