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


#: Frozenset of valid ``category`` values, for cheap membership validation.
CATEGORY_VALUES: FrozenSet[str] = frozenset(c.value for c in Category)

#: Frozenset of valid ``orientation`` values, for cheap membership validation.
ORIENTATION_VALUES: FrozenSet[str] = frozenset(o.value for o in Orientation)


def is_valid_category(value: str) -> bool:
    """True if ``value`` is a member of the category enum (``""`` is unset, not valid)."""
    return value in CATEGORY_VALUES


def is_valid_orientation(value: str) -> bool:
    """True if ``value`` is a member of the orientation enum (``""`` is unset, not valid)."""
    return value in ORIENTATION_VALUES
