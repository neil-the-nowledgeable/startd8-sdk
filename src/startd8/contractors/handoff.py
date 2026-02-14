"""
Design handoff persistence for the two-half artisan workflow.

The first half (PLAN → SCAFFOLD → DESIGN) writes a handoff file containing
context state needed by the second half (IMPLEMENT → TEST → REVIEW → FINALIZE).

The second half auto-detects or explicitly loads this handoff file,
reconstructs the shared context dict, and continues execution.

Usage::

    from startd8.contractors.handoff import write_design_handoff, load_design_handoff

    # First half writes:
    write_design_handoff(
        output_dir="out/designs",
        enriched_seed_path="/abs/path/to/seed.json",
        project_root="/abs/path/to/project",
        workflow_id="abc-123",
        completed_phases=["plan", "scaffold", "design"],
        design_results={...},
        scaffold={...},
    )

    # Second half reads:
    handoff = load_design_handoff("out/designs")  # auto-appends filename
    # or
    handoff = load_design_handoff("out/designs/design-handoff.json")

Schema (Item 13): The handoff file conforms to HandoffData; see HANDOFF_SCHEMA
and write_design_handoff validates before write when jsonschema is installed.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from startd8.utils.file_operations import atomic_write_json
from startd8.workflows.builtin.schema_versions import ARTISAN_SCHEMA_VERSION

from ..logging_config import get_logger

logger = get_logger(__name__)

DESIGN_HANDOFF_FILENAME = "design-handoff.json"
SCHEMA_VERSION = 1  # Integer for backward compat; schema_version_str = ARTISAN_SCHEMA_VERSION

# Map integer schema_version to string for legacy handoffs missing schema_version_str.
_SCHEMA_VERSION_TO_STR: dict[int, str] = {1: ARTISAN_SCHEMA_VERSION}

# JSON Schema for design-handoff.json (Item 13 — validation before write)
HANDOFF_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["enriched_seed_path", "project_root", "output_dir", "workflow_id", "schema_version"],
    "properties": {
        "enriched_seed_path": {"type": "string"},
        "project_root": {"type": "string"},
        "output_dir": {"type": "string"},
        "workflow_id": {"type": "string"},
        "completed_phases": {"type": "array", "items": {"type": "string"}},
        "design_results": {"type": "object"},
        "scaffold": {"type": "object"},
        "artifact_manifest_path": {"type": ["string", "null"]},
        "project_context_path": {"type": ["string", "null"]},
        "context_files": {"type": "array", "items": {"type": "object"}},
        "example_artifacts": {"type": "object"},
        "coverage_gaps": {"type": "array", "items": {"type": "string"}},
        "created_at": {"type": "string"},
        "schema_version": {"type": "integer"},
        "schema_version_str": {"type": "string"},
    },
    "additionalProperties": True,
}


def _validate_handoff(data: dict[str, Any]) -> None:
    """Validate handoff JSON against schema before write (Item 13).

    Requires jsonschema (included in dev dependencies).  Raises on
    validation failure rather than silently writing an invalid handoff.
    """
    try:
        import jsonschema  # noqa: F811
    except ImportError:
        raise ImportError(
            "jsonschema is required for handoff validation. "
            "Install it with: pip install jsonschema"
        )

    jsonschema.validate(data, HANDOFF_SCHEMA)
    logger.debug("Design handoff validated against schema")


@dataclass
class HandoffData:
    """Context state persisted between the design and implementation halves.

    Attributes:
        enriched_seed_path: Absolute path to the enriched context seed JSON.
        project_root: Absolute path to the target project root directory.
        output_dir: Directory where design artifacts were written.
        workflow_id: Unique identifier of the first-half workflow run.
        completed_phases: Phase values completed by the first half.
        design_results: Per-task design output (task_id → result dict).
        scaffold: Scaffold phase summary dict.
        created_at: ISO-8601 timestamp when the handoff was written.
        schema_version: Version for forward compatibility (currently 1).
    """

    enriched_seed_path: str
    project_root: str
    output_dir: str
    workflow_id: str
    completed_phases: list[str] = field(default_factory=list)
    design_results: dict[str, Any] = field(default_factory=dict)
    scaffold: dict[str, Any] = field(default_factory=dict)
    artifact_manifest_path: str | None = None
    project_context_path: str | None = None
    # Context files the design was based on (path + optional checksum)
    context_files: list[dict[str, Any]] = field(default_factory=list)
    # Example artifacts per type (e.g. ServiceMonitor YAML) for implement phase (Item 9)
    example_artifacts: dict[str, Any] = field(default_factory=dict)
    # Coverage gaps — artifact types to generate first (Item 11)
    coverage_gaps: list[str] = field(default_factory=list)
    created_at: str = ""
    schema_version: int = SCHEMA_VERSION
    schema_version_str: str = ARTISAN_SCHEMA_VERSION


def write_design_handoff(
    output_dir: str,
    enriched_seed_path: str,
    project_root: str,
    workflow_id: str,
    completed_phases: list[str] | None = None,
    design_results: dict[str, Any] | None = None,
    scaffold: dict[str, Any] | None = None,
    artifact_manifest_path: str | None = None,
    project_context_path: str | None = None,
    context_files: list[dict[str, Any]] | None = None,
    example_artifacts: dict[str, Any] | None = None,
    coverage_gaps: list[str] | None = None,
) -> Path:
    """Serialize design handoff state to a JSON file.

    Args:
        output_dir: Directory to write the handoff file into.
        enriched_seed_path: Absolute path to the enriched context seed.
        project_root: Absolute path to the target project root.
        workflow_id: Workflow run identifier.
        completed_phases: List of completed phase value strings.
        design_results: Per-task design results dict.
        scaffold: Scaffold phase summary dict.

    Returns:
        Path to the written handoff file.
    """
    handoff = HandoffData(
        enriched_seed_path=enriched_seed_path,
        project_root=project_root,
        output_dir=output_dir,
        workflow_id=workflow_id,
        completed_phases=completed_phases or [],
        design_results=design_results or {},
        scaffold=scaffold or {},
        artifact_manifest_path=artifact_manifest_path,
        project_context_path=project_context_path,
        context_files=context_files or [],
        example_artifacts=example_artifacts or {},
        coverage_gaps=coverage_gaps or [],
        created_at=datetime.now(timezone.utc).isoformat(),
        schema_version=SCHEMA_VERSION,
        schema_version_str=ARTISAN_SCHEMA_VERSION,
    )

    out_path = Path(output_dir) / DESIGN_HANDOFF_FILENAME
    out_path.parent.mkdir(parents=True, exist_ok=True)

    data = asdict(handoff)
    _validate_handoff(data)
    atomic_write_json(out_path, data, indent=2, default=str)

    logger.info("Wrote design handoff: %s", out_path)
    return out_path


def load_design_handoff(path: str | Path) -> HandoffData:
    """Load a design handoff from a file or directory.

    Args:
        path: Path to the handoff JSON file, or a directory containing one
              (the standard filename is appended automatically).

    Returns:
        Populated HandoffData instance.

    Raises:
        FileNotFoundError: If the handoff file does not exist.
        ValueError: If required keys are missing or schema version is
                    unsupported.
    """
    path = Path(path)

    if path.is_dir():
        path = path / DESIGN_HANDOFF_FILENAME

    if not path.exists():
        logger.error("Handoff file not found: %s", path)
        raise FileNotFoundError(f"Handoff file not found: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Failed to parse design handoff file {path}: {exc}"
        ) from exc

    # Validate schema version
    version = raw.get("schema_version")
    if version is None:
        raise ValueError(f"Handoff file missing 'schema_version': {path}")
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"Handoff schema version {version} is newer than supported "
            f"version {SCHEMA_VERSION}. Upgrade the SDK to read this file."
        )

    # Validate required keys
    required = ("enriched_seed_path", "project_root", "output_dir", "workflow_id")
    missing = [k for k in required if k not in raw]
    if missing:
        raise ValueError(
            f"Handoff file missing required keys {missing}: {path}"
        )

    return HandoffData(
        enriched_seed_path=raw["enriched_seed_path"],
        project_root=raw["project_root"],
        output_dir=raw["output_dir"],
        workflow_id=raw["workflow_id"],
        completed_phases=raw.get("completed_phases", []),
        design_results=raw.get("design_results", {}),
        scaffold=raw.get("scaffold", {}),
        artifact_manifest_path=raw.get("artifact_manifest_path"),
        project_context_path=raw.get("project_context_path"),
        context_files=raw.get("context_files", []),
        example_artifacts=raw.get("example_artifacts", {}),
        coverage_gaps=raw.get("coverage_gaps", []),
        created_at=raw.get("created_at", ""),
        schema_version=version,
        schema_version_str=raw.get("schema_version_str")
        or _SCHEMA_VERSION_TO_STR.get(version, ARTISAN_SCHEMA_VERSION),
    )


def validate_handoff_against_context(
    handoff: HandoffData,
    context: dict[str, Any],
) -> list[str]:
    """Cross-validate a loaded handoff against the current context dict.

    Checks that:
    - design_results task IDs match the task IDs in context["tasks"]
    - enriched_seed_path matches context["enriched_seed_path"]
    - project_root matches context["project_root"]

    Returns:
        List of warning messages (empty if everything is consistent).
        Does **not** raise — callers decide whether to abort or log.
    """
    warnings: list[str] = []

    # Task ID cross-check
    tasks = context.get("tasks")
    if tasks and handoff.design_results:
        context_task_ids = set()
        for t in tasks:
            tid = getattr(t, "task_id", None) or (t.get("task_id") if isinstance(t, dict) else None)
            if tid:
                context_task_ids.add(tid)

        handoff_task_ids = set(handoff.design_results.keys())

        in_handoff_not_context = handoff_task_ids - context_task_ids
        in_context_not_handoff = context_task_ids - handoff_task_ids

        if in_handoff_not_context:
            warnings.append(
                f"Handoff design_results contains task IDs not in context tasks: "
                f"{sorted(in_handoff_not_context)}"
            )
        if in_context_not_handoff:
            warnings.append(
                f"Context tasks contains task IDs not in handoff design_results: "
                f"{sorted(in_context_not_handoff)}"
            )

    # Path consistency checks
    ctx_seed = context.get("enriched_seed_path", "")
    if ctx_seed and handoff.enriched_seed_path and ctx_seed != handoff.enriched_seed_path:
        warnings.append(
            f"enriched_seed_path mismatch: context={ctx_seed!r}, "
            f"handoff={handoff.enriched_seed_path!r}"
        )

    ctx_root = context.get("project_root", "")
    if ctx_root and handoff.project_root and str(ctx_root) != str(handoff.project_root):
        warnings.append(
            f"project_root mismatch: context={ctx_root!r}, "
            f"handoff={handoff.project_root!r}"
        )

    if warnings:
        for w in warnings:
            logger.warning("Handoff cross-validation: %s", w)
    else:
        logger.debug("Handoff cross-validation passed — context and handoff are consistent")

    return warnings
