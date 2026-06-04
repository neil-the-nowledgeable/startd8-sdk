"""REQ-CKG-522/523/525 — rendering: parity with Phase-1, negatives, omissions, budget."""

from __future__ import annotations

from startd8.contractors.project_knowledge import (
    DraftModeProducer,
    Negative,
    ProjectKnowledge,
    estimate_tokens,
    render,
)
from startd8.contractors.upstream_interface import render_prisma_field_sets

SCHEMA = (
    "model Capability {\n id String @id\n name String\n score Float?\n tags String[]\n}\n"
    "model Outcome {\n id String @id\n label String\n}\n"
)


class TestPositiveSections:
    def test_interfaces_section_present(self):
        pk = DraftModeProducer().build({"lib/db.ts": "export const db = {}\n"}, "/p")
        out = render(pk, log=False)
        assert "## Upstream module interfaces" in out
        assert "`lib/db.ts` exports: db" in out

    def test_prisma_section_byte_matches_phase1_renderer(self):
        """Drift guard: the structured render must equal render_prisma_field_sets."""
        pk = DraftModeProducer().build({"schema.prisma": SCHEMA}, "/p")
        out = render(pk, log=False)
        assert render_prisma_field_sets(SCHEMA) in out


class TestNegatives:
    def test_negatives_rendered_first_class(self):
        pk = DraftModeProducer().build({"lib/db.ts": "export const db = {}\n"}, "/p")
        out = render(pk, log=False)
        assert "## Do NOT use these invented module paths" in out
        assert "`@/lib/prisma` is not a module path — use `@/lib/db`" in out


class TestOmissions:
    def test_omission_stated_never_empty_authority(self):
        pk = DraftModeProducer().build({"app/page.tsx": "export const x = 1\n"}, "/p")
        out = render(pk, log=False)
        assert "## Unavailable — state, do not assume" in out
        assert "do not assume a field set" in out
        # the empty-authority trap must NOT appear
        assert "(none)" not in out
        assert "## Prisma data model" not in out


class TestBudgetAndEmpty:
    def test_empty_pk_renders_empty_string(self):
        assert render(ProjectKnowledge(project_root="/p"), log=False) == ""

    def test_estimate_tokens_monotonic(self):
        assert estimate_tokens("") == 0
        assert estimate_tokens("a" * 40) == 10

    def test_over_budget_warns(self, caplog):
        negs = tuple(
            Negative(invented=f"@/x/{i}", correct=f"@/y/{i}") for i in range(200)
        )
        pk = ProjectKnowledge(project_root="/p", negatives=negs)
        with caplog.at_level("WARNING"):
            render(pk, budget_tokens=10, log=True)
        assert any("over budget" in r.message for r in caplog.records)


_RENDER_ENUM_SCHEMA = (
    "model M {\n id String @id\n kind AssetKind\n}\n"
    "enum AssetKind {\n resume_bullets\n cover_letter\n linkedin_blurb\n outreach_email\n}\n"
)


class TestEnumRender:
    def test_renders_enum_values_block(self):
        pk = DraftModeProducer().build({"prisma/schema.prisma": _RENDER_ENUM_SCHEMA}, "/proj")
        out = render(pk, log=False)
        assert "## Enum values — use EXACTLY these" in out
        assert "`AssetKind`: resume_bullets, cover_letter, linkedin_blurb, outreach_email" in out

    def test_no_enum_block_when_absent(self):
        pk = ProjectKnowledge(project_root="/p")
        assert "## Enum values" not in render(pk, log=False)
