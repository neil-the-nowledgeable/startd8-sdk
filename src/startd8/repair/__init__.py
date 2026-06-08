"""Shared repair pipeline for startd8 SDK.

Provides deterministic repair primitives shared between the micro-prime
engine and contractor-level integration pipelines.

Public API:
    RepairStep, RepairConfig, RepairContext, RepairStepResult,
    RepairPipelineResult, FileRepairResult, FeatureRepairAttribution,
    RepairRoute, RepairOutcome, RepairAttribution, RepairError, StagingError,
    route_failures, run_element_repair, run_file_repair
"""

from .config import RepairConfig
from .models import (
    Diagnostic,
    ElementContext,
    FeatureRepairAttribution,
    FileRepairResult,
    ImportDiagnostic,
    LintDiagnostic,
    RepairAttribution,
    RepairContext,
    RepairError,
    RepairOutcome,
    RepairPipelineResult,
    RepairRoute,
    RepairStepResult,
    StagingError,
    StepEffectiveness,
    SyntaxDiagnostic,
)
from .orchestrator import (
    RepairSession,
    get_repair_frequency,
    get_step_effectiveness,
    reset_circuit_breaker,
    reset_step_effectiveness,
    run_element_repair,
    run_file_repair,
)
from .protocol import AstParseValidator, PipelineValidator, RepairStep, StepValidator
from .routing import route_failures

__all__ = [
    "AstParseValidator",
    "Diagnostic",
    "ElementContext",
    "FeatureRepairAttribution",
    "FileRepairResult",
    "ImportDiagnostic",
    "LintDiagnostic",
    "PipelineValidator",
    "RepairAttribution",
    "RepairConfig",
    "RepairContext",
    "RepairError",
    "RepairOutcome",
    "RepairPipelineResult",
    "RepairRoute",
    "RepairSession",
    "RepairStep",
    "RepairStepResult",
    "StagingError",
    "StepEffectiveness",
    "StepValidator",
    "SyntaxDiagnostic",
    "get_repair_frequency",
    "get_step_effectiveness",
    "reset_circuit_breaker",
    "reset_step_effectiveness",
    "route_failures",
    "run_element_repair",
    "run_file_repair",
]
