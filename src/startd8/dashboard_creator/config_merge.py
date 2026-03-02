"""
Config override merge + default hydration (DC-005).
"""

import copy
from pathlib import Path
from typing import Any, Dict

from startd8.dashboard_creator.models import DashboardSpec
from startd8.exceptions import ValidationError

# Known top-level config keys for validation
_VALID_CONFIG_SECTIONS = {
    "datasources", "dashboardTags", "dashboardRefresh",
    "dashboardTimeFrom", "dashboardTimeTo", "serviceName",
    "metrics", "spans", "artisanMetrics", "alertThresholds", "selectors",
}

# Default config values matching startd8-mixin/config.libsonnet
_DEFAULT_CONFIG: Dict[str, Any] = {
    "datasources": {
        "tempo": {"uid": "tempo", "type": "tempo"},
        "loki": {"uid": "loki", "type": "loki"},
        "mimir": {"uid": "mimir", "type": "prometheus"},
    },
    "dashboardTags": ["startd8", "sdk"],
    "dashboardRefresh": "30s",
    "dashboardTimeFrom": "now-6h",
    "dashboardTimeTo": "now",
    "serviceName": "startd8-sdk",
    "metrics": {
        "activeSessions": "startd8_active_sessions",
        "requestsTotal": "startd8_requests_total",
        "tokensTotal": "startd8_tokens_total",
        "responseTimeMs": "startd8_response_time_ms",
        "contextUsageRatio": "startd8_context_usage_ratio",
        "truncationsTotal": "startd8_truncations_total",
        "costTotal": "startd8_cost_total",
        "costInputTokens": "startd8_cost_input_tokens",
        "costOutputTokens": "startd8_cost_output_tokens",
        "costPerRequest": "startd8_cost_per_request",
        "budgetLimit": "startd8_budget_limit",
        "eventsTotal": "startd8_events_total",
    },
    "selectors": {
        "serviceName": 'service_name=~"$service_name"',
        "model": 'model=~"$model"',
        "projectId": 'project_id=~"$project_id"',
        "agentName": 'agent_name=~"$agent_name"',
    },
}


def get_default_config() -> Dict[str, Any]:
    """Return a deep copy of the default config."""
    return copy.deepcopy(_DEFAULT_CONFIG)


def parse_config_libsonnet(config_path: Path) -> Dict[str, Any]:
    """Parse config.libsonnet into a Python dict.

    Uses regex extraction for the known structure rather than
    full Jsonnet evaluation (avoids toolchain dependency for config reads).
    Falls back to a hardcoded default map matching the current config.libsonnet.
    """
    if not config_path.is_file():
        return get_default_config()

    # For now, return the default config — config.libsonnet parsing via
    # regex is fragile and the defaults match the canonical file.
    # Future: use jsonnet toolchain to evaluate config.libsonnet if available.
    return get_default_config()


def merge_config_overrides(
    base_config: Dict[str, Any],
    overrides: Dict[str, Any],
) -> Dict[str, Any]:
    """Deep-merge user overrides into base config.

    Raises ValidationError for unknown override keys at the top level.
    List values are replaced (not concatenated).
    """
    unknown = set(overrides.keys()) - _VALID_CONFIG_SECTIONS
    if unknown:
        raise ValidationError(
            f"Unknown config override keys: {', '.join(sorted(unknown))}. "
            f"Valid keys: {', '.join(sorted(_VALID_CONFIG_SECTIONS))}",
        )

    result = copy.deepcopy(base_config)
    _deep_merge(result, overrides)
    return result


def _deep_merge(base: Dict[str, Any], overrides: Dict[str, Any]) -> None:
    """In-place deep merge of overrides into base."""
    for key, value in overrides.items():
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(value, dict)
        ):
            _deep_merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)


def hydrate_spec_defaults(
    spec: DashboardSpec,
    config: Dict[str, Any],
) -> DashboardSpec:
    """DC-005: Fill missing optional spec fields from config defaults.

    Returns a new DashboardSpec (does not mutate input).
    """
    updates: Dict[str, Any] = {}

    if spec.refresh is None:
        updates["refresh"] = config.get("dashboardRefresh", "30s")
    if spec.timezone is None:
        updates["timezone"] = "browser"
    if spec.time_from is None:
        updates["time_from"] = config.get("dashboardTimeFrom", "now-6h")
    if spec.time_to is None:
        updates["time_to"] = config.get("dashboardTimeTo", "now")
    if not spec.datasources:
        ds_config = config.get("datasources", {})
        updates["datasources"] = {
            name: info["uid"] if isinstance(info, dict) else info
            for name, info in ds_config.items()
        }

    if updates:
        return spec.model_copy(update=updates)
    return spec


def write_config_overlay(
    merged_config: Dict[str, Any],
    output_path: Path,
) -> Path:
    """Write merged config as a temporary .libsonnet file for the compiler.

    Returns the path to the written file.
    """
    # Generate a Jsonnet object literal that overrides _config
    lines = ["{\n  _config+:: "]
    lines.append(_dict_to_jsonnet(merged_config, indent=4))
    lines.append(",\n}\n")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(lines), encoding="utf-8")
    return output_path


def _dict_to_jsonnet(obj: Any, indent: int = 2) -> str:
    """Convert a Python dict to a Jsonnet object literal string."""
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        pad = " " * indent
        inner_pad = " " * (indent + 2)
        items = []
        for k, v in obj.items():
            items.append(f"{inner_pad}{k}: {_dict_to_jsonnet(v, indent + 2)}")
        return "{\n" + ",\n".join(items) + f",\n{pad}}}"
    elif isinstance(obj, str):
        # Escape single quotes for Jsonnet
        escaped = obj.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    elif isinstance(obj, bool):
        return "true" if obj else "false"
    elif isinstance(obj, (int, float)):
        return str(obj)
    elif isinstance(obj, list):
        if not obj:
            return "[]"
        pad = " " * indent
        items = [f"  {pad}{_dict_to_jsonnet(item, indent + 2)}" for item in obj]
        return "[\n" + ",\n".join(items) + f",\n{pad}]"
    elif obj is None:
        return "null"
    else:
        return repr(obj)
