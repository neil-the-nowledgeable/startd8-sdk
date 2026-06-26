"""``business-targets.yaml`` — what success looks like, in numbers (the goal lines on dashboards).

The third FR-VIP value-input class. The simplest shape ("goals in numbers"), but it hardens the shared
extractor machinery on a TABLE-per-group grammar. Strict round-trip authority (FR-VIP-2):
``parse_business_targets`` loud-fails on a malformed sheet so the prose extractor can gate every emitted
``business-targets.yaml`` against it.

Shape (§2.10): ``domain == "business-targets"``, optional ``provenance_default``, the metric groups
``product_funnel`` / ``traction`` / ``unit_economics`` (each ``{metric: {target, why}}``; ``target`` is an
int when bare, else a string), an optional ``monetization`` block, and ``per_role_top_goals``
(``{role: one-liner}``). Unknown top-level keys are rejected (typo guard); metric/role keys are open
vocabulary. Project-agnostic — a personal tool's household-outcome targets parse the same as a SaaS
funnel (FR-VIP-9).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Union

import yaml

_TOP_LEVEL_KEYS = frozenset({
    "domain", "provenance_default", "product_funnel", "traction", "unit_economics",
    "monetization", "per_role_top_goals",
})
_METRIC_GROUPS = ("product_funnel", "traction", "unit_economics")


@dataclass(frozen=True)
class Target:
    """One target row: a numeric-or-string ``target`` + an optional free-text ``why``."""

    target: Union[int, str]
    why: Optional[str] = None


@dataclass(frozen=True)
class BusinessTargetsManifest:
    """A parsed, validated ``business-targets.yaml`` — the success metrics with their goal values."""

    domain: str = "business-targets"
    provenance_default: Optional[str] = None
    product_funnel: Dict[str, Target] = field(default_factory=dict)
    traction: Dict[str, Target] = field(default_factory=dict)
    unit_economics: Dict[str, Target] = field(default_factory=dict)
    monetization: Optional[Dict[str, object]] = None
    per_role_top_goals: Dict[str, str] = field(default_factory=dict)


def _targets(value: object, key: str) -> Dict[str, Target]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"business-targets.yaml: `{key}` must be a mapping of metric -> {{target, why}}")
    out: Dict[str, Target] = {}
    for k, v in value.items():
        if not isinstance(v, dict):
            raise ValueError(f"business-targets.yaml: `{key}.{k}` must be a {{target, why}} mapping")
        extra = set(v) - {"target", "why"}
        if extra:
            raise ValueError(
                f"business-targets.yaml: `{key}.{k}` has unknown keys {sorted(extra)} (allowed: target, why)"
            )
        target = v.get("target")
        if isinstance(target, bool) or not isinstance(target, (str, int)):
            raise ValueError(f"business-targets.yaml: `{key}.{k}.target` must be a string or integer")
        why = v.get("why")
        if why is not None and not isinstance(why, str):
            raise ValueError(f"business-targets.yaml: `{key}.{k}.why` must be a string")
        out[str(k)] = Target(target=target, why=why)
    return out


def _monetization(value: object) -> Optional[Dict[str, object]]:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("business-targets.yaml: `monetization` must be a mapping")
    extra = set(value) - {"mode_now", "conversion_rate", "price_point"}
    if extra:
        raise ValueError(
            f"business-targets.yaml: `monetization` has unknown keys {sorted(extra)} "
            "(allowed: mode_now, conversion_rate, price_point)"
        )
    mode_now = value.get("mode_now")
    if mode_now is not None and not isinstance(mode_now, str):
        raise ValueError("business-targets.yaml: `monetization.mode_now` must be a string")
    for sub in ("conversion_rate", "price_point"):
        s = value.get(sub)
        if s is None:
            continue
        if not isinstance(s, dict) or set(s) - {"target", "status"}:
            raise ValueError(
                f"business-targets.yaml: `monetization.{sub}` must be a {{target, status}} mapping"
            )
    return dict(value)


def parse_business_targets(text: Optional[str]) -> BusinessTargetsManifest:
    """Parse + **strictly** validate ``business-targets.yaml`` → :class:`BusinessTargetsManifest`.

    Loud-fails (``ValueError``) on a non-mapping root, an unknown top-level key, a wrong ``domain``, a
    metric row that is not a ``{target, why}`` mapping, a non-scalar ``target``, or a malformed
    ``monetization`` block.
    """
    data = yaml.safe_load(text or "") or {}
    if not isinstance(data, dict):
        raise ValueError("business-targets.yaml must be a mapping")
    unknown = set(data) - _TOP_LEVEL_KEYS
    if unknown:
        raise ValueError(
            f"business-targets.yaml: unknown top-level keys {sorted(unknown)} "
            f"(allowed: {sorted(_TOP_LEVEL_KEYS)})"
        )
    domain = data.get("domain", "business-targets")
    if domain != "business-targets":
        raise ValueError(f"business-targets.yaml: `domain` must be 'business-targets', got {domain!r}")
    prov = data.get("provenance_default")
    if prov is not None and not isinstance(prov, str):
        raise ValueError("business-targets.yaml: `provenance_default` must be a string")

    roles = data.get("per_role_top_goals", {}) or {}
    if not isinstance(roles, dict) or any(not isinstance(v, str) for v in roles.values()):
        raise ValueError("business-targets.yaml: `per_role_top_goals` must be a mapping of role -> string")

    return BusinessTargetsManifest(
        domain=domain,
        provenance_default=prov,
        product_funnel=_targets(data.get("product_funnel"), "product_funnel"),
        traction=_targets(data.get("traction"), "traction"),
        unit_economics=_targets(data.get("unit_economics"), "unit_economics"),
        monetization=_monetization(data.get("monetization")),
        per_role_top_goals={str(k): v for k, v in roles.items()},
    )
