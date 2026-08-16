"""query-security RULE_CATALOG — the 2nd SDK rule authority (rung 1 of the consume ladder).

Module: src/startd8/query_prime/rule_catalog.py
"""

from __future__ import annotations

import pytest

from startd8.query_prime import rule_catalog as rc
from startd8.query_prime.models import SecurityCheckType


def test_catalog_imports_and_validates():
    # importing ran _validate_catalog() (no-dot + severity + full-coverage) without raising
    assert rc.PRODUCER == "query-security"
    assert rc.RULE_CATALOG


def test_every_securitychecktype_is_catalogued():
    assert set(rc.RULE_CATALOG) == {t.value for t in SecurityCheckType}


def test_no_dots_and_qualified_id_round_trips():
    assert "." not in rc.PRODUCER
    assert all("." not in rid for rid in rc.RULE_CATALOG)
    assert rc.qualified_id("injection") == "query-security.injection"
    assert rc.qualified_id("injection").split(".", 1) == ["query-security", "injection"]


def test_severities_valid_and_defaults():
    assert all(rc.RULE_CATALOG[r]["severity"] in {"error", "warning", "info"} for r in rc.RULE_CATALOG)
    assert rc.rule_severity("injection") == "error"
    assert rc.rule_severity("lifecycle") == "warning"


def test_unknown_rule_is_loud():
    with pytest.raises(KeyError):
        rc.rule_severity("nonexistent")
