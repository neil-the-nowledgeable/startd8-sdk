"""FR-SAP-6 — deterministic per-element checks, composing existing predicates.

Operates on the *structured* manifest (not skeleton text) and yields ``FrictionFinding``s for
the gate. Composes ``element_fillability`` (non-buildable empty types) and adds reserved-name /
identity-collision detection (the ``metadata`` crash class), with override tolerance (R3-F5).

These are exposed as plain functions the gate calls. They are *also* the bodies a thin
``startd8.preflight_rules`` entry-point wrapper can call for prompt-enrichment, but the
unified report (trichotomy + ranking) is gate-side, not ``RuleContribution``-side (per §0).
"""

from __future__ import annotations

import keyword
from typing import List, Optional, Set

from startd8.element_fillability import is_empty_fillable_spec

from .models import (
    AssumptionKind,
    AssumptionVerdict,
    FrictionFinding,
    Severity,
    ValidatorClass,
    avoidable_cost_stage,
    finding_fingerprint,
)

# Names that collide with framework/ORM machinery and crash on import/registration.
# ``metadata`` is the SQLModel/SQLAlchemy reserved attribute (the actual RUN crash).
_RESERVED_ATTR_NAMES: Set[str] = {"metadata", "registry", "__table__"}

# Override markers that make a name collision intentional (R3-F5 tolerance).
_OVERRIDE_DECORATORS = {"override", "typing.override", "overrides"}


def check_fillability(manifest, *, shared_files: Optional[Set[str]] = None) -> List[FrictionFinding]:
    """A file whose declared elements are only non-buildable empty types → REFUTED."""
    shared = shared_files or set()
    out: List[FrictionFinding] = []
    for path, spec in sorted(manifest.file_specs.items()):
        elements = list(spec.elements)
        if not elements:
            continue
        if is_empty_fillable_spec(elements):
            is_shared = path in shared
            out.append(
                FrictionFinding(
                    id=f"fillability::{path}",
                    kind=AssumptionKind.DECOMPOSITION_INTEGRITY,
                    verdict=AssumptionVerdict.REFUTED,
                    severity=Severity.HIGH if is_shared else Severity.MEDIUM,
                    avoidable_cost_stage=avoidable_cost_stage(
                        AssumptionKind.DECOMPOSITION_INTEGRITY, shared_file=is_shared
                    ),
                    fingerprint=finding_fingerprint(
                        AssumptionKind.DECOMPOSITION_INTEGRITY, path, "fillability"
                    ),
                    file=path,
                    expected="at least one buildable element",
                    found="only empty/non-implementable type declarations",
                    validator_class=ValidatorClass.DETERMINISTIC,
                )
            )
    return out


def _is_override(el) -> bool:
    if getattr(el, "parent_class", None):
        decs = {d.split("(")[0].lstrip("@").strip() for d in (getattr(el, "decorators", []) or [])}
        if decs & _OVERRIDE_DECORATORS:
            return True
    return False


def check_identity_collisions(
    manifest, *, shared_files: Optional[Set[str]] = None
) -> List[FrictionFinding]:
    """Reserved-name / keyword collisions on declared elements (override-tolerant, R3-F5)."""
    shared = shared_files or set()
    out: List[FrictionFinding] = []
    for path, spec in sorted(manifest.file_specs.items()):
        for el in spec.elements:
            name = getattr(el, "name", "") or ""
            bad = name in _RESERVED_ATTR_NAMES or keyword.iskeyword(name)
            if not bad or _is_override(el):
                continue
            is_shared = path in shared
            why = "Python keyword" if keyword.iskeyword(name) else "framework-reserved attribute"
            out.append(
                FrictionFinding(
                    id=f"identity::{path}:{name}",
                    kind=AssumptionKind.IDENTITY_COLLISION,
                    verdict=AssumptionVerdict.REFUTED,
                    severity=Severity.HIGH if is_shared else Severity.MEDIUM,
                    avoidable_cost_stage=avoidable_cost_stage(
                        AssumptionKind.IDENTITY_COLLISION, shared_file=is_shared
                    ),
                    fingerprint=finding_fingerprint(AssumptionKind.IDENTITY_COLLISION, path, name),
                    file=path,
                    expected=f"a non-reserved name (got `{name}`)",
                    found=f"{name} is a {why}",
                    validator_class=ValidatorClass.DETERMINISTIC,
                )
            )
    return out


def run_per_element_rules(manifest, *, shared_files: Optional[Set[str]] = None) -> List[FrictionFinding]:
    """All FR-SAP-6 per-element checks."""
    return [
        *check_fillability(manifest, shared_files=shared_files),
        *check_identity_collisions(manifest, shared_files=shared_files),
    ]
