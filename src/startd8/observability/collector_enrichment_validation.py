# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Fail-fast validation for the collector_enrichment OTTL transform/business processor.

REQ_COLLECTOR_ENRICHMENT FR-8. Deliberately separate from the fail-SOFT
``validators/observability_artifact_checks.py`` pattern (which records issues and still writes):
this contract is **fail-fast — no partial output**. The generator validates the built statement
model *before* serialization; a raise here degrades the artifact to ``status="error"`` with an empty
body, never a half-written collector config.

A "row" is one resolved OTTL statement, modeled as a ``(service_name, attr, value)`` tuple:
``attr`` ∈ ``{criticality, owner}``; for criticality ``value`` is constrained to the ContextCore
``Criticality`` enum (a non-normative snapshot — ContextCore owns the vocabulary).
"""

from typing import Iterable, List, Set, Tuple

# Non-normative snapshot of ContextCore's Criticality enum (models/core.py). ContextCore owns this
# vocabulary; we treat it as the closed set the emitter is allowed to stamp for `business.criticality`.
CRITICALITY_VALUES = frozenset({"critical", "high", "medium", "low"})

# The attribute vocabulary this generator emits (min set per the handoff). owner is free text.
BUSINESS_ATTRS = ("criticality", "owner")

Row = Tuple[str, str, str]  # (service_name, attr, value)


class CollectorEnrichmentError(ValueError):
    """Raised when the enrichment statement model is invalid. Caught at the generator boundary
    and surfaced as ArtifactResult(status="error"); never produces partial output."""


def validate_collector_enrichment(rows: Iterable[Row], business_services: Set[str]) -> None:
    """Validate the resolved statement rows. Raise ``CollectorEnrichmentError`` on any violation.

    Args:
        rows: the resolved ``(service_name, attr, value)`` statements the emitter will render.
        business_services: the set of resolved ``service.name`` values that carried ANY business
            context (criticality or owner) — used to catch "present but produced zero statements".

    Checks (FR-8):
        1. every business-carrying service contributes ≥1 statement;
        2. no ``criticality`` value outside the enum;
        3. no empty ``service.name`` and no duplicate ``(service, attr)`` statement;
        4. every attr is in the known business vocabulary (structural well-formedness).
    """
    rows = list(rows)

    covered = {sel for sel, _attr, _val in rows}
    missing = business_services - covered
    if missing:
        raise CollectorEnrichmentError(
            f"services with business context but no emitted statement: {sorted(missing)}"
        )

    for sel, attr, val in rows:
        if not sel or not sel.strip():
            raise CollectorEnrichmentError("empty service.name in enrichment statement")
        if attr not in BUSINESS_ATTRS:
            raise CollectorEnrichmentError(f"unknown business attribute: {attr!r}")
        if attr == "criticality" and val not in CRITICALITY_VALUES:
            raise CollectorEnrichmentError(
                f"criticality out of enum for {sel!r}: {val!r} "
                f"(allowed: {sorted(CRITICALITY_VALUES)})"
            )
        if val is None or (isinstance(val, str) and not val.strip()):
            raise CollectorEnrichmentError(f"empty {attr} value for {sel!r}")

    pairs: List[Tuple[str, str]] = [(sel, attr) for sel, attr, _val in rows]
    if len(pairs) != len(set(pairs)):
        dupes = sorted({p for p in pairs if pairs.count(p) > 1})
        raise CollectorEnrichmentError(f"duplicate (service, attr) statement(s): {dupes}")
