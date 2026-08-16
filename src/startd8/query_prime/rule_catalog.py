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

from typing import TypedDict

from .models import SecurityCheckType

#: This catalog's producer — the namespace root of every qualified id (D2). No dots allowed.
PRODUCER = "query-security"

_HELP_BASE = "https://github.com/neil-the-nowledgeable/startd8-sdk/blob/main/docs/QUERY_SECURITY_RULES.md"

_VALID_SEVERITIES = frozenset({"error", "warning", "info"})


class RuleSpec(TypedDict):
    """Fixed metadata for one rule (D1). `severity` is the DEFAULT a finding may override."""

    severity: str   # "error" | "warning" | "info" — the rule's default level
    domain: str     # grouping axis (the check family)
    description: str  # one line → SARIF rule.shortDescription


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


def _validate_catalog() -> None:
    """Enforce at import: no dots in PRODUCER or any rule-id (D2, so `qualified_id` has exactly one
    dot), and every severity is in the closed set. Also: every SecurityCheckType is catalogued."""
    if "." in PRODUCER:
        raise ValueError(f"PRODUCER {PRODUCER!r} must not contain '.' (D2)")
    for rule_id, spec in RULE_CATALOG.items():
        if "." in rule_id:
            raise ValueError(f"rule id {rule_id!r} must not contain '.' (D2)")
        if spec["severity"] not in _VALID_SEVERITIES:
            raise ValueError(f"rule {rule_id!r} severity {spec['severity']!r} not in {sorted(_VALID_SEVERITIES)}")
    missing = {t.value for t in SecurityCheckType} - set(RULE_CATALOG)
    if missing:
        raise ValueError(f"SecurityCheckType(s) not catalogued: {sorted(missing)}")


_validate_catalog()


def rule_severity(rule_id: str) -> str:
    """Default severity for *rule_id*; KeyError (loud) on an unknown rule."""
    return RULE_CATALOG[rule_id]["severity"]


def rule_domain(rule_id: str) -> str:
    return RULE_CATALOG[rule_id]["domain"]


def rule_help_uri(rule_id: str) -> str:
    """Derived (pure function of the id — not stored per-rule)."""
    return f"{_HELP_BASE}#{rule_id}"


def qualified_id(rule_id: str) -> str:
    """The cross-producer id `query-security.<rule>` (D2)."""
    return f"{PRODUCER}.{rule_id}"
