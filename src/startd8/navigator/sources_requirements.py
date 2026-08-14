"""Minimal det-req/0.1 → Nodes (FR-6). Full V-1..V-5 plan-DAG parity is out of scope.

Uses vendored thin Lives/`fr_health` (``det_req.py``); does not require det-req-kit
on ``sys.path``.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from startd8.wireframe.profile import RenderProfile, StatusStyle

from .det_req import fr_health, parse_fr_lines_prefer_kit
from .git_lives import prefer_git_ref
from .models import Node, NodeEvidence, NodeStatus, default_confidence, derive_status

REQUIREMENTS_PROFILE = RenderProfile(
    statuses=(
        StatusStyle("grounded", "Grounded", "#3d7a57", "reuses existing code", 0),
        StatusStyle("spec", "Spec", "#6b6252", "written, not built", 2),
        StatusStyle("awaiting", "Awaiting", "#a9781a", "needs a decision", 3, True),
        StatusStyle("excluded", "Excluded", "#948b78", "out of scope", 2),
        StatusStyle("unknown", "Unknown", "#ab473a", "done-claim without Lives", 4, True),
    ),
    title="This spec — a first look",
    eyebrow="This spec",
    section_lead="What this spec defines",
    headline="A first look at this spec",
    gap_noun="requirement",
)


def nodes_from_requirements(path: Path, *, repo: Path | None = None) -> List[Node]:
    """Project a det-req markdown file into FR Nodes."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    frs = parse_fr_lines_prefer_kit(text)
    repo_root = Path(repo) if repo else _guess_repo(path)
    nodes: List[Node] = []
    for fr in frs:
        lives = tuple(
            NodeEvidence(
                type=str(e.get("type", "")),
                ref=prefer_git_ref(str(e.get("ref", "")), repo=repo_root),
                note=str(e.get("note", "")),
            )
            for e in (fr.get("lives") or [])
        )
        # Recompute health after prefer_git upgrades soft→strong (EVIDENCE-1).
        health = fr_health(
            {
                **fr,
                "lives": [{"type": e.type, "ref": e.ref} for e in lives],
            }
        )
        has_code = any(ev.type == "code" for ev in lives)
        # Done-claim without strong lives stays SPEC / awaiting — never grounded green.
        if health == "unknown":
            status = NodeStatus.SPEC
            status_key = "unknown"
            route = ""
        elif health == "skipped":
            status = NodeStatus.SPEC
            status_key = "excluded"
            route = "declared_unimplemented"
        elif has_code:
            status = derive_status(has_code_evidence=True, maturity="stable")
            status_key = "grounded"
            route = "sdk_emitted"
        else:
            status = NodeStatus.SPEC
            status_key = "spec"
            route = "declared_unimplemented" if not lives else ""

        ships_when = ""
        if not lives:
            ships_when = "evidence authored (Lives:)"

        conf = default_confidence(lives)
        does = (fr.get("behavior") or fr.get("title") or "").strip()
        prompts = tuple(fr.get("approve_prompts") or ())
        was = tuple(fr.get("was") or ())
        attrs: dict = {
            "kind": "fr",
            "title": str(fr.get("title", "")),
            "verify": str(fr.get("verify", "")),
            "serves": ", ".join(fr.get("serves") or []),
            "touches": ", ".join(fr.get("touches") or []),
            "fr_health": health,
            "status_key": status_key,
            "section_order": "30",
            "provenance": "authored",
        }
        if prompts:
            attrs["approve_prompts"] = " · ".join(prompts)
        if was:
            attrs["was"] = " · ".join(was)
        nodes.append(
            Node(
                key=str(fr["id"]),
                does=does,
                status=status,
                lives=lives,
                ships_when=ships_when if not lives else "",
                confidence=conf,
                category="functional-requirements",
                orientation="bridge",
                route_state=route,
                attributes=attrs,
            )
        )
    return nodes


def _guess_repo(path: Path) -> Path:
    cur = path.resolve().parent
    for _ in range(8):
        if (cur / ".git").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return Path.cwd()
