"""Live, offline Perses generation from the first neutral production source."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from ...observability.dashboard_renderer_v2 import build_domain_dashboard_neutral
from ...observability.spec import from_observability_yaml
from .emitter import emit_perses_dashboard, perses_json

_DEFAULT_OUTPUT_DIR = Path(".startd8/dashboards")
_PROJECT_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


@dataclass(frozen=True)
class PersesGenerationResult:
    """Validated candidate plus its optional persisted path."""

    dashboard: Dict[str, Any]
    json_text: str
    output_path: Optional[Path]

    @property
    def name(self) -> str:
        return str(self.dashboard["metadata"]["name"])


def generate_domain_perses_dashboard(
    spec_path: Path,
    *,
    project: str = "default",
    output_dir: Optional[Path] = None,
    check: bool = False,
    dry_run: bool = False,
) -> PersesGenerationResult:
    """Parse, lower, validate, and optionally persist one domain dashboard.

    Validation is mandatory. ``--check`` and ``--dry-run`` callers receive the exact canonical
    candidate bytes but never touch the output path.
    """

    if check and dry_run:
        raise ValueError("Cannot use both --dry-run and --check together")
    if not _PROJECT_RE.fullmatch(project):
        raise ValueError(
            "--project must be a lowercase identifier containing only letters, digits, and hyphens"
        )

    loaded = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    observability = from_observability_yaml(loaded)
    neutral = build_domain_dashboard_neutral(
        observability,
        project,
        explicit_grid=True,
        datasource_name="default",
    )
    dashboard = emit_perses_dashboard(neutral, project=project, validate=True)
    json_text = perses_json(dashboard)

    output_path: Optional[Path] = None
    if not check and not dry_run:
        resolved_output = output_dir or _DEFAULT_OUTPUT_DIR
        resolved_output.mkdir(parents=True, exist_ok=True)
        output_path = resolved_output / f"{neutral.name}.perses.json"
        temporary = output_path.with_name(output_path.name + ".tmp")
        temporary.write_text(json_text, encoding="utf-8")
        os.replace(temporary, output_path)

    return PersesGenerationResult(
        dashboard=dashboard,
        json_text=json_text,
        output_path=output_path,
    )
