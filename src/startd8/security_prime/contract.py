"""Security contract derivation — SP-PL-010 through SP-PL-012.

Derives a security contract from ``.contextcore.yaml`` ``spec.security``
when available, falling back to ``query_prime.decomposer.detect_database_type()``
for auto-detection from plan/task metadata.

The contract is a plain dict suitable for ``gen_context`` forwarding and
JSON serialization.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)


def derive_security_contract(
    manifest_path: Optional[str] = None,
    plan_text: Optional[str] = None,
    feature_descriptions: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Derive a security contract from available pipeline context.

    Tries sources in priority order:
    1. ``.contextcore.yaml`` ``spec.security.data_stores`` (richest)
    2. Plan text — scan for database keywords (medium fidelity)
    3. Feature descriptions — scan for database keywords (lowest fidelity)

    Returns None if no database surface is detected.

    Args:
        manifest_path: Path to ``.contextcore.yaml`` file.
        plan_text: Raw plan markdown text.
        feature_descriptions: List of feature description strings.

    Returns:
        Security contract dict with per-database entries, or None.
    """
    # Source 1: .contextcore.yaml spec.security
    if manifest_path:
        contract = _derive_from_manifest(manifest_path)
        if contract:
            logger.info(
                "Security contract derived from .contextcore.yaml (%d data stores)",
                len(contract.get("databases", {})),
            )
            return contract

    # Source 2+3: Auto-detect from text
    text_sources: List[str] = []
    if plan_text:
        text_sources.append(plan_text)
    if feature_descriptions:
        text_sources.extend(feature_descriptions)

    if text_sources:
        contract = _derive_from_text(" ".join(text_sources))
        if contract:
            logger.info(
                "Security contract auto-derived from plan/feature text (database=%s)",
                contract.get("database", "unknown"),
            )
            return contract

    return None


def _derive_from_manifest(manifest_path: str) -> Optional[Dict[str, Any]]:
    """Parse .contextcore.yaml spec.security section."""
    path = Path(manifest_path)
    if not path.is_file():
        return None

    try:
        import yaml
    except ImportError:
        logger.debug("PyYAML not available — skipping manifest-based contract derivation")
        return None

    try:
        data = yaml.safe_load(path.read_text())
    except Exception as exc:
        logger.warning("Failed to parse %s: %s", manifest_path, exc)
        return None

    if not isinstance(data, dict):
        return None

    spec = data.get("spec", {})
    security = spec.get("security", {})
    if not security:
        return None

    data_stores = security.get("data_stores", [])
    if not data_stores:
        return None

    # Build per-database contract entries
    databases: Dict[str, Dict[str, Any]] = {}
    for store in data_stores:
        if not isinstance(store, dict):
            continue
        db_id = store.get("id") or store.get("type", "unknown")
        databases[db_id] = {
            "client_library": store.get("client_library", ""),
            "credential_source": store.get("credential_source", ""),
            "type": store.get("type", db_id),
        }

        # Enrich with safe patterns from query_prime registry
        _enrich_from_registry(databases[db_id], db_id)

    sensitivity = security.get("sensitivity", "medium")

    return {
        "databases": databases,
        "sensitivity": sensitivity,
        "source": "manifest",
        # For backward compat with existing spec_builder P0 injection:
        "database": next(iter(databases), ""),
        "safe_pattern_example": _first_safe_example(databases),
    }


def _derive_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Auto-detect database type from text content."""
    try:
        from startd8.query_prime.decomposer import detect_database_type
    except ImportError:
        return None

    db_type = detect_database_type(text)
    if db_type is None:
        return None

    db_name = db_type.value
    entry: Dict[str, Any] = {"type": db_name, "client_library": ""}
    _enrich_from_registry(entry, db_name)

    return {
        "databases": {db_name: entry},
        "sensitivity": "medium",
        "source": "auto-detect",
        "database": db_name,
        "safe_pattern_example": entry.get("safe_param_syntax", "parameterized queries"),
    }


def _enrich_from_registry(entry: Dict[str, Any], db_id: str) -> None:
    """Add safe_param_syntax from DatabasePatternRegistry if available."""
    try:
        from startd8.query_prime.patterns import DatabasePatternRegistry
    except ImportError:
        return

    # Try common languages to find any registered pattern
    for lang in ("csharp", "python", "go", "java", "nodejs"):
        pattern = DatabasePatternRegistry.get(db_id, lang)
        if pattern and pattern.safe_param_syntax:
            entry["safe_param_syntax"] = pattern.safe_param_syntax[0]
            entry.setdefault("client_library", pattern.client_library)
            break


def _first_safe_example(databases: Dict[str, Dict[str, Any]]) -> str:
    """Get first available safe pattern example for P0 constraint text."""
    for db_entry in databases.values():
        example = db_entry.get("safe_param_syntax")
        if example:
            return example
    return "parameterized queries"
