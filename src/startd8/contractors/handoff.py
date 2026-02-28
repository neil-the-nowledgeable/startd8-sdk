"""
Design handoff persistence for the two-half artisan workflow.

The first half (PLAN → SCAFFOLD → DESIGN) writes a handoff file containing
context state needed by the second half (IMPLEMENT → INTEGRATE → TEST → REVIEW → FINALIZE).

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
import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from startd8.logging_config import get_logger
from startd8.utils.file_operations import atomic_write_json
from startd8.workflows.builtin.schema_versions import ARTISAN_SCHEMA_VERSION

logger = get_logger(__name__)

DESIGN_HANDOFF_FILENAME = "design-handoff.json"
DESIGN_HANDOFF_CONTRACT_FILENAME = "design-handoff-contract.json"
SCHEMA_VERSION = 1  # Integer for backward compat; schema_version_str = ARTISAN_SCHEMA_VERSION

# Map integer schema_version to string for legacy handoffs missing schema_version_str.
_SCHEMA_VERSION_TO_STR: dict[int, str] = {
    1: "1.0.0",
    2: "2.0.0",
    3: "3.0.0",
    4: ARTISAN_SCHEMA_VERSION,  # Current version
}

# Lazy import helpers for ContextCore contracts
try:
    from contextcore.contracts.a2a.models import (
        HandoffContract,
        HandoffPriority,
        HandoffContractStatus,
        ExpectedOutput,
    )
    CONTEXTCORE_AVAILABLE = True
except ImportError:
    CONTEXTCORE_AVAILABLE = False
    HandoffContract = Any
    HandoffPriority = Any
    HandoffContractStatus = Any
    ExpectedOutput = Any


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
        "design_mode_summary": {"type": "object"},
        "source_checksum": {"type": ["string", "null"]},
        "project_manifest_summary": {
            "type": ["object", "null"],
            "description": "Manifest summary with keys: file_count, total_elements, public_elements, schema_version, generated_at",
            "properties": {
                "file_count": {"type": "integer"},
                "total_elements": {"type": "integer"},
                "public_elements": {"type": "integer"},
                "schema_version": {"type": "string"},
                "generated_at": {"type": "string"},
            },
        },
        "design_quality": {
            "type": "object",
            "description": "DESIGN phase quality gate results (total_passed, total_failed, agreement_rate)",
        },
        "created_at": {"type": "string"},
        "schema_version": {"type": "integer"},
        "schema_version_str": {"type": "string"},
    },
    "additionalProperties": True,
}


class HandoffContextDriftError(Exception):
    """Raised when context files have changed since handoff creation."""


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
        design_structural_delta: Per-task element-level intent from design
            docs (Gap 3: add/modify/preserve per file).
        design_referenced_elements: Per-task element names cross-validated
            against the manifest for phantom-element detection (Gap 1).
        manifest_file_checksums: Per-file SHA-256 at design time for
            staleness detection between split runs (Gap 2).
        design_mode_evidence: Per-task design mode reasoning with
            corroborating signals for weight elevation (Gap 4).
        manifest_truncation_tier: Per-file manifest fidelity tier used
            during DESIGN (full/compact/public_only/fqn_only/unavailable) (Gap 5).
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
    # B-6: Per-task edit mode classification ("create" | "update" | "skipped")
    design_mode_summary: dict[str, str] = field(default_factory=dict)
    # CCD-301: Shared-file manifest (file_path → list of contesting task_ids)
    shared_file_manifest: dict[str, list[str]] = field(default_factory=dict)
    # SHA-256 of the enriched seed file at design time (provenance chain)
    source_checksum: str | None = None
    # Phase 4: Manifest summary for handoff (ManifestSummarySchema typed dict)
    project_manifest_summary: dict[str, Any] | None = None
    # Gap 3: Per-task structural delta extracted from design docs
    # {task_id: {filepath: [{"element": "...", "action": "add|modify|preserve", "detail": "..."}]}}
    design_structural_delta: dict[str, dict[str, list[dict[str, str]]]] = field(default_factory=dict)
    # Gap 1: Per-task referenced element names for phantom-element cross-validation
    # {task_id: {filepath: ["ClassName", "func_name", ...]}}
    design_referenced_elements: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    # Gap 2: Per-file SHA-256 checksums of target files at design time
    # {filepath: checksum_hex}
    manifest_file_checksums: dict[str, str] = field(default_factory=dict)
    # Gap 4: Extended design mode with reasoning evidence
    # {task_id: {"mode": "create|update", "evidence": [...], "reasoning": "..."}}
    design_mode_evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Gap 5: Per-file manifest truncation tier used during DESIGN
    # {filepath: "full|compact|public_only|fqn_only|unavailable"}
    manifest_truncation_tier: dict[str, str] = field(default_factory=dict)
    # Quality gate result from DESIGN phase
    # {total_passed, total_failed, agreement_rate, evaluated_task_count}
    design_quality: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    schema_version: int = SCHEMA_VERSION
    schema_version_str: str = ARTISAN_SCHEMA_VERSION


def compute_context_checksums(context_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compute SHA-256 checksums for context files if missing.

    Args:
        context_files: List of dicts, each with at least 'path'.

    Returns:
        New list of dicts with 'checksum' populated where possible.
    """
    enriched = []
    for item in context_files:
        new_item = item.copy()
        path_str = new_item.get("path")
        
        if path_str and not new_item.get("checksum"):
            path = Path(path_str)
            if path.exists() and path.is_file():
                try:
                    # Read file and compute hash
                    content = path.read_bytes()
                    checksum = hashlib.sha256(content).hexdigest()
                    new_item["checksum"] = checksum
                except OSError as exc:
                    logger.warning("Failed to compute checksum for %s: %s", path, exc)
        
        enriched.append(new_item)
    return enriched


def verify_context_checksums(context_files: list[dict[str, Any]], strict: bool = False) -> list[str]:
    """Verify context files match their checksums.

    Args:
        context_files: List of dicts with 'path' and optional 'checksum'.
        strict: If True, raise HandoffContextDriftError on first mismatch.

    Returns:
        List of warning messages describing mismatches or missing files.

    Raises:
        HandoffContextDriftError: When ``strict=True`` and a checksum
            mismatch, missing file, or read error is detected.
    """
    warnings = []
    
    for item in context_files:
        path_str = item.get("path")
        expected_checksum = item.get("checksum")
        
        if not path_str or not expected_checksum:
            continue
            
        path = Path(path_str)
        if not path.exists():
            msg = f"Context file missing: {path}"
            warnings.append(msg)
            if strict:
                raise HandoffContextDriftError(msg)
            continue
            
        try:
            content = path.read_bytes()
            actual_checksum = hashlib.sha256(content).hexdigest()
        except OSError as exc:
            msg = f"Failed to verify checksum for {path}: {exc}"
            warnings.append(msg)
            if strict:
                raise HandoffContextDriftError(msg) from exc
            continue

        if actual_checksum != expected_checksum:
            msg = f"Context drift detected for {path}: expected {expected_checksum[:8]}, got {actual_checksum[:8]}"
            warnings.append(msg)
            if strict:
                raise HandoffContextDriftError(msg)

    return warnings


def verify_source_checksum(handoff: HandoffData) -> str | None:
    """Verify the enriched seed file hasn't changed since the handoff was written.

    Compares the handoff's ``source_checksum`` against the current SHA-256 of
    the enriched seed file.

    Returns:
        Warning message if mismatch detected, ``None`` if OK or unable to verify.
    """
    if not handoff.source_checksum:
        return None

    seed_path = Path(handoff.enriched_seed_path) if handoff.enriched_seed_path else None
    if not seed_path or not seed_path.exists():
        return None

    try:
        current = hashlib.sha256(seed_path.read_bytes()).hexdigest()
    except OSError as exc:
        logger.debug("Failed to read %s for checksum verification: %s", seed_path, exc)
        return None

    if current != handoff.source_checksum:
        return (
            f"Source checksum drift: enriched seed {seed_path.name} changed since "
            f"design handoff (expected {handoff.source_checksum[:8]}…, "
            f"got {current[:8]}…)"
        )
    return None


def wrap_handoff_in_contract(
    handoff_data: HandoffData,
    project_id: str | None = None,
    trace_id: str | None = None
) -> HandoffContract | dict[str, Any]:
    """Wrap HandoffData in a HandoffContract.

    Args:
        handoff_data: The populated HandoffData object.
        project_id: Optional ContextCore project ID.
        trace_id: Optional trace ID.

    Returns:
        HandoffContract object (if contextcore installed) or dict.
    """
    inputs = {
        "enriched_seed_path": handoff_data.enriched_seed_path,
        "design_results": handoff_data.design_results,
        "scaffold": handoff_data.scaffold,
        "context_files": handoff_data.context_files,
        "workflow_id": handoff_data.workflow_id
    }
    
    # Contract fields
    contract_data = {
        "schema_version": "v1",
        "handoff_id": handoff_data.workflow_id,
        "project_id": project_id,
        "trace_id": trace_id,
        "parent_task_id": None,  # Could be passed in if available
        "from_agent": "artisan-design-half",
        "to_agent": "artisan-implement-half",
        "capability_id": "artisan.design-to-implement",
        "priority": "normal",
        "inputs": inputs,
        "expected_output": {
            "type": "implementation_artifacts",
            "schema_ref": "generation-manifest.json"
        },
        "status": "pending",
        "result_trace_id": None,
        "error": None,
        "created_at": datetime.now(timezone.utc),
        "deadline": None
    }
    
    if CONTEXTCORE_AVAILABLE:
        # Map strings to enums if needed, or rely on Pydantic casting
        # HandoffPriority.NORMAL, HandoffContractStatus.PENDING
        try:
            return HandoffContract(
                schema_version=contract_data["schema_version"],
                handoff_id=contract_data["handoff_id"],
                project_id=contract_data["project_id"],
                trace_id=contract_data["trace_id"],
                parent_task_id=contract_data["parent_task_id"],
                from_agent=contract_data["from_agent"],
                to_agent=contract_data["to_agent"],
                capability_id=contract_data["capability_id"],
                priority=HandoffPriority.NORMAL,
                inputs=contract_data["inputs"],
                expected_output=ExpectedOutput(**contract_data["expected_output"]),
                status=HandoffContractStatus.PENDING,
                created_at=contract_data["created_at"]
            )
        except (ValueError, TypeError) as e:
            logger.warning("Failed to create HandoffContract object: %s. Returning dict.", e)
            contract_data["created_at"] = contract_data["created_at"].isoformat()
            return contract_data
    else:
        # Fallback dict
        contract_data["created_at"] = contract_data["created_at"].isoformat()
        return contract_data


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
    source_checksum: str | None = None,
    design_mode_summary: dict[str, str] | None = None,
    shared_file_manifest: dict[str, list[str]] | None = None,
    project_manifest_summary: dict[str, Any] | None = None,
    design_structural_delta: dict[str, dict[str, list[dict[str, str]]]] | None = None,
    design_referenced_elements: dict[str, dict[str, list[str]]] | None = None,
    manifest_file_checksums: dict[str, str] | None = None,
    design_mode_evidence: dict[str, dict[str, Any]] | None = None,
    manifest_truncation_tier: dict[str, str] | None = None,
    design_quality: dict[str, Any] | None = None,
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
        artifact_manifest_path: Path to the artifact manifest (if any).
        project_context_path: Path to the project context file (if any).
        context_files: Context files the design was based on.
        example_artifacts: Example artifacts per type for IMPLEMENT (Item 9).
        coverage_gaps: Artifact types to generate first (Item 11).
        source_checksum: SHA-256 of the enriched seed file for provenance.
        design_mode_summary: Per-task edit mode classification (B-6).
        shared_file_manifest: Shared-file manifest (CCD-301).
        project_manifest_summary: Manifest summary stats (Phase 4).
        design_structural_delta: Per-task structural delta (Gap 3).
        design_referenced_elements: Per-task referenced elements (Gap 1).
        manifest_file_checksums: Per-file design-time checksums (Gap 2).
        design_mode_evidence: Per-task mode evidence (Gap 4).
        manifest_truncation_tier: Per-file truncation tiers (Gap 5).
        design_quality: DESIGN phase quality gate results.

    Returns:
        Path to the written handoff file.
    """
    # Item 12: Compute checksums for context files before handoff
    enriched_context_files = compute_context_checksums(context_files or [])

    # Compute source_checksum from enriched seed if not provided
    if source_checksum is None and enriched_seed_path:
        seed_path = Path(enriched_seed_path)
        if seed_path.exists() and seed_path.is_file():
            try:
                source_checksum = hashlib.sha256(
                    seed_path.read_bytes()
                ).hexdigest()
            except OSError as exc:
                logger.warning(
                    "Failed to compute source_checksum for %s: %s",
                    seed_path, exc,
                )

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
        context_files=enriched_context_files,
        example_artifacts=example_artifacts or {},
        coverage_gaps=coverage_gaps or [],
        design_mode_summary=design_mode_summary or {},
        shared_file_manifest=shared_file_manifest or {},
        source_checksum=source_checksum,
        project_manifest_summary=project_manifest_summary,
        design_structural_delta=design_structural_delta or {},
        design_referenced_elements=design_referenced_elements or {},
        manifest_file_checksums=manifest_file_checksums or {},
        design_mode_evidence=design_mode_evidence or {},
        manifest_truncation_tier=manifest_truncation_tier or {},
        design_quality=design_quality or {},
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
    
    # Item 11: Write contract file alongside handoff (best effort)
    try:
        contract = wrap_handoff_in_contract(handoff)
        contract_path = Path(output_dir) / DESIGN_HANDOFF_CONTRACT_FILENAME
        
        contract_dict = {}
        if hasattr(contract, "model_dump"):
            contract_dict = contract.model_dump(mode="json")
        elif isinstance(contract, dict):
            contract_dict = contract
            
        if contract_dict:
            atomic_write_json(contract_path, contract_dict, indent=2, default=str)
            logger.debug("Wrote design handoff contract: %s", contract_path)
            
    except (OSError, ValueError, TypeError) as e:
        logger.warning("Failed to write handoff contract: %s", e)

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
    if not isinstance(version, int):
        raise ValueError(
            f"Handoff 'schema_version' must be int, got {type(version).__name__}: {path}"
        )
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
        design_mode_summary=raw.get("design_mode_summary", {}),
        source_checksum=raw.get("source_checksum"),
        project_manifest_summary=raw.get("project_manifest_summary"),
        design_structural_delta=raw.get("design_structural_delta", {}),
        design_referenced_elements=raw.get("design_referenced_elements", {}),
        manifest_file_checksums=raw.get("manifest_file_checksums", {}),
        design_mode_evidence=raw.get("design_mode_evidence", {}),
        manifest_truncation_tier=raw.get("manifest_truncation_tier", {}),
        design_quality=raw.get("design_quality", {}),
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
