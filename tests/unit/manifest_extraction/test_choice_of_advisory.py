"""FR-F1/F8 regression: an in-table `choice of: a|b|c` with UNESCAPED pipes silently truncated the
enum to its first value, and `kickoff check` reported "docs conform" (false-green).

Client friction (portal-rebuild F1/F8): the `|` collided with the Markdown table column separator, so
`| status | choice of: not_started|in_progress|submitted |` split into extra columns and `status`
extracted a single enum value. These tests assert the new advisory signal fires (fail on `main`,
which emits no advisory) and that FR-F1e's ragged-row evidence distinguishes truncation from a
genuine single-member vocabulary.
"""
from __future__ import annotations

import pytest

from startd8.manifest_extraction.extract import extract_manifests

pytestmark = pytest.mark.unit


def _advisories(result):
    return [r for r in result.records if r.is_advisory]


def _entity_doc(type_cell: str) -> str:
    return (
        "## Entities\n\n"
        "### Assignment\n"
        "| Field | Type | Required | Notes |\n"
        "|-------|------|----------|-------|\n"
        f"| status | {type_cell} | yes | |\n"
    )


def test_unescaped_intable_choice_of_is_flagged_advisory():
    """The F1 bug: unescaped pipes truncate the enum → exactly one value extracted → advisory."""
    result = extract_manifests({"d.md": _entity_doc("choice of: not_started|in_progress|submitted")})
    adv = _advisories(result)
    assert len(adv) == 1, "a truncated in-table choice-of must produce a choice-of-single-value advisory"
    r = adv[0]
    assert r.value_path == "/models/Assignment/fields/status"
    assert "choice-of-single-value" in (r.reason or "")
    # FR-F1e: the ragged row (extra cells from the split) is truncation evidence — the advisory must
    # name the unescaped-pipe cause, not the generic single-member one.
    assert "unescaped `|`" in r.reason


def test_escaped_intable_choice_of_extracts_all_values_no_advisory():
    """FR-F1b: escaping literal pipes as `\\|` keeps the enum intact — no advisory."""
    result = extract_manifests({"d.md": _entity_doc("choice of: not_started\\|in_progress\\|submitted")})
    assert _advisories(result) == []


def test_genuine_single_member_choice_of_is_advisory_but_not_truncation():
    """A well-formed single-member `choice of:` (no ragged row) is still advisory (a smell), but the
    reason must NOT blame an unescaped pipe — FR-F1e's disambiguator keeps `--strict` safe."""
    result = extract_manifests({"d.md": _entity_doc("choice of: only_value")})
    adv = _advisories(result)
    assert len(adv) == 1
    assert "unescaped `|`" not in adv[0].reason
    assert "single-member" in adv[0].reason
