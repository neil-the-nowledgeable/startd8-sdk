"""Shared Workbook data sources (convergence M1).

The classic Workbook loaded the stakeholder-panel answers, the panel→bridge→VIPP pipeline funnel, and
the roster directly in ``portal_build.py``. The convergence makes ``AgenticView`` the **single oracle**
every surface derives from, so those loaders live here — imported by BOTH the classic path (byte-
identical behavior) and ``agentic_view.build_agentic_view``. All are best-effort ``$0`` and never raise
(they return ``None`` on any absence), preserving the portal's degrade-not-fail contract (FR-6/FR-7).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import STAKEHOLDER_PANEL, startd8_dir
from .vipp_seam import dispositions_path, inbox_path


def load_panel_run(
    project_root: Path, session_id: Optional[str] = None
) -> Optional[List[dict]]:
    """Latest (or a specific) stakeholder-panel run's answers for the Workbook. None on any absence."""
    try:
        from ..stakeholder_panel.transcript import TranscriptStore

        if session_id:
            return [
                a.to_dict() for a in TranscriptStore(project_root, session_id).load()
            ] or None
        tdir = startd8_dir(project_root) / STAKEHOLDER_PANEL
        if not tdir.is_dir():
            return None
        sessions = sorted(
            (p for p in tdir.glob("*.json") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not sessions:
            return None
        return [
            a.to_dict() for a in TranscriptStore(project_root, sessions[0].stem).load()
        ] or None
    except (
        Exception
    ):  # pragma: no cover - never let transcript loading break the portal
        return None


def load_pipeline_state(project_root: Path) -> Optional[dict]:
    """Assemble the panel→bridge→VIPP funnel for the Workbook (best-effort, $0). None if no activity."""
    try:
        staged: List[dict] = []
        pdir = startd8_dir(project_root) / STAKEHOLDER_PANEL / "proposals"
        if pdir.is_dir():
            from ..stakeholder_panel.proposals import ProposalStore

            for f in sorted(pdir.glob("proposals-*.json")):
                sid = f.stem[len("proposals-") :]
                staged.extend(
                    r.to_dict() for r in ProposalStore(project_root, sid).load()
                )

        inbox: Dict[str, Any] = {"present": False}
        ip = inbox_path(project_root)
        if ip.is_file() and not ip.is_symlink():
            from ..vipp.models import ProposalEnvelope

            env = ProposalEnvelope.from_json(ip.read_text(encoding="utf-8"))
            inbox = {
                "present": True,
                "count": len(env.proposals),
                "envelope_seq": env.envelope_seq,
            }

        dispositions: Dict[str, Any] = {"present": False}
        disp_path = dispositions_path(project_root)
        if disp_path.is_file() and not disp_path.is_symlink():
            from ..vipp.models import VippReport

            rep = VippReport.from_json(disp_path.read_text(encoding="utf-8"))
            dispositions = {
                "present": True,
                "counts": rep.counts(),
                "evidence_available": rep.evidence_available,
                "items": [
                    {
                        "proposal_id": d.proposal_id,
                        "decision": getattr(d.decision, "value", str(d.decision)),
                        "reason": d.reason,
                    }
                    for d in rep.dispositions
                ],
                "advisories": list(rep.panel_advisories or []),
            }
        if not staged and not inbox["present"] and not dispositions["present"]:
            return None
        return {"staged": staged, "inbox": inbox, "dispositions": dispositions}
    except Exception:  # pragma: no cover - never let pipeline loading break the portal
        return None


def load_roster(project_root: Path) -> Any:
    """The stakeholder roster (personas) for the Workbook. None on any absence."""
    try:
        from ..stakeholder_panel import load_roster as _load_roster

        rp = project_root / "docs" / "kickoff" / "inputs" / "stakeholders.yaml"
        return _load_roster(rp) if rp.is_file() else None
    except Exception:  # pragma: no cover
        return None
