"""Route TODO-scan entries through the SARIF sink (consume-ladder rung 1, producer #5 — a partial).

`TodoEntry` is not a drop-in: its `category` is a resolvability class (A/B/C), not a rule; it has no
`severity` and no `message`. So this adapter maps each entry to a **synthetic rule-id** (`todo_security`
if `security_sensitive` else `todo_unresolved`), sources the severity from the `todo` catalog (the
entry has none), and uses `raw_text` as the message. `file_path`+`line` give a region.
"""

from __future__ import annotations

from typing import Any, Iterable

from startd8.coverage_map import render_sarif_from_findings

from . import todo_rule_catalog as catalog


def _to_finding(entry: Any) -> dict:
    rule = "todo_security" if getattr(entry, "security_sensitive", False) else "todo_unresolved"
    line = getattr(entry, "line", None)
    return {
        "check": rule,
        "severity": catalog.rule_severity(rule),  # TodoEntry has no severity → catalog default
        "message": getattr(entry, "raw_text", "") or rule,
        "file_path": getattr(entry, "file_path", "") or "",
        "line": line if isinstance(line, int) and line > 0 else None,
    }


def render_todo_sarif(
    entries: Iterable[Any],
    *,
    tool_name: str = "todo",
    corpus: str | None = None,
) -> dict[str, Any]:
    """Render TODO-scan entries as SARIF 2.1.0 (synthetic rule-id; severity from the catalog)."""
    findings = [_to_finding(e) for e in entries]
    help_uris = {rid: catalog.rule_help_uri(rid) for rid in catalog.RULE_CATALOG}
    return render_sarif_from_findings(
        findings, tool_name=tool_name, rule_help_uris=help_uris, corpus=corpus,
    )
