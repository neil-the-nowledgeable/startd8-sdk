"""RULE_CATALOG — the contract-compliance rule authority (`contract`; producer #7, a partial).

`forward_manifest_validator.ContractViolation` is NOT a drop-in: the SARIF renderer's rule-id chain
(`check`/`check_type`/`rule_id`/`check_id`/`category`) does not read its `violation_type`, so it is
skipped outright (audit C2). And `violation_type` is partly dynamic (`missing_{kind}`,
`unverified_{category}`). So the adapter (`forward_manifest_sarif.py`) maps `violation_type` → a STABLE
rule-id: the fixed set as-is, a dynamic `missing_*` → `missing_element`, a dynamic `unverified_*` →
`unverified`. `ContractViolation` has no line → file-level results.

Data only, on the shared `rule_catalog_base`.
"""

from __future__ import annotations

from startd8.rule_catalog_base import RuleCatalog, RuleSpec

#: This catalog's producer — the namespace root of every qualified id (D2). No dots allowed.
PRODUCER = "contract"

_HELP_BASE = "https://github.com/neil-the-nowledgeable/startd8-sdk/blob/main/docs/CONTRACT_RULES.md"

#: The stable rule set the adapter normalizes `violation_type` onto (fixed literals + two collapsed
#: families for the dynamic `missing_{kind}` / `unverified_{category}`). `severity` is a DEFAULT — a
#: ContractViolation carries its own severity, which the renderer uses.
RULE_CATALOG: dict[str, RuleSpec] = {
    "missing_base_class": {"severity": "error",   "domain": "structure",    "description": "Expected base class is absent"},
    "missing_class":      {"severity": "error",   "domain": "structure",    "description": "Expected class is absent"},
    "missing_dependency": {"severity": "error",   "domain": "structure",    "description": "Expected dependency is absent"},
    "missing_file":       {"severity": "error",   "domain": "structure",    "description": "Expected file is absent"},
    "missing_function":   {"severity": "error",   "domain": "structure",    "description": "Expected function is absent"},
    "missing_import":     {"severity": "error",   "domain": "structure",    "description": "Expected import is absent"},
    "signature_mismatch": {"severity": "error",   "domain": "structure",    "description": "Signature does not match the contract"},
    "missing_element":    {"severity": "error",   "domain": "structure",    "description": "Expected element is absent (dynamic kind)"},
    "unverified":         {"severity": "warning", "domain": "verification", "description": "Contract element could not be verified"},
}

#: The authority — validates at import (D2 no-dot + severity); helpers are its bound methods.
_CATALOG = RuleCatalog(PRODUCER, RULE_CATALOG, help_base=_HELP_BASE)

rule_severity = _CATALOG.severity
rule_domain = _CATALOG.domain
rule_help_uri = _CATALOG.help_uri
qualified_id = _CATALOG.qualified_id
