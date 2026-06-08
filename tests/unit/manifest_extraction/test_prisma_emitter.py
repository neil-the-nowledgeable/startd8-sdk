"""Prisma emitter (DRAFT mode) — FR-PE-1/2/3 slice 1.

Emit ``schema.prisma`` from a doc-derived EntityGraph and prove it (a) round-trips through
``parse_prisma_schema``, (b) injects the six bookkeeping fields with exact attributes, and
(c) renders relationships by convention (joins + belongs-to, with reverse lists).
"""

from __future__ import annotations

import pytest

from startd8.languages.prisma_parser import parse_prisma_schema
from startd8.manifest_extraction.entities import DocEntity, DocField, EntityGraph, JoinModel
from startd8.manifest_extraction.prisma_emitter import (
    parity_against_live,
    render_prisma_schema,
    semantic_diff,
)

pytestmark = pytest.mark.unit


def _f(name, prisma_type, required=False, human_only=False):
    return DocField(
        name=name, plain_type="text", prisma_type=prisma_type,
        required=required, notes="", human_only=human_only, row_index=0,
    )


def _graph():
    """Profile, ProofPoint (belongs to Profile), Capability; ProofPoint links-to-many Capability."""
    g = EntityGraph()
    g.entities["Profile"] = DocEntity("Profile", (
        _f("name", "String", required=True), _f("email", "String"),
    ), ("Entities", "Profile"))
    g.entities["ProofPoint"] = DocEntity("ProofPoint", (
        _f("title", "String"), _f("yearsExp", "Int"),
    ), ("Entities", "ProofPoint"))
    g.entities["Capability"] = DocEntity("Capability", (
        _f("name", "String"),
    ), ("Entities", "Capability"))
    g.fk_parents["ProofPoint"] = ["Profile"]                       # ProofPoint belongs to Profile
    g.joins.append(JoinModel("ProofPointCapability", "ProofPoint", "Capability"))
    return g


def test_emits_and_round_trips():
    res = render_prisma_schema(_graph())
    schema = parse_prisma_schema(res.text)               # must parse clean (FR-PE-1)
    assert schema.datasource_provider == "sqlite"
    assert schema.generator_provider == "prisma-client-js"
    assert set(schema.models) == {"Profile", "ProofPoint", "Capability", "ProofPointCapability"}
    assert res.models_rendered == 4
    assert res.unrenderable == ()


def test_bookkeeping_injected_with_exact_attributes():
    schema = parse_prisma_schema(render_prisma_schema(_graph()).text)
    for model_name in ("Profile", "ProofPoint", "Capability", "ProofPointCapability"):
        m = schema.model(model_name)
        names = m.field_names
        assert {"id", "ownerId", "source", "confirmed", "createdAt", "updatedAt"} <= names
        assert m.field("id").is_id
        assert "@default(cuid())" in m.field("id").attributes
        assert "@default(true)" in m.field("confirmed").attributes
        assert "@updatedAt" in m.field("updatedAt").attributes


def test_scalar_field_types_and_optionality():
    schema = parse_prisma_schema(render_prisma_schema(_graph()).text)
    profile = schema.model("Profile")
    assert profile.field("name").type == "String" and not profile.field("name").is_optional
    assert profile.field("email").is_optional                       # required=no → optional
    assert schema.model("ProofPoint").field("yearsExp").type == "Int"


def test_belongs_to_renders_fk_relation_and_reverse_list():
    schema = parse_prisma_schema(render_prisma_schema(_graph()).text)
    pp = schema.model("ProofPoint")
    assert pp.field("profileId") is not None                        # child FK scalar
    assert pp.field("profile").has_relation_attr                    # child relation object
    profile = schema.model("Profile")
    assert profile.field("proofPoints").is_list                     # parent reverse list
    assert profile.field("proofPoints").type == "ProofPoint"


def test_join_model_fk_relations_and_compound_unique():
    schema = parse_prisma_schema(render_prisma_schema(_graph()).text)
    j = schema.model("ProofPointCapability")
    assert j.field("proofPointId") is not None and j.field("capabilityId") is not None
    assert j.field("proofPoint").has_relation_attr and j.field("capability").has_relation_attr
    assert ("proofPointId", "capabilityId") in j.compound_unique_keys
    # reverse lists on both sides, named by the OTHER entity, typed by the join model
    assert schema.model("ProofPoint").field("capabilities").type == "ProofPointCapability"
    assert schema.model("Capability").field("proofPoints").type == "ProofPointCapability"


def test_unknown_type_flagged_never_emitted():
    g = _graph()
    g.entities["Weird"] = DocEntity("Weird", (_f("blob", None),), ("Entities", "Weird"))
    res = render_prisma_schema(g)
    assert any(u.entity == "Weird" and u.field == "blob" for u in res.unrenderable)
    assert parse_prisma_schema(res.text).model("Weird").field("blob") is None  # not emitted


def test_deterministic_byte_stable():
    g = _graph()
    assert render_prisma_schema(g).text == render_prisma_schema(g).text


# --------------------------------------------------------------------------- #
# FR-PE-4 — semantic parity diff
# --------------------------------------------------------------------------- #

_PREAMBLE = (
    'generator client {\n  provider = "prisma-client-js"\n}\n\n'
    'datasource db {\n  provider = "sqlite"\n  url      = env("DATABASE_URL")\n}\n\n'
)


def _schema(*models: str) -> str:
    return _PREAMBLE + "\n\n".join(models)


def test_semantic_diff_self_is_clean():
    # The emitter's own output has zero semantic drift against itself (FR-PE-6 parity baseline).
    text = render_prisma_schema(_graph()).text
    assert semantic_diff(text, text) == []


def test_semantic_diff_flags_type_and_optionality():
    left = _schema("model M {\n  id String @id\n  name String?\n}")
    right = _schema("model M {\n  id String @id\n  name String\n}")
    drift = semantic_diff(left, right)
    assert any("M.name: type String? (emitted) vs String (live)" == d for d in drift)


def test_semantic_diff_flags_field_default_attr():
    # The FR-PE-5 "@default on a non-bookkeeping field" gap: emitted lacks it, live has it.
    left = _schema("model M {\n  id String @id\n  score Int\n}")
    right = _schema("model M {\n  id String @id\n  score Int @default(0)\n}")
    drift = semantic_diff(left, right)
    assert any("M.score: attr @default(0) in live, not emitted" == d for d in drift)


def test_semantic_diff_flags_block_attrs():
    # FR-PE-5 @@index / compound @@unique gaps surface as block-attr drift.
    left = _schema("model M {\n  id String @id\n  ref String\n}")
    right = _schema("model M {\n  id String @id\n  ref String\n  @@index([ref])\n}")
    drift = semantic_diff(left, right)
    assert any("M: block-attr @@index([ref]) in live, not emitted" == d for d in drift)


def test_semantic_diff_flags_missing_and_extra_models():
    left = _schema("model A {\n  id String @id\n}")
    right = _schema("model B {\n  id String @id\n}")
    drift = semantic_diff(left, right)
    assert "model A: emitted, absent from live" in drift
    assert "model B: in live, not emitted" in drift


def test_parity_against_live_surfaces_fr_pe_5_gaps():
    # Slice-1 emitter vs a live model carrying all three FR-PE-5 constructs → each flagged,
    # nothing silently passed. This is the measurement that defines slice-3's worklist.
    g = EntityGraph()
    g.entities["Match"] = DocEntity("Match", (
        DocField("matchScore", "number", "Int", False, "", False, 0),
        DocField("subjectId", "text", "String", True, "", False, 1),
    ), ("Entities", "Match"))
    live = _schema(
        "model Match {\n"
        "  id String @id @default(cuid())\n"
        "  ownerId String @default(\"local\")\n"
        "  source String @default(\"user\")\n"
        "  confirmed Boolean @default(true)\n"
        "  createdAt DateTime @default(now())\n"
        "  updatedAt DateTime @updatedAt\n"
        "  matchScore Int @default(0)\n"
        "  subjectId String\n"
        "  @@index([subjectId])\n"
        "}"
    )
    drift = parity_against_live(g, live)
    assert any("matchScore: attr @default(0) in live" in d for d in drift)        # gap (a) default
    assert any("block-attr @@index([subjectId]) in live" in d for d in drift)     # gap (b) index
    # gap (c) loose-ref: a non-FK `subjectId` scalar already emits correctly — NO drift. The
    # slice-3 worklist is therefore (a) defaults + (b) indexes/compound-unique, not loose-ref render.
    assert not any("subjectId: type" in d or "subjectId: attr" in d for d in drift)
