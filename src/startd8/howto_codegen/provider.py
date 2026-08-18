"""``DetHowtoProjectorProvider`` — the deterministic-file provider (STANDARD Part 4).

A ``DeterministicFileProvider`` (``contractors/deterministic_providers``): ``owns()`` = the
``GENERATED_MARKER`` is present; ``is_in_sync()`` = resolve the source REQ from the doc's
``pairsWith`` line, re-project + re-render, and compare bytes. Silent-degradation paths **log at
DEBUG** via ``get_logger(__name__)`` so a non-skip is diagnosable (STANDARD Part 4 / L-2).
"""

from __future__ import annotations

import re
from pathlib import Path

from ..contractors.deterministic_providers import ProviderContext
from ..logging_config import get_logger
from .projector import NotHowtoOwedError, project_howto
from .render import GENERATED_MARKER, render_howto

logger = get_logger(__name__)

#: The `pairsWith` back-reference line in a rendered doc (STANDARD 6d) — the resolvable pointer the
#: provider re-projects from. Matches ``**pairsWith:** `<path>` (LIVE)``.
_PAIRS_WITH_LINE = re.compile(r"^\*\*pairsWith:\*\*\s*`(?P<p>[^`]+)`", re.MULTILINE)


class DetHowtoProjectorProvider:
    """Judges whether an on-disk HOWTO is a ``$0`` det-howto projection still in-sync with its REQ."""

    name = "det-howto-projector"

    def owns(self, path: Path, content: str) -> bool:
        """True iff *content* carries the det-howto GENERATED marker (cheap; no source read)."""
        return GENERATED_MARKER in content

    def _source_path(self, content: str, context: ProviderContext) -> Path | None:
        """Resolve the source REQ path from the doc's ``pairsWith`` back-reference (STANDARD 6d)."""
        m = _PAIRS_WITH_LINE.search(content)
        if not m:
            logger.debug("det-howto: no pairsWith line — cannot re-project to compare")
            return None
        raw = m.group("p").strip()
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = (context.project_root / raw).resolve()
        return candidate

    def is_in_sync(self, path: Path, content: str, context: ProviderContext) -> bool:
        """True iff re-projecting from the paired REQ reproduces *content* byte-for-byte.

        Marker presence alone must NOT return True (deterministic-provider contract) — we re-project
        from the real source and compare. Every silent-``False`` path logs at DEBUG (STANDARD L-2).
        """
        if not self.owns(path, content):
            return False
        src = self._source_path(content, context)
        if src is None:
            return False
        if not src.exists():
            logger.debug(
                "det-howto: source REQ %s absent — not in-sync (phantom pairsWith)", src
            )
            return False
        try:
            req_text = src.read_text(encoding="utf-8")
        except OSError as exc:
            logger.debug("det-howto: cannot read source REQ %s: %s", src, exc)
            return False
        try:
            howto = project_howto(req_text, req_path=src)
        except NotHowtoOwedError:
            # The REQ no longer declares a command surface — the on-disk howto is now stale/orphaned.
            logger.debug(
                "det-howto: source REQ %s no longer owes a HOWTO — stale on disk", src
            )
            return False
        except Exception as exc:  # pragma: no cover - projector is pure; defensive only
            logger.debug("det-howto: re-projection of %s failed: %s", src, exc)
            return False
        return render_howto(howto) == content
