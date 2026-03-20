"""Security allowlist — operator-declared false positive suppression.

Loads ``security_allowlist.yaml`` from the project root and filters
findings before verdict computation. Suppressed findings are preserved
with ``suppressed=True`` for forensic review.

Schema::

    entries:
      - file_pattern: "**/*SpannerCartStore.cs"
        check_id: "injection"
        justification: "Spanner uses parameterized queries via SpannerParameterCollection"
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any, Dict, List, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)


def load_allowlist(project_root: str) -> List[Dict[str, str]]:
    """Load security allowlist entries from project root.

    Args:
        project_root: Project root directory path.

    Returns:
        List of allowlist entry dicts, each with file_pattern, check_id,
        and justification. Empty list if file not found or parse error.
    """
    path = Path(project_root) / "security_allowlist.yaml"
    if not path.is_file():
        return []

    try:
        import yaml
    except ImportError:
        logger.debug("PyYAML not available — skipping allowlist")
        return []

    try:
        data = yaml.safe_load(path.read_text())
    except Exception as exc:
        logger.warning("Failed to parse security_allowlist.yaml: %s", exc)
        return []

    if not isinstance(data, dict):
        return []

    entries = data.get("entries", [])
    if not isinstance(entries, list):
        return []

    valid: List[Dict[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if "file_pattern" in entry and "check_id" in entry:
            valid.append({
                "file_pattern": str(entry["file_pattern"]),
                "check_id": str(entry["check_id"]),
                "justification": str(entry.get("justification", "")),
            })

    if valid:
        logger.info("Loaded %d security allowlist entries", len(valid))
    return valid


def is_allowlisted(
    file_path: str,
    check_type: str,
    allowlist: List[Dict[str, str]],
) -> Optional[str]:
    """Check if a finding is suppressed by the allowlist.

    Args:
        file_path: Path to the file with the finding.
        check_type: The check type string (e.g. "injection").
        allowlist: Loaded allowlist entries.

    Returns:
        Justification string if allowlisted, None otherwise.
    """
    for entry in allowlist:
        if entry["check_id"] != check_type:
            continue
        if fnmatch.fnmatch(file_path, entry["file_pattern"]):
            return entry.get("justification", "allowlisted")
    return None
