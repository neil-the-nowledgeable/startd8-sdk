"""Task enrichment for security-sensitive tasks — SP-PL-001 through SP-PL-002.

Tags tasks with ``security_sensitive`` and ``detected_database`` during
plan ingestion or standalone context assembly.  Reuses
``query_prime.decomposer.detect_database_type()`` — no new detection logic.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)


def enrich_security_fields(
    feature_description: str,
    target_files: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Detect database surface and return security enrichment fields.

    Returns a dict of fields to merge into ``gen_context``:
    - ``security_sensitive``: bool
    - ``detected_database``: str or None

    Args:
        feature_description: Feature or task description text.
        target_files: Optional target file paths.
        metadata: Optional feature metadata dict.

    Returns:
        Dict with security fields (always present; ``security_sensitive``
        may be False if no database detected).
    """
    try:
        from startd8.query_prime.decomposer import detect_database_type
    except ImportError:
        return {"security_sensitive": False, "detected_database": None}

    # Build search text from all available sources
    parts = [feature_description]
    if metadata:
        parts.extend(str(v) for v in metadata.values() if isinstance(v, str))
    if target_files:
        parts.extend(target_files)

    text = " ".join(parts)
    db_type = detect_database_type(text)

    if db_type is None:
        return {"security_sensitive": False, "detected_database": None}

    logger.info(
        "Security enrichment: detected database=%s from task content",
        db_type.value,
    )
    return {
        "security_sensitive": True,
        "detected_database": db_type.value,
    }


def enrich_gen_context(
    gen_context: Dict[str, Any],
    feature_description: str,
    target_files: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Enrich a gen_context dict with security fields in-place.

    Convenience wrapper that calls ``enrich_security_fields()`` and merges
    the result into the provided ``gen_context`` dict.

    Args:
        gen_context: Mutable context dict to enrich.
        feature_description: Feature/task description.
        target_files: Optional target file paths.
        metadata: Optional feature metadata.
    """
    fields = enrich_security_fields(feature_description, target_files, metadata)
    gen_context.update(fields)
