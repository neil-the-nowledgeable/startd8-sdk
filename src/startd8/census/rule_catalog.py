"""RULE_CATALOG — the ``startd8-census`` finding-class authority (the 5th SARIF producer).

The determinism-gap census emits a finding per LLM-call and per repair-intervention on the LLM-driven
construction path. Its *finding-classes* are the taxonomy of WHY the LLM was load-bearing — an
``element-render`` (the LLM rendered a whole element there is no deterministic renderer for), a
``body-fill``, a ``repair-syntax`` intervention, etc. This module is a **data-only add** in the shared
``rule_catalog_base.RuleCatalog`` family (alongside ``startd8-semantic``, ``query-security``,
``cross-file``): a ``RULE_CATALOG`` + one ``RuleCatalog(...)`` instance, inheriting the shared no-dot /
qualified-id / severity validation. No new emitter (FR-2 / NR-2).

Design: a census finding is an OBSERVATION, not a defect — its default severity is ``info`` for every
class (a measurement, not a fault). A finding-class earns attention by **frequency × language-spread**
in the aggregate (FR-5), never by its SARIF level (design-decision — the census must not cry wolf).

  * **D1** — ``RuleSpec`` = severity (default) + domain + description; ``help_uri`` derived.
  * **D2** — ``qualified_id`` = ``startd8-census.<class>`` (one dot; no dots inside — enforced at import).
  * **D3** — lives with the producer (``census/``); the SARIF sink is a consumer.
"""

from __future__ import annotations

from startd8.rule_catalog_base import RuleCatalog, RuleSpec  # RuleSpec re-exported for the annotation

#: This catalog's producer — the namespace root of every qualified id (D2). No dots allowed.
PRODUCER = "startd8-census"

_HELP_BASE = (
    "https://github.com/neil-the-nowledgeable/startd8-sdk/blob/main/"
    "docs/design/deterministic-generation/REQ-determinism-gap-census.md"
)


#: finding-class → metadata. Two domains: ``llm-intervention`` (an LLM-call rendered/filled an element —
#: the render-gap the census exists to map) and ``repair-intervention`` (a post-generation repair step
#: fired — the LLM's output needed deterministic patching). Every class defaults to ``info`` (an
#: observation, not a fault); a class earns attention by frequency × spread, not level.
RULE_CATALOG: dict[str, RuleSpec] = {
    # --- llm-intervention: the LLM did render-work (candidate for a deterministic render-template) ---
    "element_render":   {"severity": "info", "domain": "llm-intervention",    "description": "LLM rendered a whole element (no deterministic renderer exists)"},
    "body_fill":        {"severity": "info", "domain": "llm-intervention",    "description": "LLM filled an element body against a skeleton"},
    "signature_render": {"severity": "info", "domain": "llm-intervention",    "description": "LLM rendered an element signature"},
    # --- repair-intervention: the LLM's output needed deterministic patching ---
    "repair_syntax":    {"severity": "info", "domain": "repair-intervention", "description": "Repair step fixed a syntax defect in LLM-generated code"},
    "repair_import":    {"severity": "info", "domain": "repair-intervention", "description": "Repair step fixed an import defect in LLM-generated code"},
    "repair_contract":  {"severity": "info", "domain": "repair-intervention", "description": "Repair step fixed a contract/structure defect in LLM-generated code"},
    "repair_lint":      {"severity": "info", "domain": "repair-intervention", "description": "Repair step fixed a lint defect in LLM-generated code"},
    "repair_other":     {"severity": "info", "domain": "repair-intervention", "description": "Repair step fired (unclassified category)"},
}


#: The authority — validates at import (D2 no-dot + severity). Public helpers below are its bound
#: methods, re-exported so the module API mirrors the sibling catalogs byte-for-byte.
_CATALOG = RuleCatalog(PRODUCER, RULE_CATALOG, help_base=_HELP_BASE)

rule_severity = _CATALOG.severity
rule_domain = _CATALOG.domain
rule_help_uri = _CATALOG.help_uri
qualified_id = _CATALOG.qualified_id


def help_uri_map() -> dict[str, str]:
    """Every catalogued finding-class → its derived help URI (for the SARIF renderer's ``rule_help_uris``)."""
    return {rule_id: _CATALOG.help_uri(rule_id) for rule_id in RULE_CATALOG}
