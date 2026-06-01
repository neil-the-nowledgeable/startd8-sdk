"""Tests for the Prisma↔Zod symmetry check (RUN-008 remediation FR-7).

Grounded in the real run-008 artifacts (the divergence `tsc` provably could not
see — see the postmortem spike). The load-bearing assertions are that every
run-008 divergence is caught AND a coherent pair produces no errors.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.languages.prisma_parser import parse_prisma_schema
from startd8.validators.prisma_zod_symmetry import (
    check_prisma_zod_symmetry,
    default_entity_name,
    extract_zod_objects,
    has_errors,
)

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def run008():
    prisma = parse_prisma_schema((FIX / "run008_schema.prisma").read_text())
    zod = extract_zod_objects((FIX / "run008_value_model.ts").read_text())
    return prisma, zod


def _by_field(violations):
    return {(v.entity, v.field): v for v in violations}


class TestZodExtraction:
    def test_extracts_run008_schemas(self, run008):
        _, zod = run008
        assert "ProfileSchema" in zod
        assert "ProofPointSchema" in zod
        assert "MetricSchema" in zod

    def test_profile_field_types(self, run008):
        _, zod = run008
        profile = zod["ProfileSchema"]
        assert profile.field("bio").type_class == "string"
        assert profile.field("bio").nullable is True
        assert profile.field("yearsOfExperience").type_class == "number"
        assert profile.field("metadata").type_class == "unknown"
        assert profile.field("createdAt").type_class == "string"  # z.string().datetime()

    def test_metric_value_is_number(self, run008):
        _, zod = run008
        assert zod["MetricSchema"].field("value").type_class == "number"


class TestRun008Divergences:
    """Every divergence the postmortem documented must be flagged."""

    def test_profile_invented_fields_flagged(self, run008):
        prisma, zod = run008
        v = check_prisma_zod_symmetry(prisma, {"ProfileSchema": zod["ProfileSchema"]})
        missing = {x.field for x in v if x.kind == "field_missing_in_prisma"}
        # Zod renamed/invented: bio (vs summary), yearsOfExperience (vs yearsExp),
        # websiteUrl, metadata — none exist on the Prisma Profile.
        assert {"bio", "yearsOfExperience", "websiteUrl", "metadata"} <= missing
        # shared, compatible fields must NOT be flagged
        assert ("Profile", "name") not in _by_field(v)
        assert ("Profile", "createdAt") not in _by_field(v)  # DateTime ↔ string OK

    def test_proofpoint_invented_fk_flagged(self, run008):
        prisma, zod = run008
        v = check_prisma_zod_symmetry(prisma, {"ProofPointSchema": zod["ProofPointSchema"]})
        fk = [x for x in v if x.kind == "fk_invented"]
        assert any(x.field == "profileId" for x in fk), "invented profileId FK must be flagged"
        missing = {x.field for x in v if x.kind == "field_missing_in_prisma"}
        # category/occurredAt/verified/metadata are Zod-only scalars
        assert {"category", "verified"} <= missing
        # `source` exists in BOTH and must not be flagged
        assert ("ProofPoint", "source") not in _by_field(v)

    def test_metric_value_type_mismatch_flagged(self, run008):
        prisma, zod = run008
        v = check_prisma_zod_symmetry(prisma, {"MetricSchema": zod["MetricSchema"]})
        mismatches = [x for x in v if x.kind == "field_type_mismatch" and x.field == "value"]
        assert mismatches, "Prisma String vs Zod number on Metric.value must be flagged"
        assert "String" in mismatches[0].detail and "number" in mismatches[0].detail

    def test_full_run008_has_errors(self, run008):
        prisma, zod = run008
        v = check_prisma_zod_symmetry(prisma, zod)
        assert has_errors(v) is True
        # the run scored 0.99 PASS; this check turns it into an honest failure
        assert sum(1 for x in v if x.severity == "error") >= 8


class TestNoFalsePositives:
    def test_coherent_pair_clean(self):
        prisma = parse_prisma_schema(
            """
            model Widget {
              id        String   @id @default(cuid())
              name      String
              size      Int?
              createdAt DateTime @default(now())
            }
            """
        )
        zod = extract_zod_objects(
            """
            export const WidgetSchema = z.object({
              id: z.string(),
              name: z.string(),
              size: z.number().int().nullable(),
              createdAt: z.string().datetime(),
            });
            """
        )
        v = check_prisma_zod_symmetry(prisma, zod)
        assert [x for x in v if x.severity == "error"] == []

    def test_nested_relation_array_not_flagged(self):
        """A Zod `z.array(OtherSchema)` maps to a relation — not an invented scalar."""
        prisma = parse_prisma_schema(
            """
            model Parent {
              id       String  @id @default(cuid())
              name     String
              children Child[]
            }
            model Child { id String @id @default(cuid()) }
            """
        )
        zod = extract_zod_objects(
            """
            export const ParentSchema = z.object({
              id: z.string(),
              name: z.string(),
              children: z.array(ChildSchema),
            });
            """
        )
        v = check_prisma_zod_symmetry(prisma, zod)
        assert [x for x in v if x.field == "children"] == []

    def test_unknown_zod_type_is_permissive(self):
        prisma = parse_prisma_schema(
            "model M { id String @id @default(cuid())\n blob Json }"
        )
        zod = extract_zod_objects(
            "export const MSchema = z.object({ id: z.string(), blob: z.unknown() });"
        )
        v = check_prisma_zod_symmetry(prisma, zod)
        assert [x for x in v if x.field == "blob"] == []

    def test_no_matching_model_skipped(self):
        prisma = parse_prisma_schema("model A { id String @id @default(cuid()) }")
        zod = extract_zod_objects("export const NopeSchema = z.object({ x: z.string() });")
        assert check_prisma_zod_symmetry(prisma, zod) == []


class TestEntityMapping:
    def test_default_strips_schema_suffix(self):
        assert default_entity_name("ProfileSchema") == "Profile"
        assert default_entity_name("Profile") == "Profile"

    def test_entity_map_override(self):
        prisma = parse_prisma_schema("model Account { id String @id @default(cuid())\n email String @unique }")
        zod = extract_zod_objects("export const UserDto = z.object({ id: z.string(), email: z.string() });")
        # without a map, UserDto → "UserDto" model (absent) → skipped
        assert check_prisma_zod_symmetry(prisma, zod) == []
        # with a map, compared against Account → clean
        v = check_prisma_zod_symmetry(prisma, zod, entity_map={"UserDto": "Account"})
        assert [x for x in v if x.severity == "error"] == []
