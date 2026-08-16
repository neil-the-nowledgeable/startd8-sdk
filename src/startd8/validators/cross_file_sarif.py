"""Route cross-file findings through the universal SARIF sink (consume-ladder rung 1, producer #3).

`cross_file_verifier.Finding` is already sink-shaped (`.check_id` → rule-id, `.source_file` → file,
`.severity`, `.message`); it has no line, so results are file-level. This is the thin, named adapter:
forward to the generic `render_sarif_from_findings` + stamp each rule's `helpUri` from the cross-file
catalog. No new renderer (Mottainai).
"""

from __future__ import annotations

from typing import Any, Iterable

from startd8.coverage_map import render_sarif_from_findings

from . import cross_file_rule_catalog as catalog
from .cross_file_verifier import Finding


def render_crossfile_sarif(
    findings: Iterable[Finding],
    *,
    tool_name: str = "cross-file",
    corpus: str | None = None,
) -> dict[str, Any]:
    """Render cross-file findings as SARIF 2.1.0 via the generic sink (file-level; no region)."""
    help_uris = {rid: catalog.rule_help_uri(rid) for rid in catalog.RULE_CATALOG}
    return render_sarif_from_findings(
        findings, tool_name=tool_name, rule_help_uris=help_uris, corpus=corpus,
    )
