"""Route ContractViolations through the SARIF sink (rung 1, producer #6, a partial) + contract catalog.

Modules: src/startd8/forward_manifest_rule_catalog.py, forward_manifest_sarif.py
"""

from __future__ import annotations

import pytest

from startd8 import forward_manifest_rule_catalog as cat
from startd8.forward_manifest_sarif import _rule_id, render_contract_sarif
from startd8.forward_manifest_validator import ContractViolation


def _v(violation_type, *, expected="X", actual=None, file_path="m.py", severity="error"):
    return ContractViolation(contract_id="c", violation_type=violation_type, expected=expected,
                             actual=actual, file_path=file_path, severity=severity)


def _run0(doc):
    return doc["runs"][0]


# --- catalog + the normalization it backs ---
def test_catalog_validates_and_qualified_id():
    assert cat.PRODUCER == "contract"
    assert "missing_element" in cat.RULE_CATALOG and "unverified" in cat.RULE_CATALOG
    assert cat.qualified_id("signature_mismatch") == "contract.signature_mismatch"


def test_rule_id_normalizes_dynamic_violation_types():
    assert _rule_id("missing_function") == "missing_function"      # fixed, as-is
    assert _rule_id("unverified_credentials") == "unverified"      # dynamic → collapsed
    assert _rule_id("missing_method") == "missing_element"         # dynamic → collapsed
    # every id the adapter can produce is catalogued
    assert {_rule_id(v) for v in ("missing_import", "unverified_x", "missing_zzz", "signature_mismatch")} <= set(cat.RULE_CATALOG)


# --- adapter ---
def test_contract_violation_renders_file_level_with_the_findings_severity():
    res = _run0(render_contract_sarif([_v("missing_function", expected="def foo()", severity="error")]))["results"][0]
    assert res["ruleId"] == "missing_function"
    assert res["level"] == "error"                    # ContractViolation carries its own severity
    loc = res["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "m.py"
    assert "region" not in loc                        # ContractViolation has no line


def test_message_is_built_from_expected_and_actual():
    res = _run0(render_contract_sarif([_v("signature_mismatch", expected="f(a)", actual="f(a, b)")]))["results"][0]
    assert res["message"]["text"] == "expected f(a), got f(a, b)"


def test_dynamic_violation_types_collapse_to_stable_rules():
    vs = [_v("unverified_credentials", severity="warning"), _v("missing_method")]
    rules = {r["id"] for r in _run0(render_contract_sarif(vs))["tool"]["driver"]["rules"]}
    assert rules == {"unverified", "missing_element"}


def test_violation_without_file_is_skipped_and_counted():
    run = _run0(render_contract_sarif([_v("missing_file"), _v("missing_class", file_path=None)]))
    assert len(run["results"]) == 1
    assert run["invocations"][0]["properties"]["skipped"] == 1
