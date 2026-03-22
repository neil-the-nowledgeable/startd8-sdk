"""
Seed validation — JSON schema checks and unified field coverage.

All context fields are validated regardless of route (seed unification
REQ-SU-101). The ``route`` parameter on ``validate_for_route`` is retained
for backward compatibility but does not alter validation behavior.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..logging_config import get_logger

logger = get_logger(__name__)

__all__ = [
    "CONTEXT_SEED_SCHEMA",
    "validate_context_seed",
    "validate_seed_field_coverage",
    "log_seed_coverage",
    "validate_for_route",
]

# JSON Schema for context seed (Item 6 — validation before write)
CONTEXT_SEED_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["version", "tasks", "artifacts", "ingestion_metrics"],
    "properties": {
        "version": {"type": "string"},
        "schema_version": {"type": "string"},
        "source_checksum": {"type": ["string", "null"]},
        "generated_at": {"type": "string"},
        "generator": {"type": "string"},
        "plan": {"type": ["object", "null"]},
        "complexity": {"type": ["object", "null"]},
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["task_id", "title", "config"],
                "properties": {
                    "task_id": {"type": "string"},
                    "title": {"type": "string"},
                    "config": {"type": "object"},
                },
            },
        },
        "artifacts": {"type": "object"},
        "ingestion_metrics": {"type": "object"},
        "onboarding": {"type": ["object", "null"]},
        "architectural_context": {"type": ["object", "null"]},
        "design_calibration": {"type": ["object", "null"]},
        "context_files": {"type": ["array", "null"]},
        "service_metadata": {"type": ["object", "null"]},
        "wave_metadata": {"type": ["object", "null"]},
        "lane_assignments": {"type": ["object", "null"]},
        "project_metadata": {"type": ["object", "null"]},
    },
    "additionalProperties": True,
}


def validate_context_seed(data: Dict[str, Any]) -> bool:
    """Validate context seed against JSON schema.

    Uses jsonschema if installed; returns True otherwise (graceful fallback).
    """
    try:
        import jsonschema
    except ImportError:
        return True

    try:
        jsonschema.validate(data, CONTEXT_SEED_SCHEMA)
        logger.debug("Context seed validated against schema")
        return True
    except jsonschema.ValidationError as e:
        logger.warning(
            "Context seed schema validation failed: %s — writing anyway",
            e.message,
        )
        return False


def validate_seed_field_coverage(seed_dict: Dict[str, Any]) -> List[str]:
    """Advisory validation: check field coverage for seed quality.

    Returns list of warning strings (empty = all fields well-populated).
    """
    warnings: List[str] = []

    tasks = seed_dict.get("tasks", [])
    if not tasks:
        warnings.append("seed has no tasks")
        return warnings

    tasks_missing_targets = sum(
        1
        for t in tasks
        if not t.get("config", {}).get("context", {}).get("target_files")
    )
    if tasks_missing_targets > 0:
        warnings.append(
            f"{tasks_missing_targets}/{len(tasks)} task(s) missing target_files"
        )

    tasks_missing_description = sum(
        1 for t in tasks if not t.get("config", {}).get("task_description")
    )
    if tasks_missing_description > 0:
        warnings.append(
            f"{tasks_missing_description}/{len(tasks)} task(s) missing description"
        )

    if not seed_dict.get("architectural_context"):
        warnings.append(
            "no architectural_context — design phase may lack shared context"
        )

    if not seed_dict.get("design_calibration"):
        warnings.append("no design_calibration — design depth tiers unavailable")

    if not seed_dict.get("service_metadata"):
        warnings.append(
            "no service_metadata — protocol fidelity validators will be skipped"
        )

    if not seed_dict.get("onboarding"):
        warnings.append("no onboarding metadata — parameter sources unavailable")

    if not seed_dict.get("context_files"):
        warnings.append("no context_files — provenance tracking limited")

    if not seed_dict.get("project_metadata"):
        warnings.append(
            "no project_metadata — criticality/SLO-aware generation unavailable"
        )

    return warnings


def log_seed_coverage(seed_dict: Dict[str, Any], label: str = "") -> None:
    """Run advisory field-coverage check and log any warnings."""
    warnings = validate_seed_field_coverage(seed_dict)
    if warnings:
        tag = f" [{label}]" if label else ""
        logger.warning(
            "Seed field-coverage advisory%s (%d warning(s)): %s",
            tag,
            len(warnings),
            "; ".join(warnings),
        )


def validate_for_route(seed_dict: Dict[str, Any], route: str) -> List[str]:
    """Validate seed with schema check and unified field coverage.

    All context fields (architectural_context, design_calibration, onboarding,
    etc.) are validated regardless of route — see REQ-SU-101.

    Args:
        seed_dict: The seed dictionary to validate.
        route: Retained for backward compatibility. Does not affect
            validation behavior (all fields checked for all routes).

    Returns:
        List of warning strings (empty = no issues).
    """
    warnings: List[str] = []

    if not validate_context_seed(seed_dict):
        warnings.append("base schema validation failed")

    # validate_seed_field_coverage already checks all context fields
    # (architectural_context, design_calibration, onboarding, etc.)
    warnings.extend(validate_seed_field_coverage(seed_dict))

    return warnings
