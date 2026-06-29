"""Unit tests for the Prisma schema parser (RUN-008 remediation FR-6).

Grounded in the real run-008 schema (``fixtures/run008_schema.prisma``) plus
synthetic edge cases. The load-bearing assertions are the ones that make FR-5
(unique-key validity) and FR-7 (Prisma↔Zod symmetry) implementable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.languages.prisma_parser import (
    PRISMA_SCALARS,
    parse_prisma_schema,
)

FIXTURE = Path(__file__).parent / "fixtures" / "run008_schema.prisma"


@pytest.fixture(scope="module")
def run008():
    return parse_prisma_schema(FIXTURE.read_text())


class TestRun008Schema:
    def test_all_models_parsed(self, run008):
        # 10 domain models + 3 join tables = 13? run-008 has 12 (9 domain + 3 join)
        assert len(run008.models) == 12
        assert "Profile" in run008.models
        assert "ProofPoint" in run008.models
        assert "ProofPointCapability" in run008.models

    def test_datasource_and_generator(self, run008):
        assert run008.datasource_provider == "sqlite"
        assert run008.generator_provider == "prisma-client-js"

    def test_profile_field_names_match_prisma_not_zod(self, run008):
        """The Prisma side of the RUN-008 divergence — the ground truth FR-7 checks against."""
        profile = run008.model("Profile")
        names = profile.field_names
        # Prisma's real field names
        assert "summary" in names
        assert "yearsExp" in names
        # The Zod-invented names must NOT appear on the Prisma side
        assert "bio" not in names
        assert "yearsOfExperience" not in names
        assert "websiteUrl" not in names
        assert "metadata" not in names

    def test_profile_unique_keys_is_id_only(self, run008):
        """The spike crux: `findUnique({where:{ownerId}})` is invalid — only `id` is unique."""
        profile = run008.model("Profile")
        assert profile.single_column_unique_keys == frozenset({"id"})
        assert "ownerId" not in profile.single_column_unique_keys
        assert profile.compound_unique_keys == ()

    def test_proofpoint_has_no_profileid_fk(self, run008):
        """ProofPoint has NO profileId — the Zod schema invented it (FR-7 must catch)."""
        pp = run008.model("ProofPoint")
        assert "profileId" not in pp.field_names
        # It uses join-table relations instead
        assert "capabilities" in pp.field_names
        assert "outcomes" in pp.field_names

    def test_relation_vs_scalar_classification(self, run008):
        pp = run008.model("ProofPoint")
        capabilities = pp.field("capabilities")
        assert capabilities.is_list is True
        assert run008.is_relation_field(capabilities) is True
        # join-table FK columns are scalars, the object links are relations
        ppc = run008.model("ProofPointCapability")
        assert run008.is_relation_field(ppc.field("proofPointId")) is False  # scalar String
        assert run008.is_relation_field(ppc.field("proofPoint")) is True  # @relation object
        scalar_names = {f.name for f in run008.scalar_fields("ProofPointCapability")}
        assert "proofPointId" in scalar_names
        assert "proofPoint" not in scalar_names

    def test_compound_unique_on_join_table(self, run008):
        ppc = run008.model("ProofPointCapability")
        assert ppc.compound_unique_keys == (("proofPointId", "capabilityId"),)
        # neither FK is independently unique
        assert ppc.single_column_unique_keys == frozenset({"id"})

    def test_field_modifiers(self, run008):
        profile = run008.model("Profile")
        assert profile.field("name").is_optional is False
        assert profile.field("title").is_optional is True
        assert profile.field("yearsExp").type == "Int"
        assert profile.field("id").is_id is True
        assert profile.field("id").is_unique is False  # @id, not @unique


class TestEdgeCases:
    def test_empty_and_blank(self):
        assert parse_prisma_schema("").models == {}
        assert parse_prisma_schema("   \n\n  ").models == {}

    def test_enum_parsing(self):
        text = """
        enum Role {
          USER
          ADMIN  // an admin
          SUPERADMIN
        }
        model U {
          id   String @id @default(cuid())
          role Role
        }
        """
        schema = parse_prisma_schema(text)
        assert schema.enums["Role"] == ("USER", "ADMIN", "SUPERADMIN")
        # an enum-typed field is scalar (not a relation)
        u = schema.model("U")
        assert schema.is_scalar_type("Role") is True
        assert schema.is_relation_field(u.field("role")) is False

    def test_single_column_unique(self):
        text = """
        model Account {
          id    String @id @default(cuid())
          email String @unique
          name  String
        }
        """
        acct = parse_prisma_schema(text).model("Account")
        assert acct.single_column_unique_keys == frozenset({"id", "email"})

    def test_comment_inside_string_default_preserved(self):
        """`//` inside a @default string must not be treated as a comment."""
        text = 'model X {\n  id  String @id\n  url String @default("https://a//b")\n}\n'
        x = parse_prisma_schema(text).model("X")
        url = x.field("url")
        assert url is not None
        assert any('https://a//b' in a for a in url.attributes)

    def test_list_type_modifier(self):
        text = """
        model Post {
          id   String   @id
          tags String[]
        }
        """
        post = parse_prisma_schema(text).model("Post")
        tags = post.field("tags")
        assert tags.is_list is True
        assert tags.type == "String"

    def test_malformed_block_is_lenient(self):
        # a stray non-field line should be skipped, valid fields still parsed
        text = """
        model M {
          id String @id
          this is not a valid field line ???
          name String
        }
        """
        m = parse_prisma_schema(text).model("M")
        assert m is not None
        assert "id" in m.field_names
        assert "name" in m.field_names

    def test_scalars_constant(self):
        assert "String" in PRISMA_SCALARS
        assert "DateTime" in PRISMA_SCALARS
        assert "Profile" not in PRISMA_SCALARS


class TestNavLabelOverride:
    """FR-26: a `/// @nav <Label>` doc-comment above a model overrides its derived nav label."""

    SCHEMA = (
        "/// @nav Invoices\n"
        "model Invoice {\n"
        "  id String @id\n"
        "  amount Float\n"
        "}\n\n"
        "model LineItem {\n"
        "  id String @id\n"
        "}\n"
    )

    def test_annotation_sets_nav_label(self):
        schema = parse_prisma_schema(self.SCHEMA)
        assert schema.model("Invoice").nav_label == "Invoices"

    def test_absent_annotation_is_none(self):
        schema = parse_prisma_schema(self.SCHEMA)
        assert schema.model("LineItem").nav_label is None

    def test_annotation_does_not_disturb_fields_or_relations(self):
        # the additive scan must not change normal parsing (fields, ids stay intact)
        schema = parse_prisma_schema(self.SCHEMA)
        inv = schema.model("Invoice")
        assert inv.field_names == frozenset({"id", "amount"})
        assert "id" in inv.single_column_unique_keys

    def test_no_annotation_schema_unchanged(self):
        # a schema with no `/// @nav` parses identically (nav_label defaults to None everywhere)
        plain = parse_prisma_schema("model Widget {\n  id String @id\n  name String\n}\n")
        assert plain.model("Widget").nav_label is None
        assert plain.model("Widget").field_names == frozenset({"id", "name"})
