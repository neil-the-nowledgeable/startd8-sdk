"""Route query-security findings through the universal SARIF sink (rung 1 of the consume ladder).

`SecurityFinding` is a drop-in for `coverage_map.render_sarif_from_findings` — its `check_type` enum
supplies the rule-id (`.value`), `file_path`/`line` the location, `severity`/`message` the rest. This
module is the thin, named adapter: it forwards the findings to the generic sink and stamps each rule's
`helpUri` from the `query-security` catalog. It renders findings only — no new SARIF logic, no new
renderer (Mottainai). A finding without a file self-skips in the sink (honest, counted).
"""

from __future__ import annotations

from typing import Any, Iterable

from startd8.coverage_map import render_sarif_from_findings

from . import rule_catalog
from .models import SecurityFinding, SecurityVerificationResult


def render_security_sarif(
    findings: Iterable[SecurityFinding],
    *,
    tool_name: str = "query-security",
    corpus: str | None = None,
) -> dict[str, Any]:
    """Render query-security findings as a SARIF 2.1.0 document via the generic sink.

    The on-the-wire rule-id stays the bare `check_type.value` (e.g. ``injection``) — consistent with the
    semantic validators; the qualified ``query-security.injection`` (D2) is what the Derivation
    `verify Checks:` join computes, not what SARIF carries. ``helpUri`` per rule comes from the catalog.
    """
    help_uris = {rid: rule_catalog.rule_help_uri(rid) for rid in rule_catalog.RULE_CATALOG}
    return render_sarif_from_findings(
        findings, tool_name=tool_name, rule_help_uris=help_uris, corpus=corpus,
    )


def result_to_sarif(
    result: SecurityVerificationResult,
    *,
    tool_name: str = "query-security",
    corpus: str | None = None,
) -> dict[str, Any]:
    """Convenience: render a whole `verify_file` result's findings as SARIF."""
    return render_security_sarif(result.findings, tool_name=tool_name, corpus=corpus)
