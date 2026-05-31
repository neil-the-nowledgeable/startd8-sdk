"""
Artifact inventory consumer for the pipeline provenance system.

Loads, queries, and extends the typed ``artifact_inventory`` section of
``run-provenance.json``.  Implements the Mottainai Design Principle by
letting downstream pipeline stages discover and reuse artifacts produced
by earlier stages instead of regenerating them.

Usage::

    from startd8.utils.artifact_inventory import load_inventory, lookup_artifact

    inventory = load_inventory(output_dir)
    entry, outcome = lookup_artifact(inventory, "derivation_rules")
    if entry:
        data = load_artifact_content(entry, output_dir)
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

logger = logging.getLogger(__name__)

# Type alias for lookup outcomes
LookupOutcome = Literal["hit", "miss", "stale"]


# Observability manifest descriptor — consumed by generate_manifest(), zero runtime
# cost. The instrument is lazily created inside _emit_lookup_metric(); this static
# declaration mirrors it for the descriptor↔emission parity test. Module-level
# taxonomy defaults (REQ-OBS-SHARED-001): artifact-inventory reuse metrics are innate
# codegen-pipeline mechanics, system-oriented.
_OTEL_DESCRIPTORS = {
    "category": "pipeline_innate",
    "orientation": "system",
    "metrics": [
        {
            "name": "pipeline.artifact_inventory.lookup",
            "instrument": "counter",
            "unit": "1",
            "description": "Artifact inventory lookup outcomes",
            "meter": "startd8.pipeline",
            "labels": ["role", "outcome"],
        },
    ],
}


# ---------------------------------------------------------------------------
# OTel metric helper (guarded)
# ---------------------------------------------------------------------------

def _emit_lookup_metric(role: str, outcome: str) -> None:
    """Emit an OTel counter metric for an inventory lookup.

    Guarded by ``try/except ImportError`` so environments without OTel
    are unaffected.
    """
    try:
        from opentelemetry import metrics

        meter = metrics.get_meter("startd8.pipeline")
        counter = meter.create_counter(
            "pipeline.artifact_inventory.lookup",
            description="Artifact inventory lookup outcomes",
        )
        counter.add(1, {"role": role, "outcome": outcome})
    except (ImportError, Exception):
        pass  # OTel not available — silently skip


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_inventory(output_dir: str | Path) -> List[Dict[str, Any]]:
    """Load the artifact inventory from ``run-provenance.json``.

    Returns the ``artifact_inventory`` list, or ``[]`` when:
    - The file is missing or malformed.
    - The schema is v1 (no inventory section).

    Never raises — graceful degradation is a hard requirement.
    """
    prov_path = Path(output_dir) / "run-provenance.json"
    if not prov_path.exists():
        logger.debug("artifact_inventory: run-provenance.json not found in %s", output_dir)
        return []

    try:
        with open(prov_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("artifact_inventory: failed to parse run-provenance.json: %s", exc)
        return []

    if not isinstance(data, dict):
        return []

    version = data.get("version", "1.0.0")
    if version.startswith("1."):
        logger.debug("artifact_inventory: v1 schema — no inventory section")
        return []

    inventory = data.get("artifact_inventory")
    if not isinstance(inventory, list):
        return []

    return inventory


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

def lookup_artifact(
    inventory: List[Dict[str, Any]],
    role: str,
    *,
    verify_freshness: bool = False,
    source_dir: str | Path | None = None,
) -> Tuple[Optional[Dict[str, Any]], LookupOutcome]:
    """Look up an artifact by role in the inventory.

    Args:
        inventory: The artifact inventory list.
        role: Semantic role to search for (e.g. ``"derivation_rules"``).
        verify_freshness: If ``True``, recompute source checksum and compare.
        source_dir: Base directory for resolving freshness source paths.

    Returns:
        ``(entry, outcome)`` where outcome is ``"hit"``, ``"miss"``, or
        ``"stale"``.  On miss, entry is ``None``.
    """
    for entry in inventory:
        if entry.get("role") == role:
            # Check freshness if requested
            if verify_freshness and source_dir:
                freshness = entry.get("freshness", {})
                src_file = freshness.get("source_file")
                expected_checksum = freshness.get("source_checksum")
                if src_file and expected_checksum:
                    src_path = Path(source_dir) / src_file
                    if src_path.exists():
                        actual = _sha256_file(src_path)
                        if actual and actual != expected_checksum:
                            logger.warning(
                                "mottainai.fallback: %s is stale "
                                "(source_checksum mismatch: %s vs %s)",
                                role, expected_checksum[:12], actual[:12],
                            )
                            _emit_lookup_metric(role, "stale")
                            return entry, "stale"

            logger.info("mottainai.reuse: %s found in artifact inventory", role)
            _emit_lookup_metric(role, "hit")
            return entry, "hit"

    logger.warning(
        "mottainai.fallback: %s not found in artifact inventory — "
        "falling back to LLM generation",
        role,
    )
    _emit_lookup_metric(role, "miss")
    return None, "miss"


# ---------------------------------------------------------------------------
# Content loader
# ---------------------------------------------------------------------------

def load_artifact_content(
    entry: Dict[str, Any],
    output_dir: str | Path,
) -> Any:
    """Load the actual artifact content referenced by an inventory entry.

    Reads ``source_file`` from ``output_dir`` and optionally extracts a
    sub-document via ``json_path`` (simplified: supports ``$.key`` syntax).

    Returns ``None`` on any failure (file missing, parse error, key missing).
    """
    source_file = entry.get("source_file", "")
    if not source_file:
        return None

    file_path = Path(output_dir) / source_file
    if not file_path.exists():
        logger.debug("artifact_inventory: source file not found: %s", file_path)
        return None

    try:
        with open(file_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("artifact_inventory: failed to load %s: %s", file_path, exc)
        return None

    json_path = entry.get("json_path")
    if json_path:
        return _extract_json_path(data, json_path)

    return data


def _extract_json_path(data: Any, json_path: str) -> Any:
    """Extract a value from data using a simplified JSONPath expression.

    Supports ``$.key`` and ``$.key1.key2`` dot-notation paths.
    Returns ``None`` if any key is missing.
    """
    if not json_path.startswith("$."):
        return data

    keys = json_path[2:].split(".")
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


# ---------------------------------------------------------------------------
# Extend (read-extend-write)
# ---------------------------------------------------------------------------

def extend_inventory(
    output_dir: str | Path,
    new_entries: List[Dict[str, Any]],
) -> bool:
    """Extend the artifact inventory in ``run-provenance.json``.

    Reads the existing provenance file, appends ``new_entries`` to the
    inventory (deduplicating by ``artifact_id``), and writes back atomically.

    Returns ``True`` on success, ``False`` on failure.
    """
    prov_path = Path(output_dir) / "run-provenance.json"

    # Load existing provenance
    provenance: Dict[str, Any] = {}
    if prov_path.exists():
        try:
            with open(prov_path, encoding="utf-8") as fh:
                provenance = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "artifact_inventory: failed to load existing provenance: %s", exc
            )
            return False

    # Ensure we have a v2 structure
    if provenance.get("version", "1.0.0").startswith("1."):
        provenance["version"] = "2.0.0"

    existing = provenance.get("artifact_inventory", [])
    if not isinstance(existing, list):
        existing = []

    # Deduplicate: existing entries take precedence for same artifact_id,
    # new entries replace existing ones with same artifact_id
    existing_ids = {e.get("artifact_id") for e in existing}
    for entry in new_entries:
        aid = entry.get("artifact_id")
        if aid and aid not in existing_ids:
            existing.append(entry)
            existing_ids.add(aid)

    provenance["artifact_inventory"] = existing

    # Atomic write
    try:
        from startd8.utils.file_operations import atomic_write_json

        atomic_write_json(prov_path, provenance, indent=2)
    except ImportError:
        # Fallback: direct write if file_operations not available
        try:
            prov_path.parent.mkdir(parents=True, exist_ok=True)
            with open(prov_path, "w", encoding="utf-8") as fh:
                json.dump(provenance, fh, indent=2, default=str)
        except OSError as exc:
            logger.warning("artifact_inventory: failed to write provenance: %s", exc)
            return False

    logger.info(
        "artifact_inventory: extended inventory with %d entries (total: %d)",
        len(new_entries), len(existing),
    )
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> Optional[str]:
    """Compute SHA-256 hex digest of a file."""
    if not path.exists():
        return None
    hasher = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except OSError:
        return None
