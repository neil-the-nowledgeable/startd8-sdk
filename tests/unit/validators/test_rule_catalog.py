"""Tests for the RULE_CATALOG authority module (validators/rule_catalog.py).

The catalog is the single enumerable source of the rules the semantic validators emit. These tests
guard its invariants (D2 no-dot namespace, closed severity set) and — the load-bearing one —
`test_completeness`: a new `check="..."` cannot be added to a validator without registering it in the
catalog, or `rule_severity(...)` would raise KeyError at emit time.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from startd8.validators import rule_catalog
from startd8.validators.rule_catalog import (
    PRODUCER,
    RULE_CATALOG,
    qualified_id,
    rule_severity,
)

_VALIDATOR_DIR = Path(rule_catalog.__file__).parent
_VALIDATOR_FILES = [
    "semantic_checks.py",
    "go_semantic_checks.py",
    "java_semantic_checks.py",
    "nodejs_semantic_checks.py",
    "csharp_semantic_checks.py",
]
_CHECK_LITERAL_RE = re.compile(r'check="([^"]+)"')
_VALID_SEVERITIES = {"error", "warning", "info"}


def _emitted_check_literals() -> set[str]:
    """Every `check="..."` literal grep'd across the 5 validator source files."""
    literals: set[str] = set()
    for name in _VALIDATOR_FILES:
        src = (_VALIDATOR_DIR / name).read_text()
        literals.update(_CHECK_LITERAL_RE.findall(src))
    return literals


def test_catalog_imports_and_validates():
    """Importing rule_catalog runs `_validate_catalog()` (D2 no-dot + severity checks) at import.

    Re-importing must not raise; and the module-level validator must be present.
    """
    import importlib

    importlib.reload(rule_catalog)  # re-runs _validate_catalog() — must not raise
    assert callable(rule_catalog._validate_catalog)
    rule_catalog._validate_catalog()  # explicit re-run, belt-and-suspenders


def test_completeness():
    """Every check literal emitted by the 5 validators is a key in RULE_CATALOG.

    This is the guard: a validator cannot emit a rule the catalog doesn't know, or `rule_severity`
    would KeyError at runtime.
    """
    emitted = _emitted_check_literals()
    assert emitted, "expected to find check=\"...\" literals in the validator sources"
    missing = emitted - set(RULE_CATALOG)
    assert not missing, f"validators emit checks absent from RULE_CATALOG: {sorted(missing)}"


def test_no_dots_in_ids():
    """D2: PRODUCER and every rule-id contain no `.`; qualified_id round-trips cleanly."""
    assert "." not in PRODUCER
    for rule_id in RULE_CATALOG:
        assert "." not in rule_id, f"rule id {rule_id!r} contains a dot (violates D2)"

    assert qualified_id("bare_except_pass") == "startd8-semantic.bare_except_pass"
    producer, rule_id = qualified_id("bare_except_pass").split(".", 1)
    assert (producer, rule_id) == (PRODUCER, "bare_except_pass")


def test_unknown_rule_is_loud():
    """An unregistered rule id raises KeyError (never a silent default)."""
    with pytest.raises(KeyError):
        rule_severity("nonexistent")


def test_every_rule_has_valid_severity():
    """Every catalog severity is in the closed set {error, warning, info}."""
    for rule_id, spec in RULE_CATALOG.items():
        assert spec["severity"] in _VALID_SEVERITIES, (
            f"rule {rule_id!r} has invalid severity {spec['severity']!r}"
        )
