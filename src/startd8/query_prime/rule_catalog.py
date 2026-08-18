"""RULE_CATALOG — the query-security rule authority (the 2nd producer routed to the SARIF sink).

`SecurityFinding` (`query_prime/models.py`) already carries everything the SARIF sink needs — a
`check_type` enum (→ rule-id), `file_path`, `line`, `severity`, `message` — so it is a genuine drop-in
for `coverage_map.render_sarif_from_findings`. This module adds the *enumerable authority* the finding
itself doesn't provide: the set of rule-ids this producer can emit + their metadata, so the
FINDING↔REQ↔Derivation loop (the `verify Checks:` convention, `derive_checks`) can reason over
`query-security.*` rules the same way it reasons over `startd8-semantic.*`.

Seeded from `SecurityCheckType` (the enum IS the enumerable vocabulary — the strong catalog seed the
2026-08-16 producer audit named). `severity` here is the rule's DEFAULT (D1); a `SecurityFinding`
carries its own per-instance severity, which the renderer uses — the catalog default is for
enumerability + Derivation, not for overriding the finding.

Same D1/D2/D3 shape as `validators/rule_catalog.py` (`PRODUCER="startd8-semantic"`):
  * D1 — `RuleSpec` = severity (default) + domain + description; help_uri derived (`rule_help_uri`).
  * D2 — `qualified_id` = `query-security.<rule>` (one dot; no dots inside — enforced at import).
  * D3 — lives with the producer (`query_prime/`); the SARIF sink is a consumer.

NOTE (rule-of-three): this is the SDK's 2nd rule catalog (after `startd8-semantic`). A 3rd
(`startd8-obs`, rung 2) is the trigger to extract a shared `RuleSpec`/validate/helpers base — not yet
(YAGNI; see the RULE-CATALOG D3 decision). Until then this deliberately mirrors the pattern.
"""

from __future__ import annotations

from startd8.rule_catalog_base import RuleCatalog, RuleSpec  # RuleSpec re-exported for the annotation

from .models import SecurityCheckType

#: This catalog's producer — the namespace root of every qualified id (D2). No dots allowed.
PRODUCER = "query-security"

_HELP_BASE = "https://github.com/neil-the-nowledgeable/startd8-sdk/blob/main/docs/QUERY_SECURITY_RULES.md"


#: rule_id → metadata. Keys are the `SecurityCheckType` values (the bare `check_type.value` the sink
#: reads off a SecurityFinding today), so routing is byte-honest with the on-the-wire rule-id.
RULE_CATALOG: dict[str, RuleSpec] = {
    SecurityCheckType.INJECTION.value:
        {"severity": "error",   "domain": "injection",   "description": "SQL/command injection risk in a query"},
    SecurityCheckType.CREDENTIAL_LEAKAGE.value:
        {"severity": "error",   "domain": "credentials", "description": "Hard-coded or leaked credential"},
    SecurityCheckType.LIFECYCLE.value:
        {"severity": "warning", "domain": "lifecycle",   "description": "Resource lifecycle issue (unclosed connection/cursor)"},
    SecurityCheckType.HEALTH_CHECK_EXPOSURE.value:
        {"severity": "warning", "domain": "exposure",    "description": "Health/diagnostic endpoint exposes internals"},
}


#: The authority — validates at import (D2 + severity + every SecurityCheckType catalogued). Public
#: helpers below are its bound methods, re-exported so the module API is unchanged.
_CATALOG = RuleCatalog(
    PRODUCER, RULE_CATALOG, help_base=_HELP_BASE,
    require_all={t.value for t in SecurityCheckType},
)

rule_severity = _CATALOG.severity
rule_domain = _CATALOG.domain
rule_help_uri = _CATALOG.help_uri
qualified_id = _CATALOG.qualified_id
