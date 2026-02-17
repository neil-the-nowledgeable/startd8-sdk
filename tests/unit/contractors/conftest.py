"""Shared test helpers for contractors unit tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FakeSeedTask:
    """Comprehensive SeedTask-like object for handler tests.

    Mirrors all fields on the real ``SeedTask`` dataclass so handler
    methods that access any attribute will find it here.
    """

    task_id: str = "T-1"
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
