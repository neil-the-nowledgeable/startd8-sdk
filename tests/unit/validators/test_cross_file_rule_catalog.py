"""cross-file RULE_CATALOG — the 3rd SDK rule authority (consume-ladder rung 1, producer #3).

Module: src/startd8/validators/cross_file_rule_catalog.py
"""

from __future__ import annotations

import pytest

from startd8.validators import cross_file_rule_catalog as cat

#: The complete set of `check_id`s `cross_file_verifier._to_finding(...)` can emit.
_CHECK_IDS = {
    "zod_symmetry", "unresolvable_import", "missing_dependency",
    "prisma_usage", "tsconfig_paths", "external_type_presence",
}


def test_catalog_imports_and_validates():
    assert cat.PRODUCER == "cross-file"
    assert cat.RULE_CATALOG


def test_catalog_covers_every_verifier_check_id():
    assert set(cat.RULE_CATALOG) == _CHECK_IDS


def test_no_dots_and_qualified_id_round_trips():
    assert "." not in cat.PRODUCER
    assert all("." not in rid for rid in cat.RULE_CATALOG)
    assert cat.qualified_id("zod_symmetry") == "cross-file.zod_symmetry"
    assert cat.qualified_id("zod_symmetry").split(".", 1) == ["cross-file", "zod_symmetry"]


def test_severities_valid():
    assert all(cat.RULE_CATALOG[r]["severity"] in {"error", "warning", "info"} for r in cat.RULE_CATALOG)
    assert cat.rule_severity("zod_symmetry") == "error"
    assert cat.rule_severity("tsconfig_paths") == "warning"


def test_unknown_rule_is_loud():
    with pytest.raises(KeyError):
        cat.rule_severity("nonexistent")
