# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""The proactive recommendation pass (Teian — FR-KIR-1/4/12/13/14).

Given a project's kickoff input package and a live :class:`~startd8.stakeholder_panel.panel.StakeholderPanel`,
walk the **unfilled** fields of each supported value domain, route each to the persona who *owns* the
domain, ask for a **starter estimate**, and stage the drafts out-of-band. It mirrors the reactive
:func:`~startd8.stakeholder_panel.vipp_bridge.consult_panel` shape (enumerate → resolve → preflight →
ask → status-tagged results) but is *proactive*: it drafts values, it does not answer OMIT claims.

Order of operations (the CRP-hardened contract):

1. **Enumerate** unfilled fields on the *live* YAML (a field filled directly by a human is no longer
   unfilled → naturally skipped, R3-S3); a composite metric row is one item (FR-KIR-4).
2. **Resolve owner** per domain (bounded — default role or high-confidence ``answers_for``, else skip
   the domain, FR-KIR-3/R3-F1). **Skip fields already drafted** in the session store unless
   ``redraft`` (no wasted re-spend, R2-S2/FR-KIR-12).
3. **Budget-preflight the resolved, capped set** — *after* resolution so an un-owned domain never
   inflates the count (R3-S1). On denial, defer everything and spend nothing.
4. **Ask** each owner for its field (sequential; the persona lock serializes anyway). An
   ``unavailable`` persona leaves the field unchanged and never aborts the pass (FR-KIR-13).
5. **Stage** the drafts (``estimate`` provenance) and return a :class:`RecommendationRun`.

The whole pass runs under a parent OTel span ``stakeholder.recommend_pass`` (R4-S3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from startd8.logging_config import get_logger
from startd8.stakeholder_panel.input_domains import (
    DOMAINS,
    SUPPORTED_DOMAINS,
    DomainSpec,
    FieldSlot,
    get_domain,
    resolve_owner,
    unfilled_fields,
)
from startd8.stakeholder_panel.contradiction_guard import check_contradiction
from startd8.stakeholder_panel.models import Grounding, Recommendation
from startd8.stakeholder_panel.proposals import ProposalStore
from startd8.stakeholder_panel.recommend_provenance import (
    ESTIMATE_PROVENANCE,
    panel_origin,
)
from startd8.stakeholder_panel.telemetry import span

__all__ = ["RecommendationRun", "recommend_inputs"]

logger = get_logger(__name__)

_MARKERS = ("VALUE", "TARGET", "WHY", "STATUS")


@dataclass
class RecommendationRun:
    """Result of a proactive pass: staged drafts + status-tagged skips + rolled-up cost."""

    session_id: str
    recommendations: List[Recommendation] = field(default_factory=list)
    skipped: List[Dict[str, Any]] = field(default_factory=list)
    fields_enumerated: int = 0
    fields_drafted: int = 0
    total_cost_usd: float = 0.0
    llm_used: bool = False


def _new_session_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"rec-{stamp}-{uuid4().hex[:8]}"


def _parse_markers(text: str) -> Dict[str, str]:
    """Extract ``VALUE:``/``TARGET:``/``WHY:``/``STATUS:`` markers from a persona reply (lenient)."""
    out: Dict[str, str] = {}
    for chunk in re.split(r"\|\||\n", text or ""):
        if ":" not in chunk:
            continue
        key, value = chunk.split(":", 1)
        key = key.strip().upper()
        if key in _MARKERS:
            out[key] = value.strip()
    return out


def _drafting_prompt(spec: DomainSpec, slot: FieldSlot) -> str:
    intro = (
        f'Kickoff input: recommend a STARTER value for the field "{slot.value_path}" in '
        f"{spec.name} ({spec.label}). It is a DRAFT a human will confirm, not a fact — give your "
        f"best estimate from your role, or DEFER if it is outside your remit.\n"
    )
    if slot.composite_keys == ("target", "why"):
        fmt = "TARGET: <your recommended value> || WHY: <one short sentence>"
    elif slot.composite_keys == ("target", "status"):
        fmt = "TARGET: <your recommended value> || STATUS: <dormant or active>"
    else:
        fmt = "VALUE: <your recommended value> || WHY: <one short sentence>"
    return intro + "Reply in ONE line, exactly:\n" + fmt


def _build_recommendation(
    spec: DomainSpec,
    slot: FieldSlot,
    owner: str,
    answer: Any,
    session_id: str,
    brief: Any,
) -> Recommendation:
    markers = _parse_markers(answer.text)
    primary = (
        markers.get("TARGET") or markers.get("VALUE") or (answer.text or "").strip()
    )
    if slot.composite_keys == ("target", "why"):
        value: Any = {"target": primary, "why": markers.get("WHY", "")}
        rationale = markers.get("WHY", "")
    elif slot.composite_keys == ("target", "status"):
        value = {"target": primary, "status": markers.get("STATUS", "")}
        rationale = ""
    else:
        value = primary
        rationale = markers.get("WHY", "")
    # FR-KIR-6: a drafted starter is an ESTIMATE (not grounded in a project fact by construction).
    # Do NOT carry the reactive "unsupported-specifics" flags — an estimate is expected to introduce
    # a value the brief never stated. The only guard that fires is a CONTRADICTION with the brief.
    flags = check_contradiction(brief, value) if brief is not None else []
    return Recommendation(
        domain=spec.name,
        value_path=slot.value_path,
        recommended_value=value,
        rationale=rationale,
        role_id=owner,
        grounding=Grounding.ESTIMATE,
        provenance=ESTIMATE_PROVENANCE,
        origin=panel_origin(owner),
        composite_keys=slot.composite_keys,
        brief_hash=answer.brief_hash,
        roster_version=getattr(answer, "roster_version", ""),
        session_id=session_id,
        model=answer.model,
        cost_usd=answer.cost_usd,
        disposition="draft",
        created_at=answer.created_at,
        flags=flags,
    )


def _default_domains(package_root: Path) -> List[str]:
    """Every supported domain whose YAML is present in the package (deterministic order)."""
    present = []
    for name in SUPPORTED_DOMAINS:
        if (package_root / DOMAINS[name].rel_path()).is_file():
            present.append(name)
    return present


async def recommend_inputs(
    package_root: Path | str,
    panel: Any,
    *,
    domains: Optional[List[str]] = None,
    cap: Optional[int] = None,
    redraft: bool = False,
    session_id: Optional[str] = None,
) -> RecommendationRun:
    """Draft starter values for the unfilled kickoff-input fields the panel's personas own.

    ``panel`` is duck-typed on ``.briefs`` / ``.ask`` / ``.preflight_budget`` / ``.session_id`` /
    ``.roster_version`` so this module takes no hard dependency on the concrete panel. Never raises for
    a persona failure (FR-KIR-13); a budget denial degrades to "defer all, spend nothing" (FR-KIR-12).
    """
    root = Path(package_root).expanduser()
    session_id = session_id or getattr(panel, "session_id", None) or _new_session_id()
    store = ProposalStore(root, session_id)
    existing = {(r.domain, r.value_path): r for r in store.load()}
    briefs = list(getattr(panel, "briefs", []))
    briefs_by_id = {b.role_id: b for b in briefs}

    run = RecommendationRun(session_id=session_id)
    domain_names = domains if domains is not None else _default_domains(root)

    # ── 1-2. enumerate + resolve owner + staging-aware skip ──────────────────
    plan_items: List[tuple] = []  # (spec, slot, owner)
    for dname in domain_names:
        spec = get_domain(dname)
        if spec is None:
            run.skipped.append({"domain": dname, "status": "unsupported"})
            continue
        path = root / spec.rel_path()
        if not path.is_file():
            run.skipped.append({"domain": dname, "status": "no-file"})
            continue
        text = path.read_text(encoding="utf-8")
        slots = unfilled_fields(spec, text)
        run.fields_enumerated += len(slots)
        owner = resolve_owner(dname, briefs)
        if owner is None:
            run.skipped.append({"domain": dname, "status": "no-owner"})
            continue
        for slot in slots:
            key = (dname, slot.value_path)
            prior = existing.get(key)
            if not redraft and prior is not None and prior.disposition == "draft":
                run.skipped.append(
                    {
                        "domain": dname,
                        "value_path": slot.value_path,
                        "status": "already-drafted",
                    }
                )
                continue
            plan_items.append((spec, slot, owner))

    # ── 3. budget preflight AFTER resolution (R3-S1) ─────────────────────────
    to_ask = plan_items if cap is None else plan_items[: max(0, cap)]
    deferred = [] if cap is None else plan_items[max(0, cap) :]
    for spec, slot, _owner in deferred:
        run.skipped.append(
            {
                "domain": spec.name,
                "value_path": slot.value_path,
                "status": "deferred-cap",
            }
        )

    preflight = getattr(panel, "preflight_budget", None)
    if to_ask and callable(preflight):
        try:
            preflight(len(to_ask))
        except Exception as exc:  # noqa: BLE001 - a preflight signals denial by raising
            logger.warning(
                "recommend pass budget-denied (%d asks); deferring all, no spend: %s",
                len(to_ask),
                exc,
            )
            for spec, slot, _owner in to_ask:
                run.skipped.append(
                    {
                        "domain": spec.name,
                        "value_path": slot.value_path,
                        "status": "deferred-budget",
                    }
                )
            return run

    # ── 4-5. ask + stage, under the parent span (R4-S3) ──────────────────────
    with span(
        "stakeholder.recommend_pass",
        **{
            "panel.session_id": session_id,
            "recommend.fields_enumerated": run.fields_enumerated,
            "recommend.fields_to_ask": len(to_ask),
        },
    ) as active_span:
        new_recs: List[Recommendation] = []
        for spec, slot, owner in to_ask:
            answer = await panel.ask(
                owner, _drafting_prompt(spec, slot), value_path=slot.value_path
            )  # never raises (FR-KIR-13)
            # A failed call (unavailable) or an in-character DEFERRAL both leave the field unchanged
            # and never fabricate a value (FR-KIR-13 / FR-7): a persona declining "outside my remit"
            # must not be turned into a drafted starter.
            if answer.grounding in (Grounding.UNAVAILABLE, Grounding.DEFERRED):
                status = (
                    "unavailable"
                    if answer.grounding is Grounding.UNAVAILABLE
                    else "deferred-persona"
                )
                run.skipped.append(
                    {
                        "domain": spec.name,
                        "value_path": slot.value_path,
                        "status": status,
                        "role_id": owner,
                    }
                )
                continue
            rec = _build_recommendation(
                spec, slot, owner, answer, session_id, briefs_by_id.get(owner)
            )
            new_recs.append(rec)
            run.total_cost_usd += rec.cost_usd

        run.recommendations = new_recs
        run.fields_drafted = len(new_recs)
        run.llm_used = bool(new_recs)
        _stamp_span(active_span, run)

    # Merge new drafts over any prior session record and persist the full set.
    if new_recs:
        merged = dict(existing)
        for rec in new_recs:
            merged[(rec.domain, rec.value_path)] = rec
        store.save(list(merged.values()))
    return run


def _stamp_span(active_span: object, run: RecommendationRun) -> None:
    from startd8.agents.agentic_otel import set_attributes

    set_attributes(
        active_span,
        **{
            "recommend.fields_drafted": run.fields_drafted,
            "recommend.total_cost_usd": run.total_cost_usd,
        },
    )
