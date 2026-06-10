"""`_build_graph` merge completeness — the CLI extraction path must preserve EVERY graph field.

Regression for the strtd8 `generate contract --check` finding (SDK_EMITTER_GRAMMAR_GAPS_2026-06-09):
``_build_graph`` merged only entities/joins/fk_parents from each doc's sub-graph and silently dropped
``indexes`` / ``uniques`` / ``loose_refs``. The emitter renders all three correctly, but they never
reached it through the real CLI path (only the unit tests, which call ``extract_entities`` directly,
exercised them). So a "derived" contract emitted via the CLI was missing its @@index / @@unique /
loose-ref FK — `--promote` would have dropped them.
"""

from __future__ import annotations

import pytest

from startd8.languages.prisma_parser import parse_prisma_schema
from startd8.manifest_extraction.extract import build_entity_graph
from startd8.manifest_extraction.prisma_emitter import render_prisma_schema

pytestmark = pytest.mark.unit

# A doc carrying all three FR-PE-5(b/c) constructs (the TailoredMatch shape from the strtd8 report).
_DOC = (
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


def test_build_graph_preserves_indexes_uniques_loose_refs():
    g = build_entity_graph({"d.md": _DOC})
    assert g.indexes.get("TailoredMatch") == [("jobDescriptionId",)]
    assert g.uniques.get("TailoredMatch") == [("jobDescriptionId", "subjectId")]
    assert g.loose_refs.get("TailoredMatch") == ["JobDescription"]


def test_cli_path_emits_index_unique_and_loose_ref_scalar():
    # The end-to-end proof: the schema emitted from the CLI graph carries all three constructs.
    schema = parse_prisma_schema(render_prisma_schema(build_entity_graph({"d.md": _DOC})).text)
    tm = schema.model("TailoredMatch")
    assert tm.field("jobDescriptionId") is not None          # loose-ref scalar (#3, breaking)
    assert tm.field("jobDescription") is None                # ...with NO @relation object
    assert ("jobDescriptionId", "subjectId") in tm.compound_unique_keys   # @@unique (#2, breaking)
    norm = {x.replace(" ", "") for x in tm.block_attributes}
    assert "@@index([jobDescriptionId])" in norm             # @@index (#1)


def test_indexes_uniques_merge_across_docs():
    # Split the catalog across two docs (the plan+requirements case _build_graph supports). The
    # declaration-local constructs (Indexes:/Unique:) merge regardless of which doc declares them.
    # (Relationship resolution — loose_refs/joins/fk_parents — is per-doc by design, so a reference
    # whose target lives in another doc is a separate, pre-existing limitation, not exercised here.)
    doc_a = (
        "## Entities\n\n### TailoredMatch\n"
        "| Field | Type | Required | Notes |\n|-------|------|----------|-------|\n"
        "| subjectId | text | yes | |\n\n"
        "Unique: jobDescriptionId, subjectId\nIndexes: jobDescriptionId\n"
    )
    doc_b = (
        "## Entities\n\n### JobDescription\n"
        "| Field | Type | Required | Notes |\n|-------|------|----------|-------|\n"
        "| title | text | no | |\n"
    )
    g = build_entity_graph({"a.md": doc_a, "b.md": doc_b})
    assert g.uniques.get("TailoredMatch") == [("jobDescriptionId", "subjectId")]
    assert g.indexes.get("TailoredMatch") == [("jobDescriptionId",)]
