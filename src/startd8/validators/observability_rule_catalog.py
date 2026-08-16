"""RULE_CATALOG — the observability-artifact rule authority (`startd8-obs`; producer #5).

The `OBS-*` ids the observability-artifact validators emit (`observability_artifact_validators.py`,
`_issue(check_id, …)`) — the strong, already-namespaced seed the 2026-08-16 producer audit named. Data
only, on the shared `rule_catalog_base`.

Grouped by family (the 3 validated artifact kinds + cross-artifact): `OBS-100x` dashboard, `OBS-101x`
alert rules, `OBS-102x` SLO, `OBS-203x` alert PromQL, `OBS-40x` cross-artifact. `severity` is the rule's
DEFAULT (transcribed from the `_issue` call sites); the runtime issue carries its own severity, which
the renderer uses — so the default is for enumerability, not for overriding the finding. Per-check
`description` stays family-level on purpose: the specific meaning is the issue's runtime `message`.

This is the rung-2 producer — the o11y-validation → SARIF bridge (roadmap Milestone A): its findings
live on a parent `*ValidationResult.file_path`, so the adapter (`observability_sarif.py`) stamps the
parent's file onto each issue before rendering.
"""

from __future__ import annotations

from startd8.rule_catalog_base import RuleCatalog, RuleSpec

#: This catalog's producer — the namespace root of every qualified id (D2). No dots allowed.
PRODUCER = "startd8-obs"

_HELP_BASE = "https://github.com/neil-the-nowledgeable/startd8-sdk/blob/main/docs/OBSERVABILITY_RULES.md"

#: OBS check_id → metadata (transcribed from the validators' `_issue` call sites; family-grouped).
RULE_CATALOG: dict[str, RuleSpec] = {
    "OBS-100a": {"severity": "error", "domain": "dashboard", "description": "Dashboard spec check"},
    "OBS-100b": {"severity": "error", "domain": "dashboard", "description": "Dashboard spec check"},
    "OBS-100c": {"severity": "error", "domain": "dashboard", "description": "Dashboard spec check"},
    "OBS-100d": {"severity": "error", "domain": "dashboard", "description": "Dashboard spec check"},
    "OBS-100e": {"severity": "error", "domain": "dashboard", "description": "Dashboard spec check"},
    "OBS-100f": {"severity": "warning", "domain": "dashboard", "description": "Dashboard spec check"},
    "OBS-100g": {"severity": "warning", "domain": "dashboard", "description": "Dashboard spec check"},
    "OBS-100h": {"severity": "warning", "domain": "dashboard", "description": "Dashboard spec check"},
    "OBS-100i": {"severity": "warning", "domain": "dashboard", "description": "Dashboard spec check"},
    "OBS-100j": {"severity": "info", "domain": "dashboard", "description": "Dashboard spec check"},
    "OBS-101a": {"severity": "error", "domain": "alert", "description": "Alert rules check"},
    "OBS-101b": {"severity": "error", "domain": "alert", "description": "Alert rules check"},
    "OBS-101c": {"severity": "error", "domain": "alert", "description": "Alert rules check"},
    "OBS-101d": {"severity": "error", "domain": "alert", "description": "Alert rules check"},
    "OBS-101e": {"severity": "warning", "domain": "alert", "description": "Alert rules check"},
    "OBS-101f": {"severity": "error", "domain": "alert", "description": "Alert rules check"},
    "OBS-101g": {"severity": "warning", "domain": "alert", "description": "Alert rules check"},
    "OBS-101h": {"severity": "warning", "domain": "alert", "description": "Alert rules check"},
    "OBS-101j": {"severity": "error", "domain": "alert", "description": "Alert rules check"},
    "OBS-102a": {"severity": "error", "domain": "slo", "description": "SLO spec check"},
    "OBS-102b": {"severity": "error", "domain": "slo", "description": "SLO spec check"},
    "OBS-102c": {"severity": "error", "domain": "slo", "description": "SLO spec check"},
    "OBS-102d": {"severity": "error", "domain": "slo", "description": "SLO spec check"},
    "OBS-102e": {"severity": "error", "domain": "slo", "description": "SLO spec check"},
    "OBS-102f": {"severity": "error", "domain": "slo", "description": "SLO spec check"},
    "OBS-102g": {"severity": "warning", "domain": "slo", "description": "SLO spec check"},
    "OBS-102h": {"severity": "warning", "domain": "slo", "description": "SLO spec check"},
    "OBS-102i": {"severity": "info", "domain": "slo", "description": "SLO spec check"},
    "OBS-102j": {"severity": "error", "domain": "slo", "description": "SLO spec check"},
    "OBS-203a": {"severity": "warning", "domain": "alert", "description": "Alert PromQL check"},
    "OBS-203b": {"severity": "error", "domain": "alert", "description": "Alert PromQL check"},
    "OBS-203c": {"severity": "warning", "domain": "alert", "description": "Alert PromQL check"},
    "OBS-400": {"severity": "warning", "domain": "cross", "description": "Cross-artifact check"},
    "OBS-401": {"severity": "warning", "domain": "cross", "description": "Cross-artifact check"},
    "OBS-402": {"severity": "warning", "domain": "cross", "description": "Cross-artifact check"},
    "OBS-403": {"severity": "info", "domain": "cross", "description": "Cross-artifact check"},
}

#: The authority — validates at import (D2 no-dot + severity); helpers are its bound methods.
_CATALOG = RuleCatalog(PRODUCER, RULE_CATALOG, help_base=_HELP_BASE)

rule_severity = _CATALOG.severity
rule_domain = _CATALOG.domain
rule_help_uri = _CATALOG.help_uri
qualified_id = _CATALOG.qualified_id
