"""FR-E16 — the multi-project portfolio readiness board.

`kickoff portal --index` builds a Grafana *dashlist* (a self-updating link-list of every project's
Workbook) — useful, but it shows no readiness. This module adds the missing half: a **$0, offline,
deterministic** scan of a workspace of projects that computes each one's readiness from the SAME
`AgenticView` read-model the cockpit/readout use (one oracle, no drift), and renders a ranked board —
**who's build-ready, who's stuck**. Read-only; a broken project degrades to an honest row, never a
failed scan.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

#: Board statuses, ordered best→worst for ranking.
_STATUS_ORDER = {"build-ready": 0, "in-progress": 1, "stuck": 2, "not-started": 3, "unknown": 4}
_STATUS_GLYPH = {
    "build-ready": "✅ build-ready",
    "in-progress": "🚧 in progress",
    "stuck": "⛔ stuck",
    "not-started": "· not started",
    "unknown": "⚠️ unreadable",
}


@dataclass(frozen=True)
class PortfolioEntry:
    name: str
    readiness: Optional[int]   # ok/total percent, or None when there are no kickoff inputs yet
    blocked: int
    status: str                # one of _STATUS_ORDER
    next_step: str             # the single recommended next action (or "")

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "readiness_percent": self.readiness, "blocked": self.blocked,
                "status": self.status, "next_step": self.next_step}


def _classify(readiness: Optional[int], blocked: int) -> str:
    if readiness is None:
        return "not-started"
    if blocked > 0:
        return "stuck"                 # has explicitly blocked inputs → needs attention
    if readiness >= 100:
        return "build-ready"           # every input resolved
    return "in-progress"


def entry_from_view(name: str, view: Any) -> PortfolioEntry:
    """Derive a portfolio row from an :class:`AgenticView` (pure — the same oracle the cockpit uses)."""
    readiness = view.readiness_percent()
    state = getattr(view, "state", None)
    blocked = int(state.attention_counts.get("blocked", 0)) if state is not None else 0
    na = getattr(view, "next_action", None)
    next_step = getattr(na, "title", "") if na is not None else ""
    return PortfolioEntry(name=name, readiness=readiness, blocked=blocked,
                          status=_classify(readiness, blocked), next_step=next_step or "")


def discover_projects(workspace: Path) -> List[Path]:
    """Project roots under *workspace* — every immediate child that holds a ``docs/kickoff`` package
    (plus *workspace* itself if it is one). Deterministic (name-sorted)."""
    workspace = Path(workspace).expanduser()
    roots = {m.parent.parent for m in workspace.glob("*/docs/kickoff") if m.is_dir()}
    if (workspace / "docs" / "kickoff").is_dir():
        roots.add(workspace)
    return sorted(roots, key=lambda p: p.name)


def scan_portfolio(workspace: Path) -> List[PortfolioEntry]:
    """Discover + read every project under *workspace*. Each project is best-effort — a project whose
    view cannot be built becomes an ``unknown`` row, never a crash."""
    from .agentic_view import build_agentic_view

    entries: List[PortfolioEntry] = []
    for root in discover_projects(workspace):
        try:
            entries.append(entry_from_view(root.name, build_agentic_view(root)))
        except Exception:  # a broken project must not sink the whole board
            entries.append(PortfolioEntry(root.name, None, 0, "unknown", ""))
    return _ranked(entries)


def _ranked(entries: List[PortfolioEntry]) -> List[PortfolioEntry]:
    # Build-ready first, then in-progress (by readiness desc), stuck, not-started, unknown last.
    return sorted(entries, key=lambda e: (_STATUS_ORDER.get(e.status, 9), -(e.readiness or 0), e.name))


def portfolio_summary(entries: List[PortfolioEntry]) -> Dict[str, int]:
    out = {k: 0 for k in _STATUS_ORDER}
    for e in entries:
        out[e.status] = out.get(e.status, 0) + 1
    out["total"] = len(entries)
    return out


def portfolio_to_dict(workspace: Path, entries: List[PortfolioEntry]) -> Dict[str, Any]:
    return {"schema": "kickoff.portfolio.v1", "workspace": str(workspace),
            "summary": portfolio_summary(entries), "projects": [e.to_dict() for e in entries]}


def _cell(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def render_portfolio_markdown(workspace: Path, entries: List[PortfolioEntry]) -> str:
    """A shareable, ranked readiness board — who's build-ready, who's stuck. Pure, ``$0``."""
    s = portfolio_summary(entries)
    lines = [f"# Portfolio readiness — {_cell(Path(workspace).name)}\n"]
    if not entries:
        lines.append("_No projects found — a project is a directory with a `docs/kickoff` package._\n")
        return "\n".join(lines) + "\n"
    lines.append(
        f"**{s['total']} projects:** {s['build-ready']} build-ready · {s['in-progress']} in progress · "
        f"{s['stuck']} stuck · {s['not-started']} not started"
        + (f" · {s['unknown']} unreadable" if s.get("unknown") else "") + "\n"
    )
    lines.append("| Project | Readiness | Blocked | Status | Next step |")
    lines.append("|---|---|---|---|---|")
    for e in entries:
        pct = f"{e.readiness}%" if e.readiness is not None else "—"
        lines.append(f"| `{_cell(e.name)}` | {pct} | {e.blocked or '—'} | "
                     f"{_STATUS_GLYPH.get(e.status, e.status)} | {_cell(e.next_step) or '—'} |")
    return "\n".join(lines) + "\n"
