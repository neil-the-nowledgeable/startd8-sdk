"""RULE_CATALOG — the TODO-scan rule authority (`todo`; producer #6, a partial).

`todo_scanner.TodoEntry` is NOT a drop-in: its `category` is a resolvability class (`A`/`B`/`C`),
not a rule name (routing it would emit opaque `A`/`B`/`C` ruleIds), and it has no `severity` and no
`message` field (it carries `raw_text`). So the adapter (`todo_sarif.py`) maps each entry to a
**synthetic** rule-id — `todo_security` when the entry is `security_sensitive`, else `todo_unresolved`
— sources the severity from THIS catalog (the entry has none), and uses `raw_text` as the message.

Data only, on the shared `rule_catalog_base`.
"""

from __future__ import annotations

from startd8.rule_catalog_base import RuleCatalog, RuleSpec

#: This catalog's producer — the namespace root of every qualified id (D2). No dots allowed.
PRODUCER = "todo"

_HELP_BASE = "https://github.com/neil-the-nowledgeable/startd8-sdk/blob/main/docs/TODO_RULES.md"

#: The synthetic rules the TODO adapter emits (the `category` A/B/C is a resolvability class, not a
#: rule; `security_sensitive` is the axis worth surfacing). `severity` here IS used at render time —
#: a TodoEntry carries none, so the adapter sources it from the catalog.
RULE_CATALOG: dict[str, RuleSpec] = {
    "todo_unresolved": {"severity": "info",    "domain": "todo", "description": "Unresolved TODO/FIXME marker"},
    "todo_security":   {"severity": "warning", "domain": "todo", "description": "Security-sensitive TODO marker"},
}

#: The authority — validates at import (D2 no-dot + severity); helpers are its bound methods.
_CATALOG = RuleCatalog(PRODUCER, RULE_CATALOG, help_base=_HELP_BASE)

rule_severity = _CATALOG.severity
rule_domain = _CATALOG.domain
rule_help_uri = _CATALOG.help_uri
qualified_id = _CATALOG.qualified_id
