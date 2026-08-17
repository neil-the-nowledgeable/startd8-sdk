"""The ``$0`` det-req → det-plan/0.1 projector (REQ-29 FR-1/FR-2/FR-3/FR-4).

``generate plan --requirements <req>`` reads a det-req and **deterministically projects** a
``det-plan/0.1`` document — the "generate plan" analog of "generate backend". It is a **pure
function of the requirement** (no LLM, no network): every field derives from the req.

- **iterations** ← the FRs (default: one iteration per FR — the transparent scaffold; ``shared-touches``
  batches FRs sharing a ``Touches`` file). Strategic role-based batching is the human-gated residue.
- **targetFiles** ← the FRs' ``Touches`` refs.
- **dependsOn** ← the FRs' *authored* ``Depends:`` edges only (acyclic via ``queue.py`` cycle
  detection); **never** an edge the requirement did not declare.
- **gate** ← the FRs' ``Verify:`` clauses (the requirement→test seed, per iteration).
- **costClass** ← the realization regime (the ``RealizationRegime`` vocabulary → a cost band).

Fires **only** on a plan-owed REQ (FR-3): a solo-by-design REQ projects nothing. A projected plan
is stamped ``maturity: 0.1`` (FR-4 anti-inflation).

Reuse (Mottainai), never rebuild: ``navigator.det_req.parse_fr_lines`` (the FRs),
``contractors.queue.FeatureQueue`` (acyclic cycle detection), ``navigator.naming.name_forms``
(DIDL), ``navigator.realization.RealizationRegime`` (the regime vocabulary).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from ..contractors.queue import FeatureQueue
from ..navigator.det_req import parse_fr_lines
from ..navigator.naming import name_forms
from ..navigator.realization import RealizationRegime
from .models import (
    COMPANION_KIND,
    COST_DETERMINISTIC,
    COST_HUMAN,
    COST_LLM,
    FORMAT_VERSION,
    PROJECTED_MATURITY,
    DetPlan,
    GateClause,
    Iteration,
)


class PlanDependencyCycleError(ValueError):
    """Raised when a requirement's authored ``Depends:`` topology contains a cycle (FR-2).

    The projector refuses to invent an ordering to break it — a cyclic requirement is a defect the
    author must resolve. Named (not a bare ``ValueError``) so the caller can report it as such.
    """


class NotPlanOwedError(ValueError):
    """Raised when the projector is asked to project a solo-by-design REQ (FR-3).

    A REQ that does not *owe* a plan (no ``plan deferred``/``plan follows`` marker and no ``PLAN-``
    companion) projects **nothing** — the honest solo-vs-gap gate; do not invent ceremony.
    """


# ── The $0-deterministic codegen modules (bucket 1). A target under one of these — and not a
#    test — is realized by the deterministic cascade (deterministic-$0); everything else is
#    contractor-built (llm-integration); a doc-only FR is human-authored content (human).
_DET_CODEGEN_MARKERS = (
    "backend_codegen",
    "frontend_codegen",
    "scaffold_codegen",
    "view_codegen",
    "presentation_polish",
    "plan_codegen",
)

# A ``Depends: FR-x, FR-y`` field authored on an FR bullet — the ONLY source of a dependency edge
# (FR-2 never-inferred). ``det_req`` recognizes ``Depends`` as a Lives-stop label but does not
# extract it, so the projector reads it from the raw FR line.
_DEPENDS = re.compile(r"(?:\*\*)?\bDepends:(?:\*\*)?\s*(?P<body>[^.]*)", re.IGNORECASE)
# The whole authored ``Depends: …`` span (period-terminated) — stripped before ``parse_fr_lines`` so
# it does not pollute the ``Touches`` capture (det-req's parser has no ``Depends`` field slot: Touches
# runs up to Verify, and Verify swallows to EOL, so an authored Depends between them leaks into
# Touches — a grammar gap the pilot records, FR-7).
_DEPENDS_SPAN = re.compile(r"\s*(?:\*\*)?\bDepends:(?:\*\*)?\s*[^.]*\.?", re.IGNORECASE)
_FR_ID = re.compile(r"FR-[\w-]+")
_FR_LINE = re.compile(r"^- \*\*(FR-[\w-]+)\s*[—-]")

# Header fields (the DIDL block + the Pairs-with companion declaration).
_SEMANTIC_NAME = re.compile(
    r"^>\s*\*\*Semantic name:\*\*\s*\*?(?P<n>.+?)\*?\s*$", re.MULTILINE
)
_CANONICAL_REF = re.compile(
    r"^>\s*\*\*Canonical ref:\*\*\s*`?(?P<r>[^`\n]+?)`?\s*$", re.MULTILINE
)
_PAIRS_WITH = re.compile(r"^\*\*Pairs with:\*\*\s*(?P<p>.+?)\s*$", re.MULTILINE)
_TITLE = re.compile(r"^#\s+(?P<t>.+?)\s*$", re.MULTILINE)
_PLAN_REF = re.compile(r"PLAN-[\w./-]+")


# ────────────────────────────────────────────────────────────────────────────────────────────────
# Header + gate
# ────────────────────────────────────────────────────────────────────────────────────────────────


def _first(pattern: re.Pattern, text: str, group: str) -> str:
    m = pattern.search(text)
    return m.group(group).strip() if m else ""


def pairs_with_line(req_text: str) -> str:
    """The req's ``**Pairs with:**`` declaration (empty when absent)."""
    return _first(_PAIRS_WITH, req_text, "p")


def is_plan_owed(req_text: str) -> bool:
    """FR-3 solo-vs-gap gate: does this REQ *owe* a plan?

    A REQ is plan-owed iff its ``Pairs with:`` line either carries the ``plan deferred``/``plan
    follows`` marker (a companion owed but not yet delivered) OR names a ``PLAN-…`` companion (an
    existing/intended plan). A REQ whose ``Pairs with:`` names only a non-plan artifact (a brief, an
    ADR, a sibling REQ) — or has no ``Pairs with:`` at all — is **solo-by-design**: it projects
    nothing (charter §6.4; do not invent ceremony).
    """
    pairs = pairs_with_line(req_text).lower()
    if not pairs:
        return False
    if "plan deferred" in pairs or "plan follows" in pairs:
        return True
    return bool(_PLAN_REF.search(pairs_with_line(req_text)))


def _req_key(req_text: str, req_path: Optional[Path]) -> str:
    """The canonical key for the plan's DIDL ref — the req's ``…:req-NN`` tail, else its filename."""
    ref = _first(_CANONICAL_REF, req_text, "r")
    if ref:
        return ref.rsplit(":", 1)[-1].strip()
    if req_path is not None:
        return req_path.stem.lower()
    return "req"


# ────────────────────────────────────────────────────────────────────────────────────────────────
# FR grouping (batch by shared Touches) + per-iteration derivation
# ────────────────────────────────────────────────────────────────────────────────────────────────


def _ordinal(fr_id: str) -> Tuple[int, str]:
    """Sort key for an FR id: its leading integer then the raw id (``FR-10`` after ``FR-2``)."""
    m = re.search(r"\d+", fr_id)
    return (int(m.group()) if m else 1_000_000, fr_id)


# Grouping strategies (how FRs batch into iterations).
GROUP_PER_FR = "per-fr"
GROUP_SHARED_TOUCHES = "shared-touches"


def _group_per_fr(frs: Sequence[dict]) -> List[List[dict]]:
    """One iteration per FR — the transparent, never-inferred scaffold (the default).

    The pilot (FR-7) found that *strategic* FR batching (foundation → logic → integration) is human
    judgment the requirement does not encode — the two golden PLANs batch the SAME FRs differently
    by role, not by any authored signal. So the projector emits the honest mechanical scaffold (one
    iteration per FR, ordered by ordinal) and leaves the strategic re-batching as the human-gated
    residue (charter: "the ordering strategy is the human-gated residue"). ``shared-touches`` remains
    available for a coarser projection.
    """
    return [[fr] for fr in sorted(frs, key=lambda fr: _ordinal(fr["id"]))]


def _group_by_shared_touches(frs: Sequence[dict]) -> List[List[dict]]:
    """Batch FRs into iterations by **shared ``Touches`` connected components** (SCHEMA §2).

    Two FRs land in the same iteration when they (transitively) share ≥1 ``Touches`` file — the
    authored grouping the format calls for. ``Touches`` is authored, so this invents nothing; an FR
    with no ``Touches`` is its own singleton iteration. Components are returned ordered by their
    lowest FR ordinal (deterministic, stable across runs).

    NOTE (pilot friction, FR-7): the transitive closure **over-merges** on a hub file — a REQ where
    many FRs touch one shared module (e.g. ``cli_navigator.py``) collapses to a single giant
    iteration (REQ-08's 9 FRs → 1). Hence ``per-fr`` is the default; this stays opt-in.
    """
    # Union-find over FR indices keyed by shared file.
    parent = list(range(len(frs)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        parent[find(a)] = find(b)

    file_to_first: Dict[str, int] = {}
    for idx, fr in enumerate(frs):
        for f in fr.get("touches") or []:
            key = f.strip().strip("`")
            if not key:
                continue
            if key in file_to_first:
                union(idx, file_to_first[key])
            else:
                file_to_first[key] = idx

    comps: Dict[int, List[dict]] = {}
    for idx, fr in enumerate(frs):
        comps.setdefault(find(idx), []).append(fr)

    groups = list(comps.values())
    for g in groups:
        g.sort(key=lambda fr: _ordinal(fr["id"]))
    groups.sort(key=lambda g: _ordinal(g[0]["id"]))
    return groups


def _clean_files(frs: Sequence[dict]) -> Tuple[str, ...]:
    seen: List[str] = []
    for fr in frs:
        for f in fr.get("touches") or []:
            key = f.strip().strip("`")
            if key and key not in seen:
                seen.append(key)
    return tuple(sorted(seen))


def _regime_of_fr(fr: dict) -> str:
    """The realization regime of a single FR (the ``RealizationRegime`` vocabulary).

    Driven by what the FR **builds** (its ``Touches``), NOT by an incidental doc citation:

    - ``deterministic`` — the FR has code ``Touches`` and every one is under a ``$0`` codegen module
      and none is a test (bucket 1, the deterministic cascade).
    - ``llm`` — the FR has code ``Touches`` outside those modules (contractor-built integration,
      bucket 3). The honest default for hand-written SDK code; a coarse band the pilot records.
    - ``human`` — the FR builds no code (no ``Touches``) and its ``Lives`` are all ``doc`` (authored
      content, bucket 4). Checked LAST so an FR that Touches code but *cites* a doc vocabulary-home
      is not mis-banded ``human`` (the REQ-08 FR-1 case the pilot surfaced).
    """
    touches = [f.strip().strip("`") for f in (fr.get("touches") or []) if f.strip()]
    if touches:
        if all(
            any(m in t for m in _DET_CODEGEN_MARKERS) and "test" not in t
            for t in touches
        ):
            return RealizationRegime.DETERMINISTIC
        return RealizationRegime.LLM
    lives = fr.get("lives") or []
    live_types = {(e.get("type") or "").lower() for e in lives}
    if lives and live_types == {"doc"}:
        return RealizationRegime.HUMAN
    return RealizationRegime.LLM


_REGIME_TO_COST = {
    RealizationRegime.DETERMINISTIC: COST_DETERMINISTIC,
    RealizationRegime.LLM: COST_LLM,
    RealizationRegime.HUMAN: COST_HUMAN,
}
_COST_RANK = {COST_DETERMINISTIC: 0, COST_LLM: 1, COST_HUMAN: 2}


def _cost_class(frs: Sequence[dict]) -> str:
    """The iteration cost band — the most-costly regime among its FRs (a batch is as dear as its
    dearest FR: a doc FR makes the batch ``human``, an integration FR makes it ``llm-integration``).
    """
    costs = [_REGIME_TO_COST[_regime_of_fr(fr)] for fr in frs]
    return max(costs, key=lambda c: _COST_RANK[c]) if costs else COST_LLM


def _iteration_name(frs: Sequence[dict]) -> str:
    """The iteration's DIDL semantic name — the lowest-ordinal FR's authored ``Name:`` (actor·
    action·object·outcome), falling back to its title/behavior."""
    lead = frs[0]
    return (
        lead.get("name") or lead.get("title") or lead.get("behavior") or lead["id"]
    ).strip()


def _parse_depends(raw_line: str) -> Tuple[str, ...]:
    """The authored ``Depends: FR-x, FR-y`` edge list on an FR bullet (empty when unauthored)."""
    m = _DEPENDS.search(raw_line)
    if not m:
        return ()
    return tuple(_FR_ID.findall(m.group("body")))


def _fr_depends_map(req_text: str) -> Dict[str, Tuple[str, ...]]:
    """Map each FR id → its authored ``Depends:`` FR ids, read from the raw FR bullet lines."""
    out: Dict[str, Tuple[str, ...]] = {}
    for raw in req_text.splitlines():
        m = _FR_LINE.match(raw.strip())
        if not m:
            continue
        out[m.group(1)] = _parse_depends(raw)
    return out


# ────────────────────────────────────────────────────────────────────────────────────────────────
# Cycle detection (reuse queue.py) + projection
# ────────────────────────────────────────────────────────────────────────────────────────────────


def _assert_acyclic(edges: Dict[str, List[str]]) -> None:
    """Reject a cyclic iteration graph via ``queue.py``'s cycle detector (FR-2), fail-loud.

    Reuses ``FeatureQueue._find_cycles`` (the same guard the corpus DAG self-study used) rather than
    silently breaking the cycle — a cyclic authored topology is a requirement defect.
    """
    cycles = FeatureQueue._find_cycles({k: list(v) for k, v in edges.items()})
    if cycles:
        pretty = "; ".join(" → ".join(c) for c in cycles)
        raise PlanDependencyCycleError(
            f"authored Depends: topology is cyclic ({pretty}) — the projector never invents an "
            "ordering to break it; fix the requirement's dependency declarations"
        )


def project_plan(
    req_text: str, *, req_path: Optional[Path] = None, strategy: str = GROUP_PER_FR
) -> DetPlan:
    """Project a det-req into a :class:`DetPlan` — the pure ``$0`` function of the requirement.

    ``strategy`` selects the FR→iteration grouping: ``"per-fr"`` (default — one iteration per FR, the
    honest scaffold) or ``"shared-touches"`` (batch FRs sharing a ``Touches`` file). Raises
    :class:`NotPlanOwedError` for a solo-by-design REQ (FR-3) and :class:`PlanDependencyCycleError`
    for a cyclic authored ``Depends:`` topology (FR-2). Makes no network/LLM call.
    """
    if not is_plan_owed(req_text):
        raise NotPlanOwedError(
            "requirement is solo-by-design (no `plan deferred`/`plan follows` marker and no "
            "`PLAN-…` companion) — a solo REQ projects no plan (FR-3)"
        )

    # Read authored Depends: from the raw text, THEN strip those spans so they don't pollute the
    # Touches capture (det-req has no Depends field slot — see _DEPENDS_SPAN).
    depends = _fr_depends_map(req_text)
    frs = parse_fr_lines(_DEPENDS_SPAN.sub("", req_text))
    if not frs:
        raise ValueError(
            "requirement declares no parseable FR bullets — nothing to project"
        )
    if strategy == GROUP_SHARED_TOUCHES:
        groups = _group_by_shared_touches(frs)
    elif strategy == GROUP_PER_FR:
        groups = _group_per_fr(frs)
    else:
        raise ValueError(
            f"unknown grouping strategy {strategy!r} (use 'per-fr' or 'shared-touches')"
        )

    # Assign iteration ids and a FR→iteration index for dependency resolution.
    fr_to_iter: Dict[str, str] = {}
    for i, g in enumerate(groups, start=1):
        for fr in g:
            fr_to_iter[fr["id"]] = f"F-{i}"

    iterations: List[Iteration] = []
    edges: Dict[str, List[str]] = {}
    for i, g in enumerate(groups, start=1):
        iter_id = f"F-{i}"
        # dependsOn: authored FR Depends: edges mapped to the *containing* iteration (self-edges and
        # dupes dropped). An unknown/absent Depends: target yields no edge — never inferred.
        dep_iters: List[str] = []
        for fr in g:
            for dep_fr in depends.get(fr["id"], ()):  # authored deps only
                dep_iter = fr_to_iter.get(dep_fr)
                if dep_iter and dep_iter != iter_id and dep_iter not in dep_iters:
                    dep_iters.append(dep_iter)
        edges[iter_id] = list(dep_iters)
        gate = tuple(
            GateClause(fr=fr["id"], verify=fr.get("verify") or "")
            for fr in g
            if (fr.get("verify") or "").strip()
        )
        iterations.append(
            Iteration(
                id=iter_id,
                name=_iteration_name(g),
                frs=tuple(fr["id"] for fr in g),
                target_files=_clean_files(g),
                depends_on=tuple(dep_iters),
                gate=gate,
                cost_class=_cost_class(g),
            )
        )

    _assert_acyclic(edges)

    # Plan-level Verify rollup (§5): every FR's verify carried forward, in FR order.
    verify_rollup = tuple(
        GateClause(fr=fr["id"], verify=fr.get("verify") or "")
        for fr in sorted(frs, key=lambda fr: _ordinal(fr["id"]))
        if (fr.get("verify") or "").strip()
    )

    # Reuse/phantom audit (§4): each authored Touches/Lives ref + whether it resolves on disk.
    reuse_refs = _reuse_audit(frs, req_path)

    name = (
        _first(_SEMANTIC_NAME, req_text, "n")
        or _first(_TITLE, req_text, "t")
        or "projected plan"
    )
    key = _req_key(req_text, req_path)
    forms = name_forms(name, key, initiative="requirements-visualization", kind="plan")

    pairs = req_path.name if req_path is not None else "(source req)"

    return DetPlan(
        version="0.1",
        format_version=FORMAT_VERSION,
        pairs_with=pairs,
        companion_kind=COMPANION_KIND,
        maturity=PROJECTED_MATURITY,
        name=forms["name"],
        handle=forms["handle"],
        ref=forms["canonical"],
        iterations=tuple(iterations),
        verify_rollup=verify_rollup,
        reuse_refs=reuse_refs,
    )


def _reuse_audit(
    frs: Sequence[dict], req_path: Optional[Path]
) -> Tuple[Tuple[str, bool], ...]:
    """The §4 phantom audit: resolve each authored ``Touches``/code-``Lives`` ref on disk.

    A ref that names an existing file resolves ``True``; a claimed-existing ref that is absent
    resolves ``False`` (the honest-grounding flag, at the plan altitude). Resolved relative to the
    repo root inferred from the req path; when no root is available every ref is reported unresolved
    (honest — we cannot claim presence we cannot check).
    """
    root = _repo_root(req_path)
    seen: List[str] = []
    out: List[Tuple[str, bool]] = []
    refs: List[str] = []
    for fr in frs:
        for f in fr.get("touches") or []:
            refs.append(f.strip().strip("`"))
        for e in fr.get("lives") or []:
            if (e.get("type") or "").lower() == "code":
                refs.append((e.get("ref") or "").strip().strip("`"))
    for ref in refs:
        if not ref or ref in seen:
            continue
        seen.append(ref)
        resolved = bool(root) and (root / ref).exists()
        out.append((ref, resolved))
    return tuple(out)


def _repo_root(req_path: Optional[Path]) -> Optional[Path]:
    """Infer the repo root from the req path (walk up to a dir containing ``src/startd8``)."""
    if req_path is None:
        return None
    for parent in [req_path.resolve()] + list(req_path.resolve().parents):
        if (parent / "src" / "startd8").is_dir():
            return parent
    return None
