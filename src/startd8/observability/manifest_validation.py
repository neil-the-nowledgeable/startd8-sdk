"""
Manifest-level validation: taxonomy-axis completeness (REQ-OBS-SHARED-001, R3-F5).

After the keystone, ``category``/``orientation`` empty defaults are a *compatibility
bridge*, not an accepted end state: a descriptor with unset axes routes to no
generated dashboard/coverage. This gate reports such descriptors **by source file**.

During bootstrap, a shrinking **grandfather list** of source files whose descriptors
are not yet annotated is tolerated (they are owned by other categories / later passes
— e.g. cat-4 project spans, pipeline-innate internals). A descriptor that carries a
*set-but-invalid* axis value is always a violation, regardless of the grandfather list.
"""

from dataclasses import dataclass, field
from typing import FrozenSet, List, Optional

from .manifest import ObservabilityManifest, generate_manifest
from .taxonomy_enums import is_valid_category, is_valid_orientation

# Source files whose descriptors are not yet axis-annotated and are tolerated for
# now. Each entry is owned by a follow-up: project spans → cat-4 Phase 2;
# pipeline-innate internals → a later pass. The list MUST shrink to empty; removing
# an entry requires annotating that module's descriptors in the same change.
# Empty: every collector-instrumented module now declares its taxonomy axes. cat-4
# annotated the project-obs contractors; B/pipeline-catalog annotated the pipeline-innate
# modules (events, repair, orchestration, workflows, complexity). A module with unset
# axes is now a real violation, not a tolerated bootstrap gap.
GRANDFATHERED_SOURCES: FrozenSet[str] = frozenset()


@dataclass
class AxisViolation:
    """A descriptor whose taxonomy axes are unset (and not grandfathered) or invalid."""

    name: str
    kind: str  # "metric" | "span"
    source_file: str
    problems: List[str] = field(default_factory=list)  # e.g. ["category unset", "orientation 'foo' invalid"]


def _check_axes(name: str, kind: str, source_file: str, category: str,
                orientation: str, grandfathered: FrozenSet[str]) -> Optional["AxisViolation"]:
    problems: List[str] = []

    # Set-but-invalid is always a violation (grandfather only excuses *unset*).
    if category and not is_valid_category(category):
        problems.append(f"category '{category}' not a valid taxonomy value")
    if orientation and not is_valid_orientation(orientation):
        problems.append(f"orientation '{orientation}' not a valid value")

    # Unset axes are violations unless the source file is grandfathered.
    if source_file not in grandfathered:
        if not category:
            problems.append("category unset")
        if not orientation:
            problems.append("orientation unset")

    if problems:
        return AxisViolation(name=name, kind=kind, source_file=source_file, problems=problems)
    return None


def check_axis_completeness(
    manifest: Optional[ObservabilityManifest] = None,
    grandfathered: FrozenSet[str] = GRANDFATHERED_SOURCES,
) -> List[AxisViolation]:
    """Return axis violations across the manifest's metric + span descriptors.

    Empty result == every non-grandfathered descriptor carries valid axes.
    """
    if manifest is None:
        manifest = generate_manifest()

    violations: List[AxisViolation] = []
    for m in manifest.metrics:
        v = _check_axes(m.name, "metric", m.source_file, m.category, m.orientation, grandfathered)
        if v:
            violations.append(v)
    for s in manifest.spans:
        v = _check_axes(s.name_pattern, "span", s.source_file, s.category, s.orientation, grandfathered)
        if v:
            violations.append(v)
    return violations
