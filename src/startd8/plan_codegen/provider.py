"""Deterministic-file provider for projected det-plans (REQ-29 FR-6).

Mirrors ``backend_codegen``'s ``PydanticSQLModelProvider``: registered under the
``startd8.contractors.deterministic_providers`` entry-point group, it lets the prime-contractor's
owned-file skip-hook recognize an in-sync projected det-plan (a ``$0`` file) **without the core
importing anything plan-specific**. The kit (``SCHEMA_det-plan-0.1``) owns the format; this provider
is the cited ``$0`` generator.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..contractors.deterministic_providers import ProviderContext
from .projector import NotPlanOwedError, project_plan
from .render import GENERATED_MARKER, render_plan

_PAIRS_WITH_LINE = re.compile(
    r"^-\s*\*\*pairsWith:\*\*\s*`?(?P<p>[^`\n]+?)`?\s*$", re.MULTILINE
)


class DetPlanProjectorProvider:
    """Recognizes our projected det-plan files and judges them in-sync against the paired req."""

    name = "det-plan-projector"

    def owns(self, path: Path, content: str) -> bool:
        # One of ours iff it carries the projected-plan marker. Cheap; no source read.
        return GENERATED_MARKER in content

    def is_in_sync(self, path: Path, content: str, context: ProviderContext) -> bool:
        req_path = self._resolve_req(content, context)
        if req_path is None or not req_path.is_file():
            # Owned plan present but the paired req can't be resolved → cannot verify → not in-sync
            # (safe: the caller falls through rather than skipping a stale file).
            return False
        try:
            req_text = req_path.read_text(encoding="utf-8")
        except OSError:
            return False
        try:
            plan = project_plan(req_text, req_path=req_path)
        except (NotPlanOwedError, ValueError):
            return False
        return render_plan(plan) == content

    @staticmethod
    def _resolve_req(content: str, context: ProviderContext) -> Optional[Path]:
        """Resolve the paired req from the plan's ``pairsWith`` line, then the context anchors.

        The plan names its source req in ``pairsWith``; resolve it under the project root (the req
        lives alongside the plan in the design corpus). Falls back to a ``.md`` source anchor.
        """
        root = Path(context.project_root)
        m = _PAIRS_WITH_LINE.search(content)
        if m:
            name = m.group("p").strip()
            # Try alongside the plan's own dir first (design docs are siblings), then the root.
            candidates = [root / name]
            for anchor in context.source_anchors:
                ap = Path(anchor)
                base = ap.parent if ap.is_absolute() else root / ap.parent
                candidates.append(base / name)
            for c in candidates:
                if c.is_file():
                    return c
        for anchor in context.source_anchors:
            if str(anchor).endswith(".md"):
                ap = Path(anchor) if Path(anchor).is_absolute() else root / anchor
                if ap.is_file():
                    return ap
        return None
