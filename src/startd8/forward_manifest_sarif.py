"""Route contract-compliance violations through the SARIF sink (rung 1, producer #6 — a partial).

`ContractViolation` is skipped by the generic renderer (its `violation_type` is not in the rule-id
chain — audit C2), and `violation_type` is partly dynamic. So this adapter maps `violation_type` → a
STABLE rule-id (fixed literals as-is; dynamic `missing_*` → `missing_element`; `unverified_*` →
`unverified`), builds a message from `expected`/`actual`, and renders via the generic sink. No line →
file-level. A violation with no `file_path` self-skips in the sink.
"""

from __future__ import annotations

from typing import Any, Iterable

from startd8.coverage_map import render_sarif_from_findings

from . import forward_manifest_rule_catalog as catalog

_FIXED = frozenset({
    "missing_base_class", "missing_class", "missing_dependency", "missing_file",
    "missing_function", "missing_import", "signature_mismatch",
})


def _rule_id(violation_type: str) -> str:
    """`violation_type` → a stable catalogued rule-id (collapse the dynamic suffixes)."""
    if violation_type in _FIXED:
        return violation_type
    if violation_type.startswith("unverified"):
        return "unverified"
    if violation_type.startswith("missing"):
        return "missing_element"
    return violation_type  # fallback: pass through (renderer still emits a valid ruleId)


def _to_finding(v: Any) -> dict:
    expected = getattr(v, "expected", "") or ""
    actual = getattr(v, "actual", None)
    message = f"expected {expected}" + (f", got {actual}" if actual else "")
    return {
        "check": _rule_id(getattr(v, "violation_type", "") or ""),
        "severity": getattr(v, "severity", "error"),
        "message": message,
        "file_path": getattr(v, "file_path", None),
    }


def render_contract_sarif(
    violations: Iterable[Any],
    *,
    tool_name: str = "contract",
    corpus: str | None = None,
) -> dict[str, Any]:
    """Render contract violations as SARIF 2.1.0 (violation_type → stable rule-id; file-level)."""
    findings = [_to_finding(v) for v in violations]
    help_uris = {rid: catalog.rule_help_uri(rid) for rid in catalog.RULE_CATALOG}
    return render_sarif_from_findings(
        findings, tool_name=tool_name, rule_help_uris=help_uris, corpus=corpus,
    )
