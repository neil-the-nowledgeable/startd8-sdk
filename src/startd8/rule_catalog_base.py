"""Shared base for the SDK's per-producer rule catalogs (the rule-of-three distillation).

Three catalogs — `validators/rule_catalog.py` (`startd8-semantic`), `query_prime/rule_catalog.py`
(`query-security`), `validators/cross_file_rule_catalog.py` (`cross-file`) — had each redefined the
same `RuleSpec` + validation + four `rule_*`/`qualified_id` helpers, identical but for their DATA.
The RULE_CATALOG design (decision D3) deferred extracting this "until a 3rd consumer appears"; it has.

This module owns the shared shape + logic once; each catalog module keeps only its data (`PRODUCER`,
`RULE_CATALOG`, `_HELP_BASE`), instantiates one `RuleCatalog`, and re-exports the four bound methods as
its module-level functions — so the public API (`rule_severity`, `qualified_id`, …) is byte-identical
to before. Behaviour-preserving: same D1/D2 shape, same formulas.

A 4th producer (`startd8-obs`, rung 2) is now a data-only add: a `RULE_CATALOG` + one `RuleCatalog(...)`.
(The det-req kit's catalog stays a separate vendored copy — cross-repo, must not import startd8-sdk.)
"""

from __future__ import annotations

from typing import Iterable, Mapping, Optional, TypedDict

#: SARIF `level` is a closed vocabulary; a rule's default severity must be one of these.
_VALID_SEVERITIES = frozenset({"error", "warning", "info"})


class RuleSpec(TypedDict):
    """Fixed metadata for one rule (D1). `severity` is the DEFAULT a finding may override."""

    severity: str   # "error" | "warning" | "info"
    domain: str     # grouping axis
    description: str  # one line → SARIF rule.shortDescription


class RuleCatalog:
    """A producer's enumerable rule authority. Validates at construction (D2 no-dot + severity, and
    optionally full-coverage of a required id set); exposes the four helpers as bound methods."""

    def __init__(
        self,
        producer: str,
        rules: Mapping[str, RuleSpec],
        *,
        help_base: str,
        require_all: Optional[Iterable[str]] = None,
    ) -> None:
        self.producer = producer
        self.rules = rules
        self._help_base = help_base
        self._validate(require_all)

    def _validate(self, require_all: Optional[Iterable[str]]) -> None:
        if "." in self.producer:
            raise ValueError(f"PRODUCER {self.producer!r} must not contain '.' (D2)")
        for rule_id, spec in self.rules.items():
            if "." in rule_id:
                raise ValueError(f"rule id {rule_id!r} must not contain '.' (D2)")
            if spec["severity"] not in _VALID_SEVERITIES:
                raise ValueError(
                    f"rule {rule_id!r} severity {spec['severity']!r} not in {sorted(_VALID_SEVERITIES)}")
        if require_all is not None:
            missing = set(require_all) - set(self.rules)
            if missing:
                raise ValueError(f"{self.producer}: rule(s) not catalogued: {sorted(missing)}")

    def severity(self, rule_id: str) -> str:
        """Default severity for *rule_id*; KeyError (loud) on an unknown rule."""
        return self.rules[rule_id]["severity"]

    def domain(self, rule_id: str) -> str:
        return self.rules[rule_id]["domain"]

    def help_uri(self, rule_id: str) -> str:
        """Derived — a pure function of the id (not stored per-rule)."""
        return f"{self._help_base}#{rule_id}"

    def qualified_id(self, rule_id: str) -> str:
        """The cross-producer id `PRODUCER.rule_id` (D2 — exactly one dot)."""
        return f"{self.producer}.{rule_id}"
