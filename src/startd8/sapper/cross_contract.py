"""FR-SAP-5 — plan-time cross-contract consistency over the ForwardManifest.

Detects **contradictory contracts** — two ``InterfaceContract``s that prescribe incompatible
specs for the *same resolved identity* (same endpoint with different schemas, same class with
different bases). Distinct from post-gen ``validate_forward_manifest``, which checks generated
code against contracts; this checks contracts against *each other*, at plan time.

Versioned/overloaded tolerance (R2-F2): identity is the *resolved* target (the exact endpoint
/ class name), not the raw ``contract_id`` — so ``/v1/x`` and ``/v2/x`` are different identities
and never collide; and contracts scoped to disjoint ``applicable_task_ids`` are not compared.
"""

from __future__ import annotations

from typing import List, Optional

from .models import (
    AssumptionKind,
    AssumptionVerdict,
    FrictionFinding,
    Severity,
    ValidatorClass,
    avoidable_cost_stage,
    finding_fingerprint,
)

# category → (primary-identity attr, [secondary attrs that must agree], assumption kind)
_CONFLICT_SPECS = {
    "api_endpoint": ("endpoint", ["request_schema", "response_schema"], AssumptionKind.INTERFACE_SIGNATURE),
    "class_name": ("class_name", ["base_class"], AssumptionKind.IDENTITY_COLLISION),
    "import_path": ("import_path", [], AssumptionKind.MODULE_SOURCE),
}


def _cat_value(c) -> str:
    return c.category.value if hasattr(c.category, "value") else str(c.category)


def _tasks_disjoint(a, b) -> bool:
    """Contracts scoped to non-overlapping task sets are not compared (both empty = global)."""
    ta, tb = set(a.applicable_task_ids or []), set(b.applicable_task_ids or [])
    if not ta or not tb:
        return False  # at least one applies globally → they share scope
    return ta.isdisjoint(tb)


def run_cross_contract(manifest, *, shared_files=None) -> List[FrictionFinding]:
    """Return REFUTED findings for mutually contradictory contracts in the manifest."""
    findings: List[FrictionFinding] = []
    contracts = list(getattr(manifest, "contracts", []) or [])

    # Group by (category, resolved-primary-identity).
    groups: dict = {}
    for c in contracts:
        cat = _cat_value(c)
        spec = _CONFLICT_SPECS.get(cat)
        if not spec:
            continue
        primary_attr, _secondary, _kind = spec
        identity = getattr(c, primary_attr, None)
        if not identity:
            continue
        groups.setdefault((cat, identity), []).append(c)

    for (cat, identity), members in groups.items():
        if len(members) < 2:
            continue
        primary_attr, secondary, kind = _CONFLICT_SPECS[cat]
        # Pairwise compare; flag the first genuine conflict per identity.
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                if _tasks_disjoint(a, b):
                    continue
                conflict = _first_conflict(a, b, secondary)
                if conflict is None:
                    continue
                attr, va, vb = conflict
                findings.append(
                    FrictionFinding(
                        id=f"xcontract::{cat}:{identity}:{attr}",
                        kind=kind,
                        verdict=AssumptionVerdict.REFUTED,
                        severity=Severity.HIGH,
                        avoidable_cost_stage=avoidable_cost_stage(kind),
                        fingerprint=finding_fingerprint(kind, str(identity), attr),
                        expected=f"single {attr} for {identity}",
                        found=f"conflict: {a.contract_id}={_short(va)} vs {b.contract_id}={_short(vb)}",
                        validator_class=ValidatorClass.DETERMINISTIC,
                    )
                )
                break  # one finding per identity is enough
            else:
                continue
            break
    return findings


def _first_conflict(a, b, secondary) -> Optional[tuple]:
    for attr in secondary:
        va, vb = getattr(a, attr, None), getattr(b, attr, None)
        if va is not None and vb is not None and va != vb:
            return (attr, va, vb)
    return None


def _short(v) -> str:
    s = str(v)
    return s if len(s) <= 60 else s[:57] + "..."
