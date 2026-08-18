"""startd8-obs RULE_CATALOG — producer #5 authority (rung 2, the o11y bridge).

Module: src/startd8/validators/observability_rule_catalog.py
"""

from __future__ import annotations

import re

import pytest

from startd8.validators import observability_rule_catalog as cat


def _emitted_obs_ids() -> set:
    """The OBS ids the validators actually emit (grep the `_issue(...)` call sites)."""
    import startd8.validators.observability_artifact_validators as m
    src = open(m.__file__).read()
    return set(re.findall(r'_issue\(\s*["\'](OBS-[0-9a-z]+)["\']', src))


def test_catalog_imports_and_validates():
    assert cat.PRODUCER == "startd8-obs"
    assert len(cat.RULE_CATALOG) == 36


def test_catalog_covers_every_emitted_obs_id():
    assert _emitted_obs_ids() <= set(cat.RULE_CATALOG)


def test_no_dots_and_qualified_id_round_trips():
    assert all("." not in rid for rid in cat.RULE_CATALOG)
    assert cat.qualified_id("OBS-100a") == "startd8-obs.OBS-100a"
    assert cat.qualified_id("OBS-100a").split(".", 1) == ["startd8-obs", "OBS-100a"]


def test_domains_grouped_by_family():
    assert cat.rule_domain("OBS-100a") == "dashboard"
    assert cat.rule_domain("OBS-101a") == "alert"
    assert cat.rule_domain("OBS-102a") == "slo"
    assert cat.rule_domain("OBS-400") == "cross"


def test_severities_valid_and_unknown_is_loud():
    assert all(cat.RULE_CATALOG[r]["severity"] in {"error", "warning", "info"} for r in cat.RULE_CATALOG)
    with pytest.raises(KeyError):
        cat.rule_severity("OBS-999z")
