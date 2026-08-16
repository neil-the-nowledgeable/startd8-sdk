"""RULE_CATALOG — the single enumerable authority for the rules the semantic validators emit.

Before this, each rule's identity + default severity was authored inline at every `SemanticIssue(...)`
call across the five `*_semantic_checks.py` files (a shadow taxonomy: ~40 scattered `check="..."`
literals, no enumerable set). This module lifts that to ONE place, so:

  * the validators source their default severity from here (`rule_severity`) instead of hard-coding it;
  * the FINDING↔REQ↔Derivation loop has an enumerable set of rule-ids with metadata to reason over
    (which checks exist, their domain, their default severity) — the artifact Derivation needs.

Design (see `docs/design/RULE-CATALOG-derivation-linchpin.md` + `…-decisions-D1-D3.md`):
  * **D1** — `RuleSpec` carries `severity` (a *default*; a finding may still override per instance),
    `domain` (a grouping axis), and `description` (→ SARIF `rule.shortDescription`). `help_uri` is a
    pure function of the id (`rule_help_uri`), so it is *derived*, not stored — storing it 42× would
    be the redundant re-derivation this exercise exists to remove.
  * **D2** — the qualified, cross-producer id is `PRODUCER.rule_id` (exactly one dot). Enforced at
    import: neither `PRODUCER` nor any rule-id may contain `.`. Bare ids stay the on-the-wire `check`
    value today (byte-identical); the dotted `qualified_id` is what the rule-id join (increment 2b)
    and the det-req `verify Checks:` convention consume.
  * **D3** — this lives with the producers (`validators/`), the authority; the SARIF sink
    (`coverage_map`) is a consumer that depends on it, never the reverse.

The det-req kit has its own sibling catalog (`det-req-kit/rule_catalog.py`, `PRODUCER="det-req"`);
the two are disjoint by namespace and share no import (the kit must not depend on startd8-sdk).
"""

from __future__ import annotations

from startd8.rule_catalog_base import RuleCatalog, RuleSpec  # RuleSpec re-exported for the annotation

#: This catalog's producer — the namespace root of every qualified id (D2). No dots allowed.
PRODUCER = "startd8-semantic"

_HELP_BASE = "https://github.com/neil-the-nowledgeable/startd8-sdk/blob/main/docs/SEMANTIC_RULES.md"


#: rule_id → its fixed metadata. Seeded from the inline literals across the 5 `*_semantic_checks.py`
#: (severities transcribed verbatim, so sourcing them back is byte-identical). Keys are the bare
#: `check` values the validators emit today. Cross-language rules (python_contamination,
#: sql_injection_risk, empty_catch_block, duplicate_definition, interface_file_contains_class,
#: missing_access_modifier) are ONE entry — their severity is consistent across every emitter.
RULE_CATALOG: dict[str, RuleSpec] = {
    # --- python (semantic_checks.py) ---
    "duplicate_main_guard":   {"severity": "warning", "domain": "structure",     "description": "Duplicate `if __name__ == \"__main__\"` guard"},
    "duplicate_definition":   {"severity": "warning", "domain": "structure",     "description": "Duplicate top-level definition"},
    "bare_except_pass":       {"severity": "warning", "domain": "quality",       "description": "Bare `except: pass` swallows all exceptions"},
    "fake_work_stub":         {"severity": "error",   "domain": "quality",       "description": "Placeholder stub simulating work (sleep + canned return)"},
    "block_scoped_namespace": {"severity": "info",    "domain": "structure",     "description": "Block-scoped namespace usage"},
    "phantom_dependency":     {"severity": "warning", "domain": "structure",     "description": "Import outside a try/except ImportError guard"},
    # --- go (go_semantic_checks.py) ---
    "unchecked_error":        {"severity": "warning", "domain": "quality",       "description": "Error value assigned but not checked"},
    "duplicate_function":     {"severity": "warning", "domain": "structure",     "description": "Duplicate function definition"},
    "fmt_println_in_service": {"severity": "warning", "domain": "quality",       "description": "fmt.Print*/Println in a non-main package"},
    "dot_import":             {"severity": "warning", "domain": "quality",       "description": "Go dot-import pollutes the namespace"},
    "python_contamination":   {"severity": "error",   "domain": "contamination", "description": "Python fingerprint in a non-Python file"},
    "package_dir_mismatch":   {"severity": "warning", "domain": "structure",     "description": "Go package name does not match its directory"},
    "invalid_go_version":     {"severity": "warning", "domain": "config",        "description": "Malformed go directive version"},
    "invalid_go_mod":         {"severity": "error",   "domain": "config",        "description": "Malformed or missing go.mod"},
    "go_version_mismatch":    {"severity": "warning", "domain": "config",        "description": "go.mod version disagrees with the toolchain"},
    # --- java (java_semantic_checks.py) ---
    "system_out_in_service":  {"severity": "warning", "domain": "quality",       "description": "System.out/err.println in a service (use SLF4J)"},
    "sql_injection_risk":     {"severity": "error",   "domain": "security",      "description": "SQL built by string concatenation — injection risk"},
    "interface_file_contains_class": {"severity": "warning", "domain": "structure", "description": "Interface file also declares a class"},
    "empty_catch_block":      {"severity": "warning", "domain": "quality",       "description": "Empty catch block swallows the exception"},
    "raw_type_usage":         {"severity": "warning", "domain": "quality",       "description": "Raw (unparameterized) generic type"},
    "missing_override":       {"severity": "warning", "domain": "quality",       "description": "Overriding method missing @Override"},
    "missing_access_modifier":{"severity": "warning", "domain": "structure",     "description": "Member missing an explicit access modifier"},
    "wildcard_import":        {"severity": "warning", "domain": "quality",       "description": "Wildcard import"},
    "package_case_mismatch":  {"severity": "warning", "domain": "structure",     "description": "Package name case disagrees with convention"},
    "package_filepath_mismatch": {"severity": "warning", "domain": "structure",  "description": "Package declaration disagrees with the file path"},
    "duplicate_method":       {"severity": "warning", "domain": "structure",     "description": "Duplicate method definition"},
    "invalid_java_version":   {"severity": "error",   "domain": "config",        "description": "Malformed or unsupported Java version"},
    # --- node.js (nodejs_semantic_checks.py) ---
    "console_log_in_service": {"severity": "warning", "domain": "quality",       "description": "console.log/warn/error in a service (use a logger)"},
    "var_usage":              {"severity": "warning", "domain": "quality",       "description": "`var` used instead of let/const"},
    "duplicate_require":      {"severity": "warning", "domain": "structure",     "description": "Duplicate require of the same module"},
    "unhandled_promise":      {"severity": "warning", "domain": "quality",       "description": "Promise without await or .catch()"},
    "module_system_mixing":   {"severity": "error",   "domain": "structure",     "description": "CommonJS and ESM mixed in one module"},
    "invalid_package_json":   {"severity": "error",   "domain": "config",        "description": "Malformed or missing package.json"},
    "invalid_node_version":   {"severity": "error",   "domain": "config",        "description": "Malformed or unsupported Node version"},
    "missing_module_type":    {"severity": "warning", "domain": "config",        "description": "package.json missing an explicit \"type\""},
    # --- c# (csharp_semantic_checks.py) ---
    "console_writeline_in_service": {"severity": "warning", "domain": "quality", "description": "Console.Write/WriteLine in a service (use ILogger)"},
    "missing_nullable_in_csproj": {"severity": "warning", "domain": "config",    "description": ".csproj missing <Nullable> enablement"},
    "missing_async_await":    {"severity": "warning", "domain": "quality",       "description": "async method with no await"},
    "global_using_static":    {"severity": "warning", "domain": "quality",       "description": "global using static pollutes every file"},
    "wrong_file_content":     {"severity": "error",   "domain": "structure",     "description": "File content does not match its declared type"},
    "namespace_case_mismatch":{"severity": "warning", "domain": "structure",     "description": "Namespace case disagrees with convention"},
    "namespace_filepath_mismatch": {"severity": "warning", "domain": "structure","description": "Namespace disagrees with the file path"},
}


#: The authority — validates at import (D2 no-dot + severity). Public helpers below are its bound
#: methods, re-exported so the module API (rule_severity / qualified_id / …, imported by the 5
#: `*_semantic_checks.py`) is byte-identical.
_CATALOG = RuleCatalog(PRODUCER, RULE_CATALOG, help_base=_HELP_BASE)

rule_severity = _CATALOG.severity
rule_domain = _CATALOG.domain
rule_help_uri = _CATALOG.help_uri
qualified_id = _CATALOG.qualified_id
