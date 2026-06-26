"""derive-contract orchestration — preview (Step 3), exclusion/orphans (Step 4), drift (Step 5).

Composes the pieces: contained introspection (Step 1) → EntityGraph mapper (Step 2) →
`render_prisma_schema` (the reused emitter) → a **candidate** contract carrying the FR-DC-7c
`unratified` provenance header + a derivation report (the Architect's review surface).

- **Step 3** `build_derivation`: emit the candidate contract + report. Pure preview — no disk write
  (the CLI is the sole writer, OQ-7).
- **Step 4** exclusion sidecar (FR-DC-12, project-curation, FQ-class-keyed) + **orphan detection**:
  an exclusion/marker whose target no longer exists is reported, never silently ignored.
- **Step 5** `check_drift` (FR-DC-11): re-derive and `parity_against_live`, **excluding
  ratified-flagged items** (a flagged ambiguity the human ratified into the live contract must not
  read as perpetual drift).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from startd8.logging_config import get_logger
from startd8.manifest_extraction.prisma_emitter import parity_against_live, render_prisma_schema

from .containment import run_contained_introspection
from .introspect import IntrospectionResult
from .mapper import DerivationReport, build_entity_graph

logger = get_logger(__name__)

SCHEMA_VERSION = 1

# FR-DC-7c — machine-readable provenance so the candidate is not byte-indistinguishable from a
# hand-authored, ratified contract (a cascade guard can detect `status: unratified`).
PROVENANCE_HEADER = (
    "// derived-by: derive-contract (Concierge) — CANDIDATE, NOT RATIFIED\n"
    "// status: unratified — the Architect must review the derivation report and ratify before use (FR-DC-7c)\n"
)


@dataclass
class DerivationResult:
    schema_version: int
    contract_text: str                      # candidate .prisma WITH the provenance header
    report: Dict[str, Any]                   # DerivationReport (transforms/exclusions/flags/joins)
    shape: Dict[str, int]
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    unrenderable: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class DriftResult:
    schema_version: int
    verdict: str                             # "in_sync" | "drifted"
    drift: List[str] = field(default_factory=list)
    excluded_flagged: List[str] = field(default_factory=list)  # FR-DC-11 suppressed lines


def _flag_prefixes(report: DerivationReport) -> set:
    """`{Entity}.{field}` keys for flagged ambiguities — used to suppress ratified-flagged drift."""
    out = set()
    for fl in report.flags:
        ent, fld = fl.get("entity"), fl.get("field")
        if ent and fld:
            out.add(f"{ent}.{fld}")
    return out


def _apply_exclusions(
    result: IntrospectionResult, exclude_models: Optional[List[str]]
) -> List[Dict[str, Any]]:
    """Step 4 — drop excluded models (FQ ``module.Class`` or bare ``Class``), in place. Returns
    flags: orphaned exclusions (target absent) and dangling references (a kept entity still points
    at an excluded model)."""
    flags: List[Dict[str, Any]] = []
    if not exclude_models:
        return flags
    present = {e.name for e in result.entities}
    excl_simple = {x.rsplit(".", 1)[-1] for x in exclude_models}

    for x in exclude_models:                       # orphaned exclusion markers (R1-S6/FR-DC-12)
        if x.rsplit(".", 1)[-1] not in present:
            flags.append({"kind": "orphan-exclusion",
                          "reason": f"exclusion target {x!r} is not among the introspected models"})

    # dangling reference: a kept entity references an excluded model → relation to a missing model.
    for ent in result.entities:
        if ent.name in excl_simple:
            continue
        for f in ent.fields:
            if f.ref_model in excl_simple:
                flags.append({"kind": "dangling-reference", "entity": ent.name, "field": f.name,
                              "reason": f"references excluded model {f.ref_model!r} — relation will dangle"})

    result.entities = [e for e in result.entities if e.name not in excl_simple]
    for n in sorted(excl_simple & present):
        flags.append({"kind": "sidecar-exclude", "entity": n, "reason": "excluded from the contract"})
    return flags


def _detect_join_orphans(graph_joins, entity_names: set) -> List[Dict[str, Any]]:
    flags = []
    for j in graph_joins:
        for side in (j.left, j.right):
            if side not in entity_names:
                flags.append({"kind": "orphan-join-marker", "join": j.name,
                              "reason": f"M2M join target {side!r} is not an introspected model"})
    return flags


def _assemble(
    result: IntrospectionResult, exclude_models: Optional[List[str]] = None
) -> Tuple[DerivationResult, DerivationReport]:
    """Steps 3+4 from an already-introspected result (no subprocess) — the testable core."""
    excl_flags = _apply_exclusions(result, exclude_models)
    graph, report = build_entity_graph(result)
    report.flags.extend(excl_flags)
    report.flags.extend(_detect_join_orphans(graph.joins, set(graph.entities)))

    res = render_prisma_schema(graph)
    derivation = DerivationResult(
        schema_version=SCHEMA_VERSION,
        contract_text=PROVENANCE_HEADER + res.text,
        report=dataclasses.asdict(report),
        shape={"entities": len(graph.entities), "enums": len(graph.enums), "joins": len(graph.joins)},
        warnings=list(res.warnings),
        errors=list(res.errors),
        unrenderable=[{"model": u.model, "field": u.field, "reason": u.reason} for u in res.unrenderable],
    )
    return derivation, report


def _check(
    result: IntrospectionResult, live_schema_text: str,
    exclude_models: Optional[List[str]] = None,
) -> DriftResult:
    """Step 5 core: drift of the re-derived graph vs the live contract, ratified-flagged-suppressed."""
    excl_flags = _apply_exclusions(result, exclude_models)
    graph, report = build_entity_graph(result)
    report.flags.extend(excl_flags)
    raw = parity_against_live(graph, live_schema_text)
    # semantic_diff lines are "{Entity}.{field}: …" — anchor on the ':' boundary so a flagged
    # field "tag" does not falsely suppress drift on a different field "tags".
    prefixes = {f"{p}:" for p in _flag_prefixes(report)}
    kept, excluded = [], []
    for line in raw:
        if any(line.startswith(p) for p in prefixes):
            excluded.append(line)            # FR-DC-11: a ratified flagged item is not real drift
        else:
            kept.append(line)
    return DriftResult(schema_version=SCHEMA_VERSION,
                       verdict="drifted" if kept else "in_sync", drift=kept, excluded_flagged=excluded)


# ── public, contained entrypoints (the CLI / MCP call these) ─────────────────

def build_derivation(
    modules: List[str], *,
    project_pythonpath: Optional[str] = None,
    model_names: Optional[List[str]] = None,
    exclude_models: Optional[List[str]] = None,
    timeout: float = 30.0,
) -> DerivationResult:
    """Step 3 — derive a candidate contract + report from *modules* (contained introspection)."""
    result = run_contained_introspection(
        modules, project_pythonpath=project_pythonpath, model_names=model_names, timeout=timeout)
    derivation, _ = _assemble(result, exclude_models)
    return derivation


def check_drift(
    modules: List[str], *, live_schema_text: str,
    project_pythonpath: Optional[str] = None,
    model_names: Optional[List[str]] = None,
    exclude_models: Optional[List[str]] = None,
    timeout: float = 30.0,
) -> DriftResult:
    """Step 5 — re-derive and report drift vs *live_schema_text* (ratified-flagged suppressed)."""
    result = run_contained_introspection(
        modules, project_pythonpath=project_pythonpath, model_names=model_names, timeout=timeout)
    return _check(result, live_schema_text, exclude_models)
