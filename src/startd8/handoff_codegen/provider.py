"""Deterministic-file provider for projected det-handoffs (SCHEMA §6).

Mirrors ``plan_codegen``'s ``DetPlanProjectorProvider``: registered under the
``startd8.contractors.deterministic_providers`` entry-point group so the prime-contractor's skip-hook
recognizes an in-sync projected handoff (a ``$0`` file) without the core importing anything
handoff-specific. The kit (``SCHEMA_det-handoff-0.1``) owns the format; this is the cited generator.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..contractors.deterministic_providers import ProviderContext
from ..logging_config import get_logger
from .projector import NotHandoffOwedError, project_handoff
from .render import GENERATED_MARKER, render_handoff

logger = get_logger(__name__)

_PAIRS_WITH_LINE = re.compile(
    r"^-\s*\*\*pairsWith:\*\*\s*`?(?P<p>[^`\n]+?)`?\s*$", re.MULTILINE
)
# Extract the sha from ``- **base:** main @ <sha>`` so re-projection reproduces the same base line.
_BASE_LINE = re.compile(
    r"^-\s*\*\*base:\*\*\s*main @ (?P<sha>[^\s(]+)\s*$", re.MULTILINE
)


class DetHandoffProjectorProvider:
    """Recognizes our projected det-handoff files and judges them in-sync against the paired REQ."""

    name = "det-handoff-projector"

    def owns(self, path: Path, content: str) -> bool:
        return GENERATED_MARKER in content

    def is_in_sync(self, path: Path, content: str, context: ProviderContext) -> bool:
        req_path = self._resolve_req(content, context)
        if req_path is None or not req_path.is_file():
            logger.debug(
                "det-handoff %s: paired REQ unresolved (%s) — not in-sync",
                path,
                req_path,
            )
            return False
        try:
            req_text = req_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.debug(
                "det-handoff %s: cannot read paired REQ %s: %s", path, req_path, exc
            )
            return False
        # The spine is a pure function of the REQ; only `base` depends on the sha, which the rendered
        # doc carries — extract it so re-projection reproduces the same base line (no ledger needed).
        m = _BASE_LINE.search(content)
        base_sha = m.group("sha") if m else None
        try:
            handoff = project_handoff(req_text, req_path=req_path, base_sha=base_sha)
        except (NotHandoffOwedError, ValueError) as exc:
            logger.debug(
                "det-handoff %s: paired REQ %s no longer projects (%s)",
                path,
                req_path,
                exc,
            )
            return False
        return render_handoff(handoff) == content

    @staticmethod
    def _resolve_req(content: str, context: ProviderContext) -> Optional[Path]:
        """Resolve the paired REQ from the handoff's ``pairsWith`` line, then a ``.md`` anchor."""
        root = Path(context.project_root)
        m = _PAIRS_WITH_LINE.search(content)
        if m:
            name = m.group("p").strip()
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
