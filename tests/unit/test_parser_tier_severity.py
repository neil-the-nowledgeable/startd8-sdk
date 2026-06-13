"""WI-7 / FR-CL-5: the parser_tier severity calibration (MULTILANG FR-5).

AC-8 claimed this calibration was duplicated (forward_manifest.py:608 +
validator). On inspection it was a misread: the forward_manifest.py site is a
*skip-on-None* check (unsupported language), not severity logic. The mapping lives
in exactly one place. This pins that single source — the load-bearing rule that an
*advisory* (regex-grade) miss must NEVER block a review, while authoritative and
legacy (None) misses are errors.
"""

from __future__ import annotations

from startd8.forward_manifest_validator import severity_for_parser_tier


def test_advisory_is_warning() -> None:
    # Regex-grade parsers (Go/Node/Vue) — a blind spot must not block (FR-5).
    assert severity_for_parser_tier("advisory") == "warning"


def test_authoritative_is_error() -> None:
    assert severity_for_parser_tier("authoritative") == "error"


def test_none_is_error_legacy_python_path() -> None:
    # Unset tier (legacy Python AST path) is treated as authoritative.
    assert severity_for_parser_tier(None) == "error"


def test_unknown_tier_defaults_to_error() -> None:
    assert severity_for_parser_tier("something-else") == "error"
