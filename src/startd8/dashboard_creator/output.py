"""
Dashboard output persistence (DC-107).

Deterministic JSON output: json.dumps(sort_keys=True, indent=2) + trailing newline.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


_DEFAULT_OUTPUT_DIR = ".startd8/dashboards"


@dataclass
class PersistenceResult:
    """Result of dashboard file persistence."""

    json_path: Path
    libsonnet_path: Optional[Path] = None


def persist_dashboard(
    dashboard_json: Dict[str, Any],
    uid: str,
    output_dir: Optional[Path] = None,
    libsonnet_source: Optional[str] = None,
    libsonnet_dir: Optional[Path] = None,
) -> PersistenceResult:
    """DC-107: Write dashboard JSON + optional .libsonnet source.

    - JSON -> {output_dir}/{uid}.json  (default: .startd8/dashboards/)
    - Libsonnet -> {libsonnet_dir}/{name}.libsonnet  (default: None, opt-in)
    - Deterministic: json.dumps(sort_keys=True, indent=2) + trailing newline
    - Creates parent dirs if needed
    - Upsert semantics (overwrites existing)
    """
    resolved_output = output_dir or Path(_DEFAULT_OUTPUT_DIR)
    resolved_output.mkdir(parents=True, exist_ok=True)

    json_path = resolved_output / f"{uid}.json"
    json_content = json.dumps(dashboard_json, sort_keys=True, indent=2) + "\n"
    json_path.write_text(json_content, encoding="utf-8")

    libsonnet_path = None
    if libsonnet_source is not None and libsonnet_dir is not None:
        libsonnet_dir.mkdir(parents=True, exist_ok=True)
        # Derive filename from uid: strip "cc-startd8-" or "cc-" prefix,
        # then convert hyphens to underscores for valid Jsonnet identifiers.
        name = uid.replace("cc-startd8-", "").replace("cc-", "")
        name = name.replace("-", "_")
        libsonnet_path = libsonnet_dir / f"{name}.libsonnet"
        libsonnet_path.write_text(libsonnet_source, encoding="utf-8")

    return PersistenceResult(json_path=json_path, libsonnet_path=libsonnet_path)
