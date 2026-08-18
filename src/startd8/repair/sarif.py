"""Route repair diagnostics through the universal SARIF sink (consume-ladder rung 1, producer #4).

`repair.models.Diagnostic` (+ subclasses) is already sink-shaped: the renderer reads `.category`
(rule-id) and `.file` (file); `.line` (Syntax/Lint/Semantic/Convention) → a region, else file-level;
`.severity` (Semantic/Convention) → level, else degrades to `warning`. Thin, named adapter: forward to
the generic `render_sarif_from_findings` + stamp catalog helpUris. No new renderer.
"""

from __future__ import annotations

from typing import Any, Iterable

from startd8.coverage_map import render_sarif_from_findings

from . import rule_catalog as catalog
from .models import Diagnostic


def render_repair_sarif(
    diagnostics: Iterable[Diagnostic],
    *,
    tool_name: str = "repair",
    corpus: str | None = None,
) -> dict[str, Any]:
    """Render repair diagnostics as SARIF 2.1.0 via the generic sink (region when the diagnostic
    carries a line; severity degrades to `warning` for the base/Syntax/Import/Lint shapes)."""
    help_uris = {rid: catalog.rule_help_uri(rid) for rid in catalog.RULE_CATALOG}
    return render_sarif_from_findings(
        diagnostics, tool_name=tool_name, rule_help_uris=help_uris, corpus=corpus,
    )
