"""RULE_CATALOG — the cross-file rule authority (the 3rd producer routed to the SARIF sink).

`cross_file_verifier.Finding` is a drop-in for `coverage_map.render_sarif_from_findings`: the renderer
already reads `.check_id` (rule-id) and `.source_file` (file); `Finding` has no line (its `locus` is a
field/specifier, not a region), so results are file-level — honest, not lossy. This module adds the
enumerable authority the finding lacks: the set of `check_id`s the verifier can emit + metadata.

Keyed on the 6 stable `check_id`s (the `_to_finding(...)` phases) — NOT the finer `kind`, which falls
back to `check_id` (`cross_file_verifier.py:81`) and so has a dynamic, unbounded set. `check_id` is the
robust, always-exactly-one-of-6 rule identity the sink emits. The finer `kind` + `locus` + `remediation`
are richer context available for a later SARIF-`properties`/`fixes` enrichment.

Same D1/D2/D3 shape as `validators/rule_catalog.py` + `query_prime/rule_catalog.py`.

> ⚠️ **RULE-OF-THREE FIRED (2026-08-16): this is the 3rd SDK rule catalog** (`startd8-semantic`,
> `query-security`, now `cross-file`). All three redefine `RuleSpec` + `_validate_catalog` + the four
> `rule_*`/`qualified_id` helpers — identical but for their data. **The next step (before rung 2 adds a
> 4th, `startd8-obs`) is to extract a shared `catalog_base` and migrate all three** — the exact
> single-source distillation the RULE_CATALOG design (D3) deferred "until a 3rd consumer appears." It has.
"""

from __future__ import annotations

from typing import TypedDict

#: This catalog's producer — the namespace root of every qualified id (D2). No dots allowed.
PRODUCER = "cross-file"

_HELP_BASE = "https://github.com/neil-the-nowledgeable/startd8-sdk/blob/main/docs/CROSS_FILE_RULES.md"

_VALID_SEVERITIES = frozenset({"error", "warning", "info"})


class RuleSpec(TypedDict):
    """Fixed metadata for one rule (D1). `severity` is the DEFAULT a finding may override."""

    severity: str   # "error" | "warning" | "info" — the rule's default level
    domain: str     # grouping axis (the cross-file check family)
    description: str  # one line → SARIF rule.shortDescription


#: check_id → metadata. The 6 `_to_finding(...)` phases in `cross_file_verifier.py` — the complete set.
RULE_CATALOG: dict[str, RuleSpec] = {
    "zod_symmetry":           {"severity": "error",   "domain": "schema",  "description": "Zod schema and Prisma model disagree (field/type/relation)"},
    "unresolvable_import":    {"severity": "error",   "domain": "imports", "description": "Import path resolves to no module"},
    "missing_dependency":     {"severity": "error",   "domain": "imports", "description": "Imported package is not in dependencies"},
    "prisma_usage":           {"severity": "error",   "domain": "schema",  "description": "Prisma query uses a field/key that doesn't exist"},
    "tsconfig_paths":         {"severity": "warning", "domain": "config",  "description": "tsconfig path alias resolves to nothing"},
    "external_type_presence": {"severity": "warning", "domain": "types",   "description": "External type/member not found in the package"},
}


def _validate_catalog() -> None:
    if "." in PRODUCER:
        raise ValueError(f"PRODUCER {PRODUCER!r} must not contain '.' (D2)")
    for rule_id, spec in RULE_CATALOG.items():
        if "." in rule_id:
            raise ValueError(f"rule id {rule_id!r} must not contain '.' (D2)")
        if spec["severity"] not in _VALID_SEVERITIES:
            raise ValueError(f"rule {rule_id!r} severity {spec['severity']!r} not in {sorted(_VALID_SEVERITIES)}")


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
    """The cross-producer id `cross-file.<rule>` (D2)."""
    return f"{PRODUCER}.{rule_id}"
