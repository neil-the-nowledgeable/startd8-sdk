"""
Single source of truth for the observability taxonomy axes.

Defines the ``category`` (6-value) and ``orientation`` (3-value) enums that the
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
    """The 6-category observability taxonomy (what is observed).

    ``str``-valued so descriptor fields typed ``str`` can hold a member and
    serialize to its value transparently.
    """

    SERVICE = "service_observability"
    BUSINESS = "business_observability"
    PIPELINE_INNATE = "pipeline_innate"
    PROJECT = "project_observability"
    AI_AGENT = "ai_agent_observability"
    # Feature/product delivery beyond agents (milestone/epic pace, product-request
    # queue, unified rollup). Requested by ContextCore for its Feature/Delivery
    # Observability Phase 2 — see docs/CATEGORY_DELIVERY_OBSERVABILITY_REQUEST_FROM_CONTEXTCORE_2026-08-04.md
    DELIVERY = "delivery_observability"


class Orientation(str, Enum):
    """The 3-value orientation axis (who consumes the signal/artifact).

    - ``SYSTEM`` — metrics, SLOs, SLIs (machine-oriented).
    - ``HUMAN``  — dashboards (operator-oriented).
    - ``BRIDGE`` — alerts, notification policies (both: granularity + tracking).
    """

    SYSTEM = "system"
    HUMAN = "human"
    BRIDGE = "bridge"


class Criticality(str, Enum):
    """The 4-value business-criticality vocabulary (how important a service/target is).

    This is the SINGLE authority for the ``business.criticality`` enum across the
    observability package — the collector-enrichment OTTL emitter, its fail-fast
    validator, the criticality→alert-severity map, and the coverage-report rank all
    draw the *closed set* from here rather than restating the literals (which drift).
    Per the collector-enrichment gap analysis (gap #4, "criticality vocabulary drift"),
    ``collector_enrichment_validation.CRITICALITY_VALUES`` was a hand-maintained
    snapshot; it now re-exports ``CRITICALITY_VALUES`` defined below.

    **Cross-repo contract:** ContextCore supplies criticality per service via the
    manifest ``spec.business.criticality`` / ``spec.targets[].criticality`` field
    (`.contextcore.yaml`), forwarded as ``instrumentation_hints[svc].business.criticality``
    (FR-1a/1b). That manifest field IS the interface; these four values are its agreed
    vocabulary. A drift guard (``test_criticality_authority.py``) pins the set so a
    change here or in a consuming map fails loudly instead of silently diverging.
    Ordered ``str``-valued so a field typed ``str`` can hold a member transparently.
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


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

#: Frozenset of valid ``criticality`` values — the closed set the collector-enrichment
#: emitter is allowed to stamp for ``business.criticality`` (and the coverage/severity maps
#: draw their key vocabulary from). The single authority; do not restate the literals.
CRITICALITY_VALUES: FrozenSet[str] = frozenset(c.value for c in Criticality)

#: Criticality in descending severity (most → least important). Consumers that rank or sort
#: (coverage report, dashboard placement) index into this instead of a private rank dict.
CRITICALITY_ORDER: tuple = (
    Criticality.CRITICAL.value,
    Criticality.HIGH.value,
    Criticality.MEDIUM.value,
    Criticality.LOW.value,
)


def is_valid_category(value: str) -> bool:
    """True if ``value`` is a member of the category enum (``""`` is unset, not valid)."""
    return value in CATEGORY_VALUES


def is_valid_orientation(value: str) -> bool:
    """True if ``value`` is a member of the orientation enum (``""`` is unset, not valid)."""
    return value in ORIENTATION_VALUES


def is_valid_criticality(value: str) -> bool:
    """True if ``value`` is a member of the criticality enum (``""`` is unset, not valid)."""
    return value in CRITICALITY_VALUES
