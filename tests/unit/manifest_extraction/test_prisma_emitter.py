"""Prisma emitter (DRAFT mode) — FR-PE-1/2/3 slice 1.

Emit ``schema.prisma`` from a doc-derived EntityGraph and prove it (a) round-trips through
``parse_prisma_schema``, (b) injects the six bookkeeping fields with exact attributes, and
(c) renders relationships by convention (joins + belongs-to, with reverse lists).
"""

from __future__ import annotations

import pytest

from startd8.languages.prisma_parser import parse_prisma_schema
from startd8.manifest_extraction.entities import (
    DocEntity,
    DocField,
    EntityGraph,
    JoinModel,
    extract_entities,
)
from startd8.manifest_extraction.extract import build_entity_graph
from startd8.manifest_extraction.grammar import find_section, parse_sections
from startd8.manifest_extraction.prisma_emitter import (
    emit_schema_draft,
    parity_against_live,
    promote_schema,
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


# --------------------------------------------------------------------------- #
# FR-PE-5 (slice 3) — defaults, indexes/compound-unique, loose-ref marker
# --------------------------------------------------------------------------- #

def test_field_default_emits_non_optional():
    g = EntityGraph()
    g.entities["M"] = DocEntity("M", (
        DocField("matchScore", "number", "Int", False, "", False, 0, default="0"),
    ), ("Entities", "M"))
    f = parse_prisma_schema(render_prisma_schema(g).text).model("M").field("matchScore")
    assert "@default(0)" in f.attributes
    assert not f.is_optional                                # default ⇒ non-optional (FR-PE-5a)


def test_list_of_text_emits_string_array(tmp_path=None):
    # G3: `list of text` prose type → String[] @default([]) (Column(JSON) downstream).
    doc = (
        "## Entities\n\n### Item\n"
        "| Field | Type | Required | Notes |\n"
        "|-------|------|----------|-------|\n"
        "| tags | list of text | no | |\n"
    )
    g = build_entity_graph({"d.md": doc})
    text = render_prisma_schema(g).text
    assert "tags String[] @default([])" in text
    f = parse_prisma_schema(text).model("Item").field("tags")
    assert f.is_list and f.type == "String"        # round-trips as a list field


def test_two_relationship_lines_both_emit():
    # A SECOND `Relationships:` line must not be silently swallowed as a continuation of the first
    # (the reported bug: the relationship never emitted and --check still passed).
    doc = (
        "## Entities\n\n### Contact\n"
        "| Field | Type | Required | Notes |\n|-------|------|----------|-------|\n"
        "| name | text | yes | |\n\n"
        "Relationships: a Contact **belongs to** a JobDescription.\n"
        "Relationships: a Contact **references** a Company (optional).\n\n"
        "### JobDescription\n| Field | Type | Required | Notes |\n|-------|------|----------|-------|\n"
        "| title | text | no | |\n\n"
        "### Company\n| Field | Type | Required | Notes |\n|-------|------|----------|-------|\n"
        "| name | text | no | |\n"
    )
    c = parse_prisma_schema(render_prisma_schema(build_entity_graph({"d.md": doc})).text).model("Contact")
    assert c.field("jobDescriptionId") is not None          # first relationship (belongs-to FK)
    assert c.field("companyId") is not None                 # second line — NOT dropped
    assert c.field("companyId").is_optional                 # references (optional) → String?


def test_optional_references_emits_nullable_scalar():
    # G2: `references Y (optional)` → `yId String?` (the optional loose-ref variant).
    doc = (
        "## Entities\n\n### TailoredMatch\n"
        "| Field | Type | Required | Notes |\n|-------|------|----------|-------|\n"
        "| rationale | text | no | |\n\n"
        "Relationships: a TailoredMatch **references** a JobDescription (optional).\n\n"
        "### JobDescription\n"
        "| Field | Type | Required | Notes |\n|-------|------|----------|-------|\n"
        "| title | text | no | |\n"
    )
    tm = parse_prisma_schema(render_prisma_schema(build_entity_graph({"d.md": doc})).text).model("TailoredMatch")
    assert tm.field("jobDescriptionId").is_optional        # String? — nullable loose ref
    assert tm.field("jobDescription") is None              # still no @relation object


def test_required_references_stays_non_optional():
    doc = (
        "## Entities\n\n### TailoredMatch\n"
        "| Field | Type | Required | Notes |\n|-------|------|----------|-------|\n"
        "| rationale | text | no | |\n\n"
        "Relationships: a TailoredMatch **references** a JobDescription.\n\n"
        "### JobDescription\n"
        "| Field | Type | Required | Notes |\n|-------|------|----------|-------|\n"
        "| title | text | no | |\n"
    )
    tm = parse_prisma_schema(render_prisma_schema(build_entity_graph({"d.md": doc})).text).model("TailoredMatch")
    assert not tm.field("jobDescriptionId").is_optional     # required String (today's default)


def test_enum_default_not_a_member_is_flagged_not_blocked():
    # OQ-PE-7: a default outside the enum's value set → a warning, but the field still emits.
    doc = (
        "## Enums\n\n### Enum: Status\ndraft | final\n\n"
        "## Entities\n\n### Build\n"
        "| Field | Type | Required | Notes |\n|-------|------|----------|-------|\n"
        "| status | enum: Status | yes | default: bogus |\n"
    )
    res = render_prisma_schema(build_entity_graph({"d.md": doc}))
    assert any("default 'bogus' is not a value of enum Status" in w for w in res.warnings)
    assert "@default(bogus)" in res.text                    # not blocked — still emitted
    # a valid default produces no warning
    ok = render_prisma_schema(build_entity_graph({"d.md": doc.replace("bogus", "draft")}))
    assert ok.warnings == ()


def test_string_default_is_quoted():
    # G1: a String (non-enum/number/bool) default must be QUOTED — unquoted is invalid prisma.
    g = EntityGraph()
    g.entities["M"] = DocEntity("M", (
        DocField("heading", "text", "String", False, "", False, 0, default="Hello World"),
    ), ("Entities", "M"))
    f = parse_prisma_schema(render_prisma_schema(g).text).model("M").field("heading")
    assert '@default("Hello World")' in f.attributes      # quoted, round-trips
    assert not f.is_optional


def test_default_value_parsed_as_bounded_token():
    # G1: `default:` must stop at `(` (and ;,|), not run greedily to end-of-cell, so a trailing
    # parenthetical (e.g. an FR ref) is not swallowed into the @default(...).
    doc = (
        "## Enums\n\n### Enum: Status\ndraft | final\n\n"
        "## Entities\n\n### Build\n"
        "| Field | Type | Required | Notes |\n"
        "|-------|------|----------|-------|\n"
        "| status | enum: Status | yes | lifecycle; default: draft (FR-RM-2) |\n"
    )
    g = build_entity_graph({"d.md": doc})
    f = parse_prisma_schema(render_prisma_schema(g).text).model("Build").field("status")
    assert "@default(draft)" in f.attributes                # enum default unquoted + bounded
    assert not any("FR-RM-2" in a for a in f.attributes)    # parenthetical NOT swallowed


def test_loose_ref_emits_scalar_without_relation_or_reverse_list():
    g = EntityGraph()
    g.entities["TailoredMatch"] = DocEntity("TailoredMatch", (
        _f("rationale", "String"),), ("Entities", "TailoredMatch"))
    g.entities["JobDescription"] = DocEntity("JobDescription", (
        _f("title", "String"),), ("Entities", "JobDescription"))
    g.loose_refs["TailoredMatch"] = ["JobDescription"]
    schema = parse_prisma_schema(render_prisma_schema(g).text)
    tm = schema.model("TailoredMatch")
    assert tm.field("jobDescriptionId") is not None         # plain scalar present
    assert tm.field("jobDescription") is None               # NO @relation object (FR-PE-5c)
    assert schema.model("JobDescription").field("tailoredMatchs") is None  # NO reverse list


def test_index_and_compound_unique_block_attrs_emitted():
    g = EntityGraph()
    g.entities["TM"] = DocEntity("TM", (
        _f("a", "String", required=True), _f("b", "String", required=True),
    ), ("Entities", "TM"))
    g.indexes["TM"] = [("a",), ("a", "b")]
    g.uniques["TM"] = [("a", "b")]
    m = parse_prisma_schema(render_prisma_schema(g).text).model("TM")
    assert ("a", "b") in m.compound_unique_keys                                  # @@unique
    norm = {x.replace(" ", "") for x in m.block_attributes}
    assert "@@index([a])" in norm and "@@index([a,b])" in norm                   # @@index


def test_grammar_end_to_end_drives_fr_pe_5():
    """The full chain: doc grammar (default:/references/Unique:/Indexes:) → graph → emit."""
    doc = (
        "## Entities\n\n"
        "### TailoredMatch\n"
        "| Field | Type | Required | Notes |\n"
        "|-------|------|----------|-------|\n"
        "| matchScore | number | no | default: 0 |\n"
        "| subjectId | text | yes | |\n\n"
        "Relationships: a TailoredMatch **references** a JobDescription.\n\n"
        "Unique: jobDescriptionId, subjectId\n"
        "Indexes: jobDescriptionId\n\n"
        "### JobDescription\n"
        "| Field | Type | Required | Notes |\n"
        "|-------|------|----------|-------|\n"
        "| title | text | no | |\n"
    )
    secs = parse_sections(doc)
    root = find_section(secs, "Entities")
    blocks = [s for s in secs if s.level == root.level + 1
              and len(s.heading_path) >= 2 and s.heading_path[-2] == root.title]
    g = extract_entities("D", blocks, [])
    tm = parse_prisma_schema(render_prisma_schema(g).text).model("TailoredMatch")
    assert "@default(0)" in tm.field("matchScore").attributes                    # default: parsed
    assert tm.field("jobDescriptionId") is not None and tm.field("jobDescription") is None  # references
    assert ("jobDescriptionId", "subjectId") in tm.compound_unique_keys          # Unique:
    norm = {x.replace(" ", "") for x in tm.block_attributes}
    assert "@@index([jobDescriptionId])" in norm                                 # Indexes:


# --------------------------------------------------------------------------- #
# FR-PE-6 (round-trip + parity gate) / FR-PE-7 (run-dir emission + promotion)
# --------------------------------------------------------------------------- #

def test_emit_gate_round_trips_and_writes_run_dir_draft(tmp_path):
    run = tmp_path / "run"
    res = emit_schema_draft(_graph(), str(run))
    assert res.round_trips and res.ok and res.models == 4
    assert res.draft_path == str(run / "schema.prisma")
    assert (run / "schema.prisma").is_file()                       # run dir only (FR-PE-7)


def test_emit_gate_parity_pass_and_fail(tmp_path):
    emitted = render_prisma_schema(_graph()).text
    ok = emit_schema_draft(_graph(), str(tmp_path / "a"), live_text=emitted)
    assert ok.ok and ok.parity_drift == ()                          # zero drift ⇒ gate passes
    bad_live = emitted.replace("model Capability", "model CapabilityX")
    fail = emit_schema_draft(_graph(), str(tmp_path / "b"), live_text=bad_live)
    assert not fail.ok and fail.parity_drift                        # drift ⇒ gate fails
    assert fail.round_trips                                         # but the emit itself is valid


def test_promote_copies_draft_and_archives_handauthored(tmp_path):
    run, proj = tmp_path / "run", tmp_path / "prisma"
    emit_schema_draft(_graph(), str(run))
    proj.mkdir()
    (proj / "schema.prisma").write_text("// hand-authored, no provenance header\n")
    promoted = promote_schema(str(run), str(proj / "schema.prisma"))
    assert "startd8-artifact: prisma-schema" in (proj / "schema.prisma").read_text()  # now derived
    archived = proj / "_superseded-handauthored" / "schema.prisma"
    assert archived.is_file() and "hand-authored" in archived.read_text()             # old preserved
    assert promoted == str(proj / "schema.prisma")


def test_promote_without_gated_draft_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        promote_schema(str(tmp_path / "empty"), str(tmp_path / "prisma" / "schema.prisma"))


# --------------------------------------------------------------------------- #
# Critical (C1/C2): gate considers dropped fields + structural errors; the
# round-trip oracle is field- and enum-level, not just model names.
# --------------------------------------------------------------------------- #

def test_c2_render_exposes_field_and_enum_oracle():
    res = render_prisma_schema(_graph())
    assert res.field_names["Profile"]                                   # per-model fields recorded
    assert "name" in res.field_names["Profile"]
    assert "proofPoints" in res.field_names["Profile"]                  # reverse-list tracked too
    assert res.errors == ()


def test_c1_clean_graph_gate_ok(tmp_path):
    res = emit_schema_draft(_graph(), str(tmp_path))
    assert res.ok and res.round_trips and not res.unrenderable and not res.errors


def test_c1_gate_refuses_when_a_field_is_dropped(tmp_path):
    g = _graph()
    g.entities["Weird"] = DocEntity("Weird", (_f("blob", None),), ("Entities", "Weird"))
    res = emit_schema_draft(g, str(tmp_path))
    assert res.round_trips                       # the rest of the schema still round-trips
    assert res.unrenderable                      # but the author's `blob` field was dropped
    assert res.ok is False                       # → not safe to promote (C1)


# --------------------------------------------------------------------------- #
# High (H1 pluralizer+collision / H2 list caveat / H3 column typo / H4 warnings)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("word,plural", [
    ("Address", "addresses"), ("Box", "boxes"), ("Match", "matches"),  # sibilant → +es
    ("Day", "days"),                                                    # vowel+y → +s
    ("Capability", "capabilities"),                                     # consonant+y → ies
    ("ProofPoint", "proofPoints"), ("Outcome", "outcomes"),            # default → +s
])
def test_h1_pluralizer_edge_cases(word, plural):
    from startd8.manifest_extraction.prisma_emitter import _plural
    assert _plural(word) == plural


def test_h1_reverse_list_collision_fails_loud(tmp_path):
    g = EntityGraph()
    g.entities["Book"] = DocEntity("Book", (_f("title", "String"),), ("Entities", "Book"))
    g.entities["Note"] = DocEntity("Note", (_f("text", "String"),), ("Entities", "Note"))
    g.fk_parents["Note"] = ["Book"]                       # → Book.notes Note[]
    g.joins.append(JoinModel("BookNote", "Book", "Note"))  # → Book.notes BookNote[] (collision)
    res = render_prisma_schema(g)
    assert any("Book.notes: duplicate field" in e for e in res.errors)   # loud
    parse_prisma_schema(res.text)                                        # suppressed → still parses
    assert not emit_schema_draft(g, str(tmp_path)).ok                    # gate refuses


def _list_graph():
    g = EntityGraph()
    g.entities["M"] = DocEntity("M", (
        DocField(name="tags", plain_type="list of text", prisma_type="String",
                 required=False, notes="", human_only=False, row_index=0, is_list=True),
    ), ("Entities", "M"))
    return g


def test_h2_list_field_keeps_convention_but_warns_sqlite_caveat(tmp_path):
    res = render_prisma_schema(_list_graph())
    assert "tags String[]" in res.text                                   # convention preserved
    assert any("prisma validate" in w for w in res.warnings)             # caveat surfaced (H2)
    assert emit_schema_draft(_list_graph(), str(tmp_path)).warnings      # H4: reaches the gate


def test_h3_index_typo_fails_loud_and_suppresses(tmp_path):
    g = EntityGraph()
    g.entities["M"] = DocEntity("M", (_f("title", "String", required=True),), ("Entities", "M"))
    g.indexes["M"] = [("titel",)]                                        # typo
    res = render_prisma_schema(g)
    assert any("@@index references undeclared column" in e for e in res.errors)
    assert "@@index" not in res.text                                     # suppressed
    assert not emit_schema_draft(g, str(tmp_path)).ok


def test_h3_valid_index_column_emits():
    g = EntityGraph()
    g.entities["M"] = DocEntity("M", (_f("title", "String", required=True),), ("Entities", "M"))
    g.indexes["M"] = [("title",)]
    res = render_prisma_schema(g)
    assert not res.errors and "@@index([title])" in res.text


# --------------------------------------------------------------------------- #
# Low (L1 phantom subject / L2 `as` on joins / L3 enum reorder parity)
# --------------------------------------------------------------------------- #

def test_l1_unresolvable_relationship_subject_is_flagged():
    from startd8.manifest_extraction.entities import extract_entities
    doc = (
        "## Entities\n\n### Profile\n| Field | Type | Required | Notes |\n"
        "|--|--|--|--|\n| name | text | yes | |\n\n"
        "Relationships: a Proflie **belongs to** a Profile.\n"   # typo'd subject
    )
    secs = parse_sections(doc)
    root = find_section(secs, "Entities")
    blocks = [s for s in secs if s.level == root.level + 1
              and len(s.heading_path) >= 2 and s.heading_path[-2] == root.title]
    recs = []
    extract_entities("D", blocks, recs)
    assert any("unresolvable relationship subject" in (r.reason or "") for r in recs)


def test_l2_as_name_overrides_join_reverse_list():
    g = EntityGraph()
    g.entities["A"] = DocEntity("A", (_f("x", "String"),), ("Entities", "A"))
    g.entities["B"] = DocEntity("B", (_f("y", "String"),), ("Entities", "B"))
    g.joins.append(JoinModel("AB", "A", "B"))
    g.reverse_names[("A", "B")] = "customBs"          # `A links to many B as customBs`
    text = render_prisma_schema(g).text
    assert "customBs AB[]" in text                    # A's reverse-list uses the override (L2)


def test_l3_enum_value_reorder_is_not_parity_drift():
    a = _schema("enum Color {\n  RED\n  BLUE\n}", "model M {\n  id String @id\n  c Color\n}")
    b = _schema("enum Color {\n  BLUE\n  RED\n}", "model M {\n  id String @id\n  c Color\n}")
    assert not any("enum Color" in d for d in semantic_diff(a, b))   # reorder ≠ drift (L3)
