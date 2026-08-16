"""RULE_CATALOG — the repair-diagnostics rule authority (4th producer; the 1st DATA-ONLY catalog).

`repair.models.Diagnostic` (+ subclasses) is a drop-in for `coverage_map.render_sarif_from_findings`:
the renderer reads `.category` (rule-id) and `.file` (file); `.line` is present on the subclasses that
carry it (Syntax/Lint/Semantic/Convention) → a region, else file-level; `.severity` exists only on
Semantic/Convention (else the renderer degrades to `warning` — honest for a diagnostic).

This is the first catalog written against the shared `rule_catalog_base` — proof of the rule-of-three
payoff: it is **only data** + one `RuleCatalog` instance. Keys are the `category` values the repair
pipeline emits.
"""

from __future__ import annotations

from startd8.rule_catalog_base import RuleCatalog, RuleSpec

#: This catalog's producer — the namespace root of every qualified id (D2). No dots allowed.
PRODUCER = "repair"

_HELP_BASE = "https://github.com/neil-the-nowledgeable/startd8-sdk/blob/main/docs/REPAIR_RULES.md"

#: category → metadata. The categories the repair pipeline sets on a Diagnostic (base doc
#: `syntax|import|lint|test|size` + the subclasses' `__post_init__` categories). `severity` is the
#: rule's DEFAULT (most repair Diagnostics carry no severity → the renderer degrades to `warning`).
RULE_CATALOG: dict[str, RuleSpec] = {
    "syntax":            {"severity": "error",   "domain": "compile",    "description": "Syntax error from a checkpoint"},
    "import":            {"severity": "error",   "domain": "compile",    "description": "Unresolved / missing import"},
    "lint":              {"severity": "warning", "domain": "compile",    "description": "Lint rule violation"},
    "test":              {"severity": "error",   "domain": "test",       "description": "Failing test"},
    "size":              {"severity": "warning", "domain": "size",       "description": "Size regression vs the source"},
    "semantic":          {"severity": "warning", "domain": "contract",   "description": "Semantic issue (method/import resolution, etc.)"},
    "contract_violation":{"severity": "error",   "domain": "contract",   "description": "Forward-manifest contract violation"},
    "content_contract":  {"severity": "error",   "domain": "contract",   "description": "Content-contract violation (misnamed field / wrong import path)"},
    "convention":        {"severity": "error",   "domain": "convention", "description": "House-convention violation"},
    "security":          {"severity": "error",   "domain": "security",   "description": "Security issue surfaced during repair"},
}

#: The authority — validates at import (D2 no-dot + severity); helpers are its bound methods.
_CATALOG = RuleCatalog(PRODUCER, RULE_CATALOG, help_base=_HELP_BASE)

rule_severity = _CATALOG.severity
rule_domain = _CATALOG.domain
rule_help_uri = _CATALOG.help_uri
qualified_id = _CATALOG.qualified_id
