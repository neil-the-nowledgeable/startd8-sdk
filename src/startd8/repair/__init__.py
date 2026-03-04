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
    SyntaxDiagnostic,
)
from .orchestrator import run_element_repair, run_file_repair
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
    "RepairStep",
    "RepairStepResult",
    "StagingError",
    "StepValidator",
    "SyntaxDiagnostic",
    "route_failures",
    "run_element_repair",
    "run_file_repair",
]
