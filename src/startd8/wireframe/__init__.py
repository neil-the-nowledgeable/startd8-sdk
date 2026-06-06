"""Basic wireframing capability — pre-generation summary of the deterministic cascade.

Derives a structured :class:`~startd8.wireframe.plan.WireframePlan` ("what WILL the $0 cascade
build?") from the hand-authored assembly input manifests, without invoking the generators and
without writing any application files. See ``docs/design/wireframe/WIREFRAME_REQUIREMENTS.md``.

Stable public API (FR-W16): :func:`load_assembly_inputs` and :func:`build_wireframe_plan` are
importable here for programmatic use (kickoff FR-X1/FR-X5 machinery, TUI, tests) — not CLI-only.
"""

from .inputs import (
    AssemblyInputs,
    AssemblyInputsError,
    CATALOG_KEYS,
    load_assembly_inputs,
)
from .plan import (
    Status,
    WireframeItem,
    WireframePlan,
    WireframeSection,
    build_wireframe_plan,
)
from .render import plan_to_json, persist_plan, render_plan

__all__ = [
    "AssemblyInputs",
    "AssemblyInputsError",
    "CATALOG_KEYS",
    "Status",
    "WireframeItem",
    "WireframePlan",
    "WireframeSection",
    "build_wireframe_plan",
    "load_assembly_inputs",
    "persist_plan",
    "plan_to_json",
    "render_plan",
]
