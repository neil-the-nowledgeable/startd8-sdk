# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Role-informed drafting pass (FR-RP-2 — paid, opt-in).

Mirrors the *pattern* of ``stakeholder_panel.recommend_inputs`` but with **owned** enumeration and
owner-resolution (the "mirror ``recommend_inputs``" reuse failed twice — R1-S1/R2-S1). Reuse-vs-own:

* **Reuse:** ``panel.ask`` (cost/transcript/budget/OTel — NOT a bare ``Persona.ask``, R1-S1),
  ``panel.preflight_budget``, ``telemetry.span``.
* **Own:** domain **enumeration** (:func:`requirement_domains`), **owner resolution**
  (:func:`resolve_requirement_owner`), and **grounding** (:func:`ground_requirement`).

The drafting prompt carries the **brief + the literal declared entity names** (R2-F3), so a
data-touching FR references real entities verbatim. Never raises for a persona failure; a budget denial
degrades to "defer all, spend nothing". Every candidate is sanitized (FR-RP-7) and grounded (FR-RP-4)
before staging; nothing is fabricated (an ``UNAVAILABLE``/``DEFERRED`` persona leaves the area empty).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from startd8.languages.prisma_parser import parse_prisma_schema
from startd8.logging_config import get_logger
from startd8.stakeholder_panel.models import Grounding
from startd8.stakeholder_panel.recommend_provenance import panel_origin
from startd8.stakeholder_panel.telemetry import span

from startd8.requirements_panel.domains import (
    RequirementDomain,
    requirement_domains,
    resolve_requirement_owner,
)
from startd8.requirements_panel.grounding import ground_requirement
from startd8.requirements_panel.models import (
    PROV_ESTIMATE,
    RequirementCandidate,
)
from startd8.requirements_panel.sanitize import neutralize_headings

__all__ = ["ElicitationRun", "elicit_requirements", "schema_entity_names"]

logger = get_logger(__name__)

_MARKERS = ("TITLE", "REQUIREMENT", "WHY")


@dataclass
class ElicitationRun:
    """Result of a paid pass: staged candidates + status-tagged skips + rolled-up cost."""

    session_id: str
    candidates: List[RequirementCandidate] = field(default_factory=list)
    skipped: List[Dict[str, Any]] = field(default_factory=list)
    areas_enumerated: int = 0
    areas_drafted: int = 0
    total_cost_usd: float = 0.0
    llm_used: bool = False


def schema_entity_names(schema_text: str) -> List[str]:
    """The declared model names — the literal entity vocabulary handed to the drafting prompt (R2-F3)."""
    schema = parse_prisma_schema(schema_text or "")
    return list(schema.models.keys())


def _parse_markers(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for chunk in re.split(r"\|\||\n", text or ""):
        if ":" not in chunk:
            continue
        key, value = chunk.split(":", 1)
        key = key.strip().upper()
        if key in _MARKERS:
            out[key] = value.strip()
    return out


def _drafting_prompt(
    domain: RequirementDomain, brief: str, entities: Sequence[str]
) -> str:
    ent = ", ".join(entities) if entities else "(no declared entities)"
    return (
        f"Requirements elicitation for the '{domain.area}' area ({domain.label}). "
        f"Project brief:\n{brief.strip() or '(none provided)'}\n\n"
        f"The declared schema entities (use these EXACT names when referencing data): {ent}.\n\n"
        f"Propose ONE candidate requirement from your role's perspective. It is a DRAFT a human will "
        f"approve, not a decision — or DEFER if this area is outside your remit. Reply in ONE line:\n"
        f"TITLE: <short imperative title> || REQUIREMENT: The system MUST <one testable sentence> || "
        f"WHY: <one short sentence>"
    )


def _build_candidate(
    domain: RequirementDomain,
    owner: str,
    answer: Any,
    brief: str,
    entities: Sequence[str],
    session_id: str,
) -> RequirementCandidate:
    markers = _parse_markers(answer.text)
    title = markers.get("TITLE") or f"{domain.area} requirement"
    body = markers.get("REQUIREMENT") or (answer.text or "").strip()
    rationale = markers.get("WHY", "")
    # FR-RP-7: sanitize every free-text field BEFORE it can enter the assembled doc.
    title = neutralize_headings(title)
    body = neutralize_headings(body)
    rationale = neutralize_headings(rationale)
    # Which declared entities does this candidate name verbatim? (feeds the grounding schema check)
    referenced = tuple(e for e in entities if re.search(rf"\b{re.escape(e)}\b", body))
    flags = ground_requirement(
        text=f"{body} {rationale}",
        entities_referenced=referenced,
        brief=brief,
        schema_entities=entities,
    )
    return RequirementCandidate(
        area=domain.area,
        title=title,
        body=body,
        rationale=rationale,
        entities_referenced=referenced,
        provenance=PROV_ESTIMATE,
        role_id=owner,
        model=getattr(answer, "model", ""),
        cost_usd=getattr(answer, "cost_usd", 0.0),
        session_id=session_id,
        created_at=getattr(answer, "created_at", ""),
        flags=[f.render() for f in flags],
    )


async def elicit_requirements(
    package_root: Any,
    panel: Any,
    *,
    brief: str = "",
    schema_text: str = "",
    domains: Optional[Sequence[str]] = None,
    cap: Optional[int] = None,
    session_id: Optional[str] = None,
) -> ElicitationRun:
    """Draft candidate requirements for the areas the panel's personas own (FR-RP-2).

    ``panel`` is duck-typed on ``.briefs`` / ``.ask`` / ``.preflight_budget``. Never raises for a
    persona failure; a budget denial degrades to "defer all, spend nothing".
    """
    session_id = session_id or getattr(panel, "session_id", None) or "elicit-session"
    briefs = list(getattr(panel, "briefs", []))
    entities = schema_entity_names(schema_text)

    run = ElicitationRun(session_id=session_id)
    doms = requirement_domains(domains)

    # ── enumerate + resolve owner (owned — R1-S1/R2-S1) ──────────────────────
    plan_items: List[tuple] = []  # (domain, owner)
    for dom in doms:
        run.areas_enumerated += 1
        owner = resolve_requirement_owner(dom, briefs)
        if owner is None:
            run.skipped.append({"area": dom.area, "status": "no-owner"})
            continue
        plan_items.append((dom, owner))

    to_ask = plan_items if cap is None else plan_items[: max(0, cap)]
    for dom, _o in (plan_items[max(0, cap) :] if cap is not None else []):
        run.skipped.append({"area": dom.area, "status": "deferred-cap"})

    # ── budget preflight AFTER resolution ────────────────────────────────────
    preflight = getattr(panel, "preflight_budget", None)
    if to_ask and callable(preflight):
        try:
            preflight(len(to_ask))
        except Exception as exc:  # noqa: BLE001 - a preflight signals denial by raising
            logger.warning(
                "elicit budget-denied (%d asks); deferring all: %s", len(to_ask), exc
            )
            for dom, _o in to_ask:
                run.skipped.append({"area": dom.area, "status": "deferred-budget"})
            return run

    # ── ask + ground + stage, under the parent span ──────────────────────────
    with span(
        "requirements.elicit_pass",
        **{
            "requirements.session_id": session_id,
            "requirements.areas_enumerated": run.areas_enumerated,
            "requirements.areas_to_ask": len(to_ask),
        },
    ):
        new: List[RequirementCandidate] = []
        for dom, owner in to_ask:
            answer = await panel.ask(
                owner, _drafting_prompt(dom, brief, entities), value_path=dom.area
            )
            if answer.grounding in (Grounding.UNAVAILABLE, Grounding.DEFERRED):
                status = (
                    "unavailable"
                    if answer.grounding is Grounding.UNAVAILABLE
                    else "deferred-persona"
                )
                run.skipped.append(
                    {"area": dom.area, "status": status, "role_id": owner}
                )
                continue
            cand = _build_candidate(dom, owner, answer, brief, entities, session_id)
            new.append(cand)
            run.total_cost_usd += cand.cost_usd

    run.candidates = new
    run.areas_drafted = len(new)
    run.llm_used = bool(new)
    return run


# Keep the panel-origin marker importable for consumers that want the persona attribution string.
_ = panel_origin
