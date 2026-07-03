# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Role-informed screen drafting (FR-MS-2 — paid, opt-in) + heading sanitization (FR-MS-6).

Mirrors the Requirements Panel's ``elicit`` *pattern* but for screens: route the ``views``/``pages``
symbol to its owning persona, ask via **``StakeholderPanel.ask``** (never a bare ``Persona.ask`` — the
cost/telemetry/transcript lesson, R1-S1), draft a composite view **grounded in the entity facts** (the
prompt carries the *literal declared entity names*, R2-S3), and stage it. Two safety wirings:

* **Sanitization (FR-MS-6 / R3-S1).** The persona's free-text (the screen name) is neutralized
  (``persona_drafting.neutralize_headings``) before it is spliced into the ``### view:`` heading, so a
  persona can never inject an extra ``### view:``/``## Appendix`` section.
* **Join-gated + grounded (FR-MS-1/4).** ``Shows:`` targets are kept only where an M2M ``join_between``
  exists, and the built candidate is run through the schema-anchored guard — so a role-drafted screen
  is round-trip-safe by construction, not by hope.

Reuses the shared ``persona_drafting`` toolkit (``resolve_bounded_owner`` + ``neutralize_headings``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from startd8.logging_config import get_logger
from startd8.manifest_extraction.grammar import nfkd_kebab
from startd8.persona_drafting import neutralize_headings, resolve_bounded_owner
from startd8.stakeholder_panel.models import Grounding
from startd8.stakeholder_panel.telemetry import span

from startd8.manifest_suggester.baseline import build_graph
from startd8.manifest_suggester.grounding import ground
from startd8.manifest_suggester.models import (
    KIND_PAGE,
    KIND_VIEW,
    PROV_ESTIMATE,
    ScreenCandidate,
)

__all__ = [
    "SCREEN_SYMBOL",
    "SCREEN_OWNING_ROLE",
    "SCREEN_ALIASES",
    "SuggestRun",
    "suggest_screens",
]

logger = get_logger(__name__)

# The screens symbol routes like a value_path (OQ-4): a design/PM persona owns `views`/`pages`.
SCREEN_SYMBOL = "views"
SCREEN_OWNING_ROLE = "designer"
SCREEN_ALIASES = ("pages", "screens", "ui", "views")

_MARKERS = ("NAME", "KIND", "ROOT", "SHOWS")
# v1 role pass drafts the 3 simplest kinds (the doc's deliberate subset of the 7-value vocabulary).
_V1_KINDS = ("dashboard", "board", "workspace")


@dataclass
class SuggestRun:
    session_id: str
    candidates: List[ScreenCandidate] = field(default_factory=list)
    skipped: List[Dict[str, Any]] = field(default_factory=list)
    total_cost_usd: float = 0.0
    llm_used: bool = False


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


def _drafting_prompt(entities: List[str]) -> str:
    ent = ", ".join(entities) if entities else "(no declared entities)"
    return (
        "Propose ONE non-obvious SCREEN this product needs beyond basic entity CRUD — either a composite "
        "VIEW over the data (a dashboard/board/workspace) OR a non-entity PAGE (e.g. a settings or about "
        f"page). Use ONLY these EXACT declared entity names in a view: {ent}.\n"
        "It is a DRAFT a human will approve, not a decision — or DEFER if nothing non-obvious is needed.\n"
        "Reply in ONE line, exactly:\n"
        "NAME: <short screen name> || KIND: <dashboard|board|workspace|page> || ROOT: <one entity, or "
        "none for a page> || SHOWS: <comma-separated related entities, or none>"
    )


def _build_page_candidate(
    name: str, owner: str, answer: Any, session_id: str
) -> ScreenCandidate:
    """A non-entity page shell (FR-MS-2): the structural `## Pages` row; the content file is the human's."""
    name = (
        name.replace("|", "/").strip() or "Page"
    )  # a `|` would break the markdown table cell
    slug = nfkd_kebab(name)
    prose = (
        "## Pages\n\n| Page | Content file |\n| ---- | ---- |\n"
        f"| {name} | {slug}.md |\n"
    )
    return ScreenCandidate(
        kind=KIND_PAGE,
        name=name,
        prose=prose,
        entities_referenced=(),  # a non-entity page grounds trivially (no entity to resolve)
        provenance=PROV_ESTIMATE,
        role_id=owner,
        model=getattr(answer, "model", ""),
        cost_usd=getattr(answer, "cost_usd", 0.0),
        session_id=session_id,
        created_at=getattr(answer, "created_at", ""),
    )


def _build_candidate(
    graph, owner: str, answer: Any, session_id: str
) -> Optional[ScreenCandidate]:
    markers = _parse_markers(answer.text)
    # FR-MS-6: sanitize the persona free-text (name) BEFORE it becomes a `### view:` heading / page row.
    name = neutralize_headings(markers.get("NAME", "").strip()) or "Overview"
    kind = markers.get("KIND", "dashboard").strip().lower()
    if kind == "page":
        return _build_page_candidate(name, owner, answer, session_id)
    if kind not in _V1_KINDS:
        kind = "dashboard"
    root = (
        graph.resolve_entity(markers.get("ROOT", "")) if markers.get("ROOT") else None
    )
    if root is None:
        return (
            None  # no resolvable root → not a groundable screen (skip, never fabricate)
        )

    # Shows: keep only entities the graph's M2M joins actually connect to the root (R1-F2).
    partners: List[str] = []
    for raw in re.split(r"[,\s]+", markers.get("SHOWS", "")):
        ent = graph.resolve_entity(raw) if raw and raw.lower() != "none" else None
        if (
            ent
            and ent != root
            and graph.join_between(root, ent)
            and ent not in partners
        ):
            partners.append(ent)

    lines = [f"### view: {name}", f"- Kind: {kind}", f"- Root: {root}"]
    if kind == "board":
        # board requires `Group by:` — pick a scalar field on the root (round-trip requirement).
        field_name = next((f.name for f in graph.entities[root].fields), None)
        if field_name is None:
            return None
        lines.append(f"- Group by: {field_name}")
    for partner in partners:
        lines.append(f"- Shows: {root}→{partner}")
    prose = "\n".join(lines) + "\n"

    return ScreenCandidate(
        kind=KIND_VIEW,
        name=name,
        prose=prose,
        entities_referenced=(root, *partners),
        provenance=PROV_ESTIMATE,
        role_id=owner,
        model=getattr(answer, "model", ""),
        cost_usd=getattr(answer, "cost_usd", 0.0),
        session_id=session_id,
        created_at=getattr(answer, "created_at", ""),
    )


async def suggest_screens(
    package_root: Any,
    panel: Any,
    *,
    schema_text: str = "",
    cap: Optional[int] = None,
    session_id: Optional[str] = None,
) -> SuggestRun:
    """Draft non-obvious composite screens via the panel's owning persona (FR-MS-2). Never fabricates."""
    session_id = session_id or getattr(panel, "session_id", None) or "suggest-session"
    briefs = list(getattr(panel, "briefs", []))
    graph = build_graph(schema_text)
    entities = list(graph.entities.keys())

    run = SuggestRun(session_id=session_id)
    owner = resolve_bounded_owner(
        owning_role=SCREEN_OWNING_ROLE,
        aliases=SCREEN_ALIASES,
        symbol=SCREEN_SYMBOL,
        briefs=briefs,
    )
    if owner is None:
        run.skipped.append({"symbol": SCREEN_SYMBOL, "status": "no-owner"})
        return run
    if not entities:
        run.skipped.append({"symbol": SCREEN_SYMBOL, "status": "no-entities"})
        return run

    n = 1 if cap is None else max(0, cap)
    preflight = getattr(panel, "preflight_budget", None)
    if n and callable(preflight):
        try:
            preflight(n)
        except Exception as exc:  # noqa: BLE001 - preflight signals denial by raising
            logger.warning("suggest budget-denied (%d asks); deferring all: %s", n, exc)
            run.skipped.append({"symbol": SCREEN_SYMBOL, "status": "deferred-budget"})
            return run

    with span(
        "screens.suggest_pass",
        **{"screens.session_id": session_id, "screens.asks": n},
    ):
        prompt = _drafting_prompt(entities)
        for _ in range(n):
            answer = await panel.ask(owner, prompt, value_path=SCREEN_SYMBOL)
            if answer.grounding in (Grounding.UNAVAILABLE, Grounding.DEFERRED):
                status = (
                    "unavailable"
                    if answer.grounding is Grounding.UNAVAILABLE
                    else "deferred-persona"
                )
                run.skipped.append(
                    {"symbol": SCREEN_SYMBOL, "status": status, "role_id": owner}
                )
                continue
            cand = _build_candidate(graph, owner, answer, session_id)
            if cand is None:
                run.skipped.append({"symbol": SCREEN_SYMBOL, "status": "ungroundable"})
                continue
            # FR-MS-4: the schema-anchored guard is a necessary pre-filter (round-trip is authoritative).
            g = ground(cand, graph)
            if not g:
                cand.flags = list(g.reasons)
            run.candidates.append(cand)
            run.total_cost_usd += cand.cost_usd

    run.llm_used = bool(run.candidates)
    return run
