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
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from startd8.utils.file_operations import atomic_write_json

from ..logging_config import get_logger

logger = get_logger(__name__)

DESIGN_HANDOFF_FILENAME = "design-handoff.json"
SCHEMA_VERSION = 1


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
    created_at: str = ""
    schema_version: int = SCHEMA_VERSION


def write_design_handoff(
    output_dir: str,
    enriched_seed_path: str,
    project_root: str,
    workflow_id: str,
    completed_phases: list[str] | None = None,
    design_results: dict[str, Any] | None = None,
    scaffold: dict[str, Any] | None = None,
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
        created_at=datetime.now(timezone.utc).isoformat(),
        schema_version=SCHEMA_VERSION,
    )

    out_path = Path(output_dir) / DESIGN_HANDOFF_FILENAME
    out_path.parent.mkdir(parents=True, exist_ok=True)

    atomic_write_json(out_path, asdict(handoff), indent=2, default=str)

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
        created_at=raw.get("created_at", ""),
        schema_version=version,
    )
