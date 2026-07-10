"""One dispatcher over the kickoff read-model's machine-readable projections.

Every ``$0`` read-only view of a project — status, activation verdict, retrospective, exemplar
library — behind ONE function, so a surface (CLI ``--json``, the MCP tool, CI) selects a view by
name instead of each surface re-implementing each view. This is the single spine that keeps N views
× M surfaces from becoming N×M call sites: add a view to :data:`REPORT_VIEWS` once and every surface
gets it. All views are read-only and JSON-serializable; each carries its own ``schema`` field.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from . import schemas


def _status(project_root: Any) -> dict:
    from .agentic_view import kickoff_status

    return kickoff_status(project_root)


def _activation(project_root: Any) -> dict:
    from .activation import evaluate_activation
    from .agentic_view import kickoff_status

    return evaluate_activation(kickoff_status(project_root)).to_dict()


def _retrospective(project_root: Any) -> dict:
    from .retrospective import kickoff_retrospective

    return kickoff_retrospective(project_root)


def _exemplars(_project_root: Any) -> dict:
    # The exemplar registry is cross-project (not scoped to project_root); the arg is ignored so the
    # view has the uniform (project_root) signature of every other view.
    from .promotion import ExemplarRegistry

    items = ExemplarRegistry().list()
    return {"schema": schemas.EXEMPLAR, "exemplars": items, "count": len(items)}


# The registry of machine-readable views. Adding a view here surfaces it on EVERY dispatch surface.
REPORT_VIEWS: Dict[str, Callable[[Any], dict]] = {
    "status": _status,
    "activation": _activation,
    "retrospective": _retrospective,
    "exemplars": _exemplars,
}

# The schema each view emits (for discovery / `--list`).
VIEW_SCHEMAS: Dict[str, str] = {
    "status": schemas.STATUS,
    "activation": schemas.ACTIVATION,
    "retrospective": schemas.RETROSPECTIVE,
    "exemplars": schemas.EXEMPLAR,
}


def report_views() -> List[str]:
    """The available view names."""
    return list(REPORT_VIEWS)


def kickoff_report(project_root: Any, view: str = "status") -> dict:
    """Return the named read-only view of a project. Unknown view ⇒ an error dict listing the views.

    The single MCP/CLI-agnostic entry point for the machine-readable kickoff surface. Read-only, ``$0``."""
    fn = REPORT_VIEWS.get(view)
    if fn is None:
        return {"error": f"unknown view {view!r}", "views": report_views()}
    return fn(project_root)
