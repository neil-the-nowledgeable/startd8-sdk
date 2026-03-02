"""
Compiled dashboard JSON validation (DC-106).
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_REQUIRED_KEYS = {"title", "uid", "panels", "templating", "schemaVersion"}
_SUPPORTED_SCHEMA_VERSIONS = range(36, 42)  # 36–41; pinned to grafonnet


@dataclass
class JsonValidationResult:
    """Result of compiled JSON validation."""

    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    dashboard_json: Dict[str, Any] = field(default_factory=dict)


def validate_dashboard_json(
    json_str: str,
    expected_uid: str,
    expected_panel_count: Optional[int] = None,
) -> JsonValidationResult:
    """DC-106: Validate compiled JSON against Grafana dashboard requirements.

    Checks:
    1. JSON is parseable
    2. Required top-level keys present (title, uid, panels, templating, schemaVersion)
    3. uid matches expected_uid
    4. schemaVersion in supported range (warning, not error)
    5. panels is a list
    6. Panel count matches expected (excluding auto-generated rows)
    """
    errors: List[str] = []
    warnings: List[str] = []

    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, TypeError) as exc:
        return JsonValidationResult(
            valid=False,
            errors=[f"Invalid JSON: {exc}"],
        )

    if not isinstance(data, dict):
        return JsonValidationResult(
            valid=False,
            errors=["JSON root must be an object"],
        )

    # Required keys
    missing = _REQUIRED_KEYS - set(data.keys())
    if missing:
        errors.append(f"Missing required keys: {', '.join(sorted(missing))}")

    # UID match
    actual_uid = data.get("uid")
    if actual_uid is not None and actual_uid != expected_uid:
        errors.append(
            f"UID mismatch: expected '{expected_uid}', got '{actual_uid}'"
        )

    # Schema version (advisory)
    schema_version = data.get("schemaVersion")
    if schema_version is not None and schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
        warnings.append(
            f"Unsupported schemaVersion {schema_version} "
            f"(expected {_SUPPORTED_SCHEMA_VERSIONS.start}–{_SUPPORTED_SCHEMA_VERSIONS.stop - 1})"
        )

    # Panels is a list
    panels = data.get("panels")
    if panels is not None and not isinstance(panels, list):
        errors.append(f"'panels' must be a list, got {type(panels).__name__}")

    # Panel count (excluding auto-generated rows)
    if (
        expected_panel_count is not None
        and isinstance(panels, list)
    ):
        actual_count = sum(
            1 for p in panels
            if not (isinstance(p, dict) and p.get("type") == "row")
        )
        if actual_count != expected_panel_count:
            errors.append(
                f"Panel count mismatch: expected {expected_panel_count}, "
                f"got {actual_count} (excluding rows)"
            )

    return JsonValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        dashboard_json=data if isinstance(data, dict) else {},
    )
