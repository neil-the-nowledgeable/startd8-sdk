"""repair RULE_CATALOG — the 4th producer authority + the 1st catalog on the shared base.

Module: src/startd8/repair/rule_catalog.py
"""

from __future__ import annotations

import pytest

from startd8.repair import rule_catalog as rc

#: The categories the repair pipeline sets on a Diagnostic (subclass __post_init__ + base doc set).
_EMITTED = {
    "syntax", "import", "lint", "test", "size",
    "semantic", "contract_violation", "content_contract", "convention", "security",
}


def test_catalog_imports_and_validates():
    assert rc.PRODUCER == "repair"
    assert rc.RULE_CATALOG


def test_catalog_covers_the_emitted_categories():
    assert _EMITTED <= set(rc.RULE_CATALOG)


def test_no_dots_and_qualified_id_round_trips():
    assert "." not in rc.PRODUCER
    assert all("." not in rid for rid in rc.RULE_CATALOG)
    assert rc.qualified_id("syntax") == "repair.syntax"
    assert rc.qualified_id("syntax").split(".", 1) == ["repair", "syntax"]


def test_severities_valid():
    assert all(rc.RULE_CATALOG[r]["severity"] in {"error", "warning", "info"} for r in rc.RULE_CATALOG)
    assert rc.rule_severity("syntax") == "error"
    assert rc.rule_severity("lint") == "warning"


def test_unknown_rule_is_loud():
    with pytest.raises(KeyError):
        rc.rule_severity("nonexistent")
