"""
Single source of truth for the observability taxonomy axes.

Defines the ``category`` (5-value) and ``orientation`` (3-value) enums that the
descriptor manifest (``observability/manifest.py``) and the artifact-dispatch
taxonomy registry both consume. Per ``REQ-OBS-SHARED-001`` / ``REQ-OBS-SHARED-003``
(R3-F7), these domains are defined ONCE here and imported by both validation
paths; no other module restates the literal value lists. Docs cite this module
rather than duplicating the enums.

The two axes are orthogonal:
  - ``Category``    — *what is observed* (which observability domain).
  - ``Orientation`` — *who consumes it* (system / human / bridge).
"""

from enum import Enum
from typing import FrozenSet


class Category(str, Enum):
    """The 5-category observability taxonomy (what is observed).

    ``str``-valued so descriptor fields typed ``str`` can hold a member and
    serialize to its value transparently.
    """

    SERVICE = "service_observability"
    BUSINESS = "business_observability"
    PIPELINE_INNATE = "pipeline_innate"
    PROJECT = "project_observability"
    AI_AGENT = "ai_agent_observability"


class Orientation(str, Enum):
    """The 3-value orientation axis (who consumes the signal/artifact).

    - ``SYSTEM`` — metrics, SLOs, SLIs (machine-oriented).
    - ``HUMAN``  — dashboards (operator-oriented).
    - ``BRIDGE`` — alerts, notification policies (both: granularity + tracking).
    """

    SYSTEM = "system"
    HUMAN = "human"
    BRIDGE = "bridge"


class RouteState(str, Enum):
    """The 4-value emit-vs-cede provenance axis (who emits / why skipped).

    Per ``REQ-OBS-SHARED-004`` (OBSERVABILITY_DESCRIPTOR_SPINE_REQUIREMENTS.md),
    routing is driven by this explicit field, NOT inferred from ``Category``:
    *category* answers "what domain is this for," ``route_state`` answers "who
    emits it / why is it skipped." Orthogonal to both other axes.

    - ``SDK_EMITTED``           — SDK emits in-process (every metric has a
      ``meter.create_*`` site). Produced artifact; no ``skip_reason``.
    - ``CONTEXTCORE_OWNED``     — SDK produces raw signals; ContextCore owns the
      ``contextcore_*`` gauges/burndown. Honest-skip (``skip_reason=owned_elsewhere``,
      ``owner=contextcore``); **excluded** from the coverage denominator.
    - ``DECLARED_UNIMPLEMENTED`` — declared artifact type with no generator yet.
      Honest-skip (``skip_reason=unimplemented``).
    - ``EXTERNAL_CONVENTION``   — externally-observed convention metrics (HTTP RED,
      mesh) with no SDK ``meter.create_*`` site. Produced (references external metric).
    """

    SDK_EMITTED = "sdk_emitted"
    CONTEXTCORE_OWNED = "contextcore_owned"
    DECLARED_UNIMPLEMENTED = "declared_unimplemented"
    EXTERNAL_CONVENTION = "external_convention"


#: Frozenset of valid ``category`` values, for cheap membership validation.
CATEGORY_VALUES: FrozenSet[str] = frozenset(c.value for c in Category)

#: Frozenset of valid ``orientation`` values, for cheap membership validation.
ORIENTATION_VALUES: FrozenSet[str] = frozenset(o.value for o in Orientation)

#: Frozenset of valid ``route_state`` values, for cheap membership validation.
ROUTE_STATE_VALUES: FrozenSet[str] = frozenset(r.value for r in RouteState)


def is_valid_category(value: str) -> bool:
    """True if ``value`` is a member of the category enum (``""`` is unset, not valid)."""
    return value in CATEGORY_VALUES


def is_valid_orientation(value: str) -> bool:
    """True if ``value`` is a member of the orientation enum (``""`` is unset, not valid)."""
    return value in ORIENTATION_VALUES
