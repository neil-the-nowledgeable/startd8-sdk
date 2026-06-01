"""Tests for RUN-009 Gap A upstream-anchor parsing + seed emission (FR-1/FR-2b)."""

from __future__ import annotations

from startd8.seeds.upstream_anchors import parse_upstream_anchors
from startd8.seeds.models import ContextSeed

PLAN = """\
# My Plan

## Non-Goals
<!-- cap-dev-pipe: upstream-anchors -->
- `package.json`
- prisma/schema.prisma
- lib/db.ts
  next.config.mjs
- not a path just prose
<!-- /cap-dev-pipe -->

## Features
...
"""


class TestParse:
    def test_marker_block_paths(self):
        a = parse_upstream_anchors(PLAN)
        assert a == ["package.json", "prisma/schema.prisma", "lib/db.ts", "next.config.mjs"]
        assert "not a path just prose" not in a  # prose dropped (no / or .ext)

    def test_no_marker_empty(self):
        assert parse_upstream_anchors("# Plan\nNo markers here.\n") == []
        assert parse_upstream_anchors("") == []

    def test_terminates_at_heading(self):
        txt = "<!-- cap-dev-pipe: upstream-anchors -->\nlib/db.ts\n## Next section\napp/page.tsx\n"
        assert parse_upstream_anchors(txt) == ["lib/db.ts"]  # app/page.tsx is past the heading

    def test_dedup(self):
        txt = "<!-- cap-dev-pipe: upstream-anchors -->\nlib/db.ts\n`lib/db.ts`\n"
        assert parse_upstream_anchors(txt) == ["lib/db.ts"]


class TestSeedSerialization:
    def test_upstream_anchors_serialized_when_set(self):
        seed = ContextSeed(upstream_anchors=["package.json", "prisma/schema.prisma"])
        d = seed.to_dict()
        assert d["upstream_anchors"] == ["package.json", "prisma/schema.prisma"]

    def test_omitted_when_none(self):
        seed = ContextSeed()
        assert "upstream_anchors" not in seed.to_dict()  # _OPTIONAL_FIELDS: None → omitted


def test_nextjs_dynamic_and_group_segments():
    """Next.js [id]/[...slug]/(group) path segments must parse (regression)."""
    txt = ("<!-- cap-dev-pipe: upstream-anchors -->\n"
           "- app/api/proof-points/[id]/route.ts\n"
           "- app/[...slug]/page.tsx\n"
           "- app/(marketing)/page.tsx\n"
           "<!-- /cap-dev-pipe -->\n")
    a = parse_upstream_anchors(txt)
    assert "app/api/proof-points/[id]/route.ts" in a
    assert "app/[...slug]/page.tsx" in a
    assert "app/(marketing)/page.tsx" in a
