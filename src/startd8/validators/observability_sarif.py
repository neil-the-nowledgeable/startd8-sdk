"""Route observability-artifact validation findings through the SARIF sink (rung 2 — the o11y bridge).

This is the first place a ContextCore-facing domain (observability) consumes the sink. Unlike the
drop-in producers, an observability *issue* dict (`{check, severity, message}`) has **no file** — the
`file_path` lives on the parent `*ValidationResult` (Dashboard/Alert/Slo). So the adapter walks
parent→issues and **stamps the parent's file** onto each issue before forwarding to the generic
`render_sarif_from_findings`. Issues have no line → file-level results; an issue whose parent has an
empty `file_path` self-skips in the sink (honest, counted).
"""

from __future__ import annotations

from typing import Any, Iterable

from startd8.coverage_map import render_sarif_from_findings

from . import observability_rule_catalog as catalog


def _stamp(results: Iterable[Any]) -> list[dict]:
    """Flatten `[result_with_(.file_path, .issues)]` → `[{**issue, file: result.file_path}]`."""
    out: list[dict] = []
    for r in results:
        file_path = getattr(r, "file_path", "") or ""
        for issue in getattr(r, "issues", None) or []:
            if isinstance(issue, dict):
                out.append({**issue, "file": file_path})
    return out


def render_observability_sarif(
    results: Iterable[Any],
    *,
    tool_name: str = "startd8-obs",
    corpus: str | None = None,
) -> dict[str, Any]:
    """Render observability `*ValidationResult`s as SARIF 2.1.0 — parent file stamped onto each issue."""
    findings = _stamp(results)
    help_uris = {rid: catalog.rule_help_uri(rid) for rid in catalog.RULE_CATALOG}
    return render_sarif_from_findings(
        findings, tool_name=tool_name, rule_help_uris=help_uris, corpus=corpus,
    )
