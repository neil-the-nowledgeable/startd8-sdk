"""Shared rule-catalog base (the rule-of-three distillation).

Module: src/startd8/rule_catalog_base.py
"""

from __future__ import annotations

import pytest

from startd8.rule_catalog_base import RuleCatalog

_GOOD = {"bare_rule": {"severity": "warning", "domain": "d", "description": "x"}}


def test_valid_catalog_constructs_and_helpers_work():
    c = RuleCatalog("prod", _GOOD, help_base="http://h")
    assert c.severity("bare_rule") == "warning"
    assert c.domain("bare_rule") == "d"
    assert c.help_uri("bare_rule") == "http://h#bare_rule"
    assert c.qualified_id("bare_rule") == "prod.bare_rule"
    assert c.qualified_id("bare_rule").split(".", 1) == ["prod", "bare_rule"]


def test_dot_in_producer_is_rejected():
    with pytest.raises(ValueError, match="must not contain"):
        RuleCatalog("pro.d", _GOOD, help_base="h")


def test_dot_in_rule_id_is_rejected():
    with pytest.raises(ValueError, match="must not contain"):
        RuleCatalog("p", {"a.b": {"severity": "error", "domain": "d", "description": "x"}}, help_base="h")


def test_bad_severity_is_rejected():
    with pytest.raises(ValueError, match="severity"):
        RuleCatalog("p", {"r": {"severity": "nope", "domain": "d", "description": "x"}}, help_base="h")


def test_require_all_missing_is_rejected():
    with pytest.raises(ValueError, match="not catalogued"):
        RuleCatalog("p", _GOOD, help_base="h", require_all={"bare_rule", "absent_rule"})


def test_require_all_satisfied_ok():
    RuleCatalog("p", _GOOD, help_base="h", require_all={"bare_rule"})  # no raise


def test_unknown_rule_is_loud():
    c = RuleCatalog("p", _GOOD, help_base="h")
    with pytest.raises(KeyError):
        c.severity("nonexistent")
