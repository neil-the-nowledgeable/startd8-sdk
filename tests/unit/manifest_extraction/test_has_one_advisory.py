"""FR-F3 regression (flag-only default landing, FR-F3-iii): `has one` was treated IDENTICALLY to
`has many`, silently emitting a one-to-many with a non-unique child FK.

Client friction (portal-rebuild F3): `an Assignment has one Review` produced `reviews Review[]` with
a non-unique `assignmentId` — the one-to-one intent was lost with no signal. Full one-to-one support
(singular relation + `@unique` child FK) is gated on the FR-F3-iv migration-safety precondition; the
default landing FLAGS `has one` as an advisory (warn; `--strict` fails) so it is no longer silent.
These tests fail on `main` (no advisory emitted) and pass with the flag.
"""
from __future__ import annotations

import pytest

from startd8.languages.prisma_parser import parse_prisma_schema
from startd8.manifest_extraction.extract import build_entity_graph, extract_manifests
from startd8.manifest_extraction.prisma_emitter import render_prisma_schema

pytestmark = pytest.mark.unit

_DOC = (
    "## Entities\n\n### Assignment\n"
    "| Field | Type | Required | Notes |\n|-------|------|----------|-------|\n"
    "| name | text | yes | |\n\n"
    "Relationships: an Assignment **has one** Review.\n\n"
    "### Review\n"
    "| Field | Type | Required | Notes |\n|-------|------|----------|-------|\n"
    "| score | number | yes | |\n"
)


def test_has_one_is_flagged_advisory():
    result = extract_manifests({"d.md": _DOC})
    adv = [r for r in result.records if r.is_advisory and "has-one-unsupported" in (r.reason or "")]
    assert len(adv) == 1, "`has one` must emit a has-one-unsupported advisory (not silently has-many)"
    assert "not yet enforced" in adv[0].reason


def test_has_one_still_emits_has_many_until_full_support():
    """Flag-only landing: the emitted schema is unchanged (has-many) — the advisory is the only
    behavioral change. Full one-to-one support (singular + @unique) is the gated follow-up (3b)."""
    schema = parse_prisma_schema(render_prisma_schema(build_entity_graph({"d.md": _DOC})).text)
    review = schema.model("Review")
    fk = review.field("assignmentId")
    assert fk is not None                     # child carries the FK
    assert not fk.is_unique                   # NOT unique yet — that's the documented gap (3b)


def test_has_many_is_not_flagged():
    """Only `has one` is advisory; a normal `has many` carries no advisory."""
    doc = _DOC.replace("**has one**", "**has many**")
    result = extract_manifests({"d.md": doc})
    assert [r for r in result.records if r.is_advisory] == []
