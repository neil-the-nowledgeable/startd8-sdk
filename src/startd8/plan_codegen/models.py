"""Typed models for the ``$0`` det-req → det-plan/0.1 projector (REQ-29).

A :class:`DetPlan` is a **pure projection** of a det-req: every field derives from the
requirement (its FRs, ``Touches`` refs, authored ``Depends:`` topology, ``Verify:`` clauses,
realization regime). No field is authored here and nothing is LLM-inferred — the projector is a
pure function of the requirement (``SCHEMA_det-plan-0.1.md`` §0, charter invariant 1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

# costClass vocabulary (SCHEMA §2) — the realization regime rolled up to a plan cost band.
COST_DETERMINISTIC = "deterministic-$0"
COST_LLM = "llm-integration"
COST_HUMAN = "human"
COST_CLASSES = (COST_DETERMINISTIC, COST_LLM, COST_HUMAN)

# The projected-plan maturity rung (SCHEMA §7, charter invariant 3). A projection always starts
# at the lowest rung; it climbs only by earning hardening evidence — never stamped here.
PROJECTED_MATURITY = "0.1"

FORMAT_VERSION = "det-plan/0.1"
COMPANION_KIND = "PLAN"


@dataclass(frozen=True)
class GateClause:
    """One FR's exit criterion carried into an iteration gate — the requirement→test seed (§5)."""

    fr: str
    verify: str


@dataclass(frozen=True)
class Iteration:
    """One iteration of the projected plan (SCHEMA §2 — the heart).

    Every field derives from the FRs it batches: ``frs`` is the authored grouping, ``target_files``
    the union of those FRs' ``Touches``, ``gate`` the rollup of their ``Verify:`` clauses,
    ``depends_on`` the iterations carrying FRs those FRs authored a ``Depends:`` edge to, and
    ``cost_class`` the realization regime of the batch.
    """

    id: str
    name: str
    frs: Tuple[str, ...]
    target_files: Tuple[str, ...]
    depends_on: Tuple[str, ...]
    gate: Tuple[GateClause, ...]
    cost_class: str
    status: str = "planned"


@dataclass(frozen=True)
class DetPlan:
    """A projected det-plan/0.1 document (SCHEMA §1–§8)."""

    version: str
    format_version: str
    pairs_with: str
    companion_kind: str
    maturity: str
    name: str
    handle: str
    ref: str
    iterations: Tuple[Iteration, ...]
    # The plan-level Verify rollup (§5) — every FR verify carried forward, deduplicated by FR.
    verify_rollup: Tuple[GateClause, ...] = ()
    # The reuse/phantom audit (§4): each authored ``Touches``/``Lives`` ref + whether it resolves.
    reuse_refs: Tuple[Tuple[str, bool], ...] = ()


@dataclass(frozen=True)
class PlanFinding:
    """A conformance / plan-liveness finding (SCHEMA §10) — duck-typed for ``findings_sarif``.

    Carries ``check`` / ``severity`` / ``message`` / ``file_path`` so the one reusable
    ``coverage_map/findings_sarif.render_sarif_from_findings`` renders it with no adapter.
    """

    check: str
    severity: str
    message: str
    file_path: str
    line: int = 0
