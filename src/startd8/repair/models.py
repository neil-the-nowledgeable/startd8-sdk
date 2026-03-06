"""Shared repair pipeline data models.

Provides dataclasses and exception types used across the micro-prime
and contractor-level repair pipelines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..exceptions import FileOperationError, Startd8Error


# ═══════════════════════════════════════════════════════════════════════════
# Exceptions (R3-S7)
# ═══════════════════════════════════════════════════════════════════════════


class RepairError(Startd8Error):
    """Deterministic repair step failure."""

    def __init__(
        self,
        message: str,
        step_name: str | None = None,
        file_path: str | None = None,
        original_error: Exception | None = None,
    ):
        super().__init__(message)
        self.step_name = step_name
        self.file_path = file_path
        self.original_error = original_error


class StagingError(FileOperationError):
    """I/O failure during staging operations."""

    pass


# ═══════════════════════════════════════════════════════════════════════════
# Diagnostics
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class Diagnostic:
    """Base diagnostic from a checkpoint failure."""

    category: str  # "syntax" | "import" | "lint" | "test" | "size"
    file: str
    message: str


@dataclass
class SyntaxDiagnostic(Diagnostic):
    """Syntax error diagnostic."""

    line: int = 0
    col: int = 0

    def __post_init__(self) -> None:
        self.category = "syntax"


@dataclass
class ImportDiagnostic(Diagnostic):
    """Missing import diagnostic."""

    module: str = ""
    name: str = ""

    def __post_init__(self) -> None:
        self.category = "import"


@dataclass
class LintDiagnostic(Diagnostic):
    """Lint rule violation diagnostic."""

    rule: str = ""
    line: int = 0
    fixable: bool = False

    def __post_init__(self) -> None:
        self.category = "lint"


# ═══════════════════════════════════════════════════════════════════════════
# Step & pipeline results
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class RepairStepResult:
    """Result from a single repair pipeline step.

    Provides per-step attribution for observability.
    """

    step_name: str
    modified: bool
    code: str
    metrics: Dict[str, Any] = field(default_factory=dict)


class RepairAttribution(BaseModel):
    """Per-step repair attribution for micro-prime level.

    Pydantic BaseModel for backward compatibility with micro-prime
    ``MicroPrimeElementMetrics.repair_attribution`` field.
    """

    fence_stripped: bool = False
    trimmed: bool = False
    nodes_removed: int = 0
    bare_wrapped: bool = False
    indent_source: str = ""
    params_changed: int = 0
    return_type_restored: bool = False
    imports_added: int = 0
    imports_removed: int = 0
    import_names: List[str] = Field(default_factory=list)


@dataclass
class FeatureRepairAttribution:
    """Feature-level repair attribution for contractor pipelines."""

    feature_name: str = ""
    files_repaired: int = 0
    steps_applied: List[str] = field(default_factory=list)
    repair_duration_ms: float = 0.0
    repair_success: bool = False


# ═══════════════════════════════════════════════════════════════════════════
# Context models
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class ElementContext:
    """Micro-prime element context for level-specific step adaptation."""

    parent_class: Optional[str] = None
    element_kind: Optional[str] = None
    element_name: Optional[str] = None
    imports: Optional[list] = None  # ForwardImportSpec list


@dataclass
class RepairContext:
    """Shared context passed to all repair steps."""

    diagnostics: List[Diagnostic] = field(default_factory=list)
    config: Optional[Any] = None  # RepairConfig; Any to avoid circular import
    element_context: Optional[ElementContext] = None
    project_root: Optional[Path] = None
    existing_imports: Optional[Dict[Path, set]] = None  # R1-S3
    manifest_registry: Optional[Any] = None  # R3-S8
    forward_manifest: Optional[Any] = None  # R7-S1 (Phase 2)
    service_metadata: Optional[Dict[str, Any]] = None  # R7-S6 (Phase 2)


# ═══════════════════════════════════════════════════════════════════════════
# Routing & outcome models
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class RepairRoute:
    """Routing decision capturing matched patterns, steps, and confidence."""

    matched_patterns: List[str] = field(default_factory=list)
    steps: List[str] = field(default_factory=list)
    confidence: str = "HIGH"  # HIGH | MEDIUM | LOW


@dataclass
class FileRepairResult:
    """Per-file repair outcome."""

    file_path: Path
    before_valid: bool = False
    after_valid: bool = False
    steps_applied: List[str] = field(default_factory=list)
    attribution: Optional[FeatureRepairAttribution] = None
    step_results: List[RepairStepResult] = field(default_factory=list)


@dataclass
class RepairOutcome:
    """Orchestrator return type for file-level repair.

    Does NOT include re-checkpoint results — the engine drives
    re-checkpoint, not the orchestrator (R2-S2).
    """

    repaired_files: Dict[Path, str] = field(default_factory=dict)
    file_results: List[FileRepairResult] = field(default_factory=list)
    steps_applied: List[str] = field(default_factory=list)
    route: Optional[RepairRoute] = None
    any_modified: bool = False


@dataclass
class RepairPipelineResult:
    """Full result including re-checkpoint (constructed by engine)."""

    outcome: RepairOutcome
    recheckpoint_passed: bool = False
    recheckpoint_results: List[Any] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
