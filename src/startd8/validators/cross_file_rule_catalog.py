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

from startd8.rule_catalog_base import RuleCatalog, RuleSpec  # RuleSpec re-exported for the annotation

#: This catalog's producer — the namespace root of every qualified id (D2). No dots allowed.
PRODUCER = "cross-file"

_HELP_BASE = "https://github.com/neil-the-nowledgeable/startd8-sdk/blob/main/docs/CROSS_FILE_RULES.md"


#: check_id → metadata. The 6 `_to_finding(...)` phases in `cross_file_verifier.py` — the complete set.
RULE_CATALOG: dict[str, RuleSpec] = {
    "zod_symmetry":           {"severity": "error",   "domain": "schema",  "description": "Zod schema and Prisma model disagree (field/type/relation)"},
    "unresolvable_import":    {"severity": "error",   "domain": "imports", "description": "Import path resolves to no module"},
    "missing_dependency":     {"severity": "error",   "domain": "imports", "description": "Imported package is not in dependencies"},
    "prisma_usage":           {"severity": "error",   "domain": "schema",  "description": "Prisma query uses a field/key that doesn't exist"},
    "tsconfig_paths":         {"severity": "warning", "domain": "config",  "description": "tsconfig path alias resolves to nothing"},
    "external_type_presence": {"severity": "warning", "domain": "types",   "description": "External type/member not found in the package"},
}


#: The authority — validates at import (D2 no-dot + severity). Public helpers below are its bound
#: methods, re-exported so the module API (rule_severity / qualified_id / …) is unchanged.
_CATALOG = RuleCatalog(PRODUCER, RULE_CATALOG, help_base=_HELP_BASE)

rule_severity = _CATALOG.severity
rule_domain = _CATALOG.domain
rule_help_uri = _CATALOG.help_uri
qualified_id = _CATALOG.qualified_id
