"""Exemplar extraction from successful Prime Contractor runs (REQ-PEP-000).

Reads postmortem reports and kaizen prompt archives to build ExemplarEntry
instances from features that scored 1.00 with full contract compliance.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from startd8.exemplars.models import (
    ConfigFingerprint,
    ExemplarEntry,
    ExemplarScores,
    _ext_to_language,
)
from startd8.exemplars.registry import ExemplarRegistry
from startd8.logging_config import get_logger

logger = get_logger(__name__)

__all__ = ["extract_exemplars_from_run"]


def extract_exemplars_from_run(
    run_dir: str | Path,
    *,
    registry: Optional[ExemplarRegistry] = None,
    min_requirement_score: float = 1.0,
    min_disk_quality_score: float = 1.0,
) -> List[ExemplarEntry]:
    """Extract proven exemplars from a completed Prime Contractor run.

    Scans the postmortem report for features meeting the score thresholds,
    then locates the corresponding kaizen prompt archives and generated code.

    Args:
        run_dir: Path to the run's output directory.
        registry: Optional registry to add exemplars to.  If None, exemplars
            are returned but not persisted.
        min_requirement_score: Minimum requirement_score to qualify.
        min_disk_quality_score: Minimum disk_quality_score to qualify.

    Returns:
        List of extracted ExemplarEntry instances.
    """
    run_path = Path(run_dir)
    run_id = run_path.name

    # Load postmortem report
    postmortem_path = run_path / "prime-postmortem-report.json"
    if not postmortem_path.is_file():
        logger.debug("No postmortem at %s, skipping", postmortem_path)
        return []

    try:
        report = json.loads(postmortem_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read postmortem %s: %s", postmortem_path, exc)
        return []

    # Load seed for fingerprint metadata
    seed_data = _load_seed(run_path)

    # Scan features
    features = report.get("features", [])
    extracted: List[ExemplarEntry] = []

    for fpm in features:
        feature_id = fpm.get("feature_id", "")
        req_score = fpm.get("requirement_score", 0.0)
        dq_score = fpm.get("disk_quality_score", 0.0)
        verdict = fpm.get("verdict", "")

        if req_score < min_requirement_score:
            continue
        if dq_score is not None and dq_score < min_disk_quality_score:
            continue
        if verdict and verdict.upper() != "PASS":
            continue

        entry = _extract_feature_exemplar(
            run_path, run_id, fpm, seed_data,
        )
        if entry:
            extracted.append(entry)
            if registry is not None:
                registry.add(entry)

    if extracted:
        logger.info(
            "Extracted %d exemplars from run %s (%d features scanned)",
            len(extracted), run_id, len(features),
        )

    return extracted


def _load_seed(run_path: Path) -> Dict[str, Any]:
    """Load the context seed for metadata extraction."""
    for name in ("prime-context-seed.json", "context-seed.json"):
        seed_path = run_path / name
        if seed_path.is_file():
            try:
                return json.loads(seed_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.debug("Failed to load seed %s: %s", seed_path, exc)
    return {}


def _extract_feature_exemplar(
    run_path: Path,
    run_id: str,
    fpm: Dict[str, Any],
    seed_data: Dict[str, Any],
) -> Optional[ExemplarEntry]:
    """Extract a single exemplar from a passing feature."""
    feature_id = fpm.get("feature_id", "")
    target_files = fpm.get("target_files", [])

    if not target_files:
        return None

    # Use first target file for fingerprint (primary file)
    primary_file = target_files[0]

    # Determine transport from seed task metadata
    transport = _infer_transport(feature_id, seed_data)

    # Determine language from seed or file extension
    language = _infer_language(feature_id, seed_data, primary_file)

    # Compute fingerprint
    fingerprint = ConfigFingerprint.compute(
        primary_file,
        language=language,
        transport=transport,
    )

    # Locate artifacts
    spec_path = _find_artifact(run_path, feature_id, "spec")
    code_path = _find_code_artifact(run_path, feature_id, fpm)
    draft_path = _find_artifact(run_path, feature_id, "draft")

    if not code_path:
        logger.debug("No code artifact for %s in %s", feature_id, run_path)
        return None

    # Compute seed task digest
    seed_digest = _compute_seed_digest(feature_id, seed_data)

    # Read code summary (first 50 lines) — code_path is guaranteed non-empty here
    code_summary = _read_code_summary(run_path / code_path)

    # Build scores
    scores = ExemplarScores(
        requirement_score=fpm.get("requirement_score", 0.0),
        disk_quality_score=fpm.get("disk_quality_score", 0.0),
        assembly_delta=fpm.get("assembly_delta", 0.0) or 0.0,
        semantic_error_count=fpm.get("semantic_error_count", 0),
        cost_usd=fpm.get("cost_usd", 0.0),
    )

    entry_id = ExemplarEntry.make_id(fingerprint, run_id, feature_id)

    return ExemplarEntry(
        id=entry_id,
        fingerprint=fingerprint,
        maturity=1,  # Validated (REQ-PEP-000 §4)
        source_run_id=run_id,
        source_feature_id=feature_id,
        spec_artifact_path=spec_path or "",
        code_artifact_path=code_path or "",
        draft_artifact_path=draft_path or "",
        seed_task_digest=seed_digest,
        scores=scores,
        agent_specs=_extract_agent_specs(run_path, feature_id),
        code_summary=code_summary,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def _infer_transport(feature_id: str, seed_data: Dict[str, Any]) -> str:
    """Infer transport protocol from seed task metadata."""
    for task in seed_data.get("tasks", []):
        if task.get("task_id") == feature_id or task.get("feature_id") == feature_id:
            config = task.get("config", {})
            context = config.get("context", {})
            svc_meta = context.get("service_metadata", {})
            proto = svc_meta.get("transport_protocol", "")
            if proto:
                return proto.lower()
            # Check protocol field
            proto_field = task.get("protocol", "") or config.get("protocol", "")
            if "grpc" in proto_field.lower():
                return "grpc"
            if "http" in proto_field.lower():
                return "http"
    return "none"


def _infer_language(feature_id: str, seed_data: Dict[str, Any], primary_file: str) -> str:
    """Infer language from seed task or file extension."""
    for task in seed_data.get("tasks", []):
        if task.get("task_id") == feature_id or task.get("feature_id") == feature_id:
            lang = task.get("language", "")
            if lang:
                return lang.lower()
    # Fallback to extension
    return _ext_to_language(Path(primary_file).suffix.lower())


def _find_artifact(run_path: Path, feature_id: str, artifact_type: str) -> Optional[str]:
    """Find an artifact by type in the kaizen prompt archive or .artifacts."""
    # Try kaizen prompt archive
    kaizen_dir = run_path / "kaizen-prompts" / "standalone" / feature_id
    if kaizen_dir.is_dir():
        for f in sorted(kaizen_dir.iterdir()):
            if artifact_type in f.name.lower() and f.suffix in (".md", ".txt"):
                return str(f.relative_to(run_path))

    # Try .artifacts directory
    artifacts_dir = run_path / "generated" / ".artifacts"
    if artifacts_dir.is_dir():
        for f in sorted(artifacts_dir.iterdir()):
            if feature_id.replace("-", "").lower() in f.name.replace("-", "").lower():
                if artifact_type in f.name.lower():
                    return str(f.relative_to(run_path))

    return None


def _find_code_artifact(
    run_path: Path, feature_id: str, fpm: Dict[str, Any],
) -> Optional[str]:
    """Find the generated code file for a feature."""
    generated_files = fpm.get("generated_files", [])
    if generated_files:
        # Return first generated file as relative path
        for gf in generated_files:
            gf_path = Path(gf)
            # Try as relative to run_path
            if (run_path / gf_path).is_file():
                return str(gf_path)
            # Try under generated/
            gen_path = run_path / "generated" / gf_path
            if gen_path.is_file():
                return str(gen_path.relative_to(run_path))
        # Return first as-is even if not found on disk
        return generated_files[0]

    # Try kaizen draft response
    kaizen_dir = run_path / "kaizen-prompts" / "standalone" / feature_id
    if kaizen_dir.is_dir():
        for f in sorted(kaizen_dir.iterdir()):
            if "draft" in f.name.lower() and "response" in f.name.lower():
                return str(f.relative_to(run_path))

    return None


def _compute_seed_digest(feature_id: str, seed_data: Dict[str, Any]) -> str:
    """Compute SHA-256 digest of the seed task's forward manifest entry."""
    for task in seed_data.get("tasks", []):
        if task.get("task_id") == feature_id or task.get("feature_id") == feature_id:
            config = task.get("config", {})
            # Hash the implementation contract / forward manifest section
            contract = config.get("forward_manifest", config.get("implementation_contract", {}))
            return hashlib.sha256(
                json.dumps(contract, sort_keys=True, default=str).encode()
            ).hexdigest()[:16]
    return ""


def _extract_agent_specs(run_path: Path, feature_id: str) -> Dict[str, str]:
    """Extract agent specs (lead/drafter) from metadata."""
    metadata_path = (
        run_path / "kaizen-prompts" / "standalone" / feature_id / "metadata.json"
    )
    if metadata_path.is_file():
        try:
            meta = json.loads(metadata_path.read_text(encoding="utf-8"))
            return {
                "lead": meta.get("lead_agent", meta.get("agent_spec", "")),
                "drafter": meta.get("drafter_agent", meta.get("drafter_spec", "")),
            }
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("Failed to read agent metadata %s: %s", metadata_path, exc)
    return {}


def _read_code_summary(code_path: Path, max_lines: int = 50) -> str:
    """Read first N lines of a code file for preview."""
    if not code_path.is_file():
        return ""
    try:
        text = code_path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()[:max_lines]
        return "\n".join(lines)
    except OSError:
        return ""
