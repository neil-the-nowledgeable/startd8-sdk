"""Project-context enrichment for the Service Assistant (FR-5).

Best-effort loader that attaches project identity to the triage signal so SDK-side
triage is project-aware. Every lookup is defensive: missing context degrades to
``source="none"`` rather than failing the post-run hook.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from ..logging_config import get_logger
from .models import ProjectContext

logger = get_logger(__name__)


def _read_contextcore_yaml(start: Path) -> Optional[dict]:
    """Walk up from the run dir looking for a ``.contextcore.yaml`` (or project root)."""
    try:
        import yaml  # lazy; PyYAML is a project dep
    except ImportError:  # pragma: no cover
        return None

    for parent in [start, *start.parents][:6]:
        candidate = parent / ".contextcore.yaml"
        if candidate.is_file():
            try:
                return yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                return None
    return None


def _project_id_from_yaml(data: dict) -> Optional[str]:
    # Tolerate several shapes:
    #   * ContextManifest CRD (contextcore.io/v1alpha2): spec.project.{id,name}
    #   * flat: {project: {id: x}} / {project_id: x} / {project: x}
    #   * CRD metadata.name as a last resort
    spec = data.get("spec")
    if isinstance(spec, dict):
        sproj = spec.get("project")
        if isinstance(sproj, dict):
            pid = sproj.get("id") or sproj.get("project_id") or sproj.get("name")
            if pid:
                return str(pid)

    proj = data.get("project")
    if isinstance(proj, dict):
        pid = proj.get("id") or proj.get("project_id") or proj.get("name")
        if pid:
            return str(pid)
    if isinstance(proj, str):
        return proj

    pid = data.get("project_id")
    if pid:
        return str(pid)

    meta = data.get("metadata")
    if isinstance(meta, dict) and meta.get("name"):
        return str(meta["name"])
    return None


def _task_ids_from_state(project_id: str) -> tuple[List[str], Optional[str]]:
    """Read task ids from ``~/.contextcore/state/{project}/`` if present."""
    state_dir = Path.home() / ".contextcore" / "state" / project_id
    if not state_dir.is_dir():
        return [], None
    task_ids: List[str] = []
    try:
        for f in sorted(state_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            tid = data.get("task_id") or data.get("task", {}).get("id")
            if tid:
                task_ids.append(str(tid))
    except OSError:
        return [], str(state_dir)
    return task_ids, str(state_dir)


def load_project_context(output_dir: Path) -> ProjectContext:
    """Assemble a :class:`ProjectContext` from the best available source (FR-5)."""
    output_dir = Path(output_dir)

    yaml_data = _read_contextcore_yaml(output_dir)
    if not yaml_data:
        return ProjectContext(source="none")

    project_id = _project_id_from_yaml(yaml_data)
    if not project_id:
        return ProjectContext(source="contextcore_yaml")

    task_ids, state_path = _task_ids_from_state(project_id)
    source = "contextcore" if state_path else "contextcore_yaml"
    return ProjectContext(
        project_id=project_id,
        task_ids=task_ids,
        contextcore_state_path=state_path,
        source=source,
    )
