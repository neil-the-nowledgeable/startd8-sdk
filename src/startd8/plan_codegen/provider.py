"""Deterministic-file provider for projected det-plans (REQ-29 FR-6).

Mirrors ``backend_codegen``'s ``PydanticSQLModelProvider``: registered under the
``startd8.contractors.deterministic_providers`` entry-point group, it lets the prime-contractor's
owned-file skip-hook recognize an in-sync projected det-plan (a ``$0`` file) **without the core
importing anything plan-specific**. The kit (``SCHEMA_det-plan-0.1``) owns the format; this provider
is the cited ``$0`` generator.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..contractors.deterministic_providers import ProviderContext
from ..logging_config import get_logger
from ..navigator import req_header as H
from .projector import NotPlanOwedError, project_plan
from .render import GENERATED_MARKER, render_plan

logger = get_logger(__name__)


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
            # (safe: the caller falls through rather than skipping a stale file). Logged at DEBUG so
            # "why wasn't my clean plan $0-skipped?" is diagnosable in Loki (the caller only logs on
            # a raised exception; a silent-False return would otherwise be invisible).
            logger.debug(
                "det-plan %s: paired req unresolved (%s) — not in-sync", path, req_path
            )
            return False
        try:
            req_text = req_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.debug(
                "det-plan %s: cannot read paired req %s: %s", path, req_path, exc
            )
            return False
        try:
            plan = project_plan(req_text, req_path=req_path)
        except (NotPlanOwedError, ValueError) as exc:
            logger.debug(
                "det-plan %s: paired req %s no longer projects (%s) — not in-sync",
                path,
                req_path,
                exc,
            )
            return False
        return render_plan(plan) == content

    @staticmethod
    def _resolve_req(content: str, context: ProviderContext) -> Optional[Path]:
        """Resolve the paired req from the plan's ``pairsWith`` line, then the context anchors.

        The plan names its source req in ``pairsWith``; resolve it under the project root (the req
        lives alongside the plan in the design corpus). Falls back to a ``.md`` source anchor.
        """
        root = Path(context.project_root)
        name = H.parse_pairs_with_line(content)
        if name:
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
