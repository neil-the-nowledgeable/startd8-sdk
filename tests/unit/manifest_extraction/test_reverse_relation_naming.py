"""Custom reverse-relation names — FR-PE-13 (the `as <name>` grammar).

Gap #4 from SDK_EMITTER_GRAMMAR_GAPS_2026-06-09: a parent's reverse-list field is named by
convention (``_plural(child)`` → ``jobStatusEntries``), but the live contract uses a human-chosen
name (``statusHistory``) that owned code (`fsm.py`) references. The `as <name>` clause lets the prose
name the reverse list, so the contract stays fully derived without renaming the live field.
"""

from __future__ import annotations

import pytest

from startd8.languages.prisma_parser import parse_prisma_schema
from startd8.manifest_extraction.extract import build_entity_graph
from startd8.manifest_extraction.prisma_emitter import render_prisma_schema

pytestmark = pytest.mark.unit


def _emit(doc: str):
    return parse_prisma_schema(render_prisma_schema(build_entity_graph({"d.md": doc})).text)


def test_as_clause_names_the_reverse_list():
    doc = (
        "## Entities\n\n### JobDescription\n"
        "| Field | Type | Required | Notes |\n|-------|------|----------|-------|\n"
        "| title | text | no | |\n\n"
        "Relationships: a JobDescription **has many** JobStatusEntry **as** statusHistory.\n\n"
        "### JobStatusEntry\n"
        "| Field | Type | Required | Notes |\n|-------|------|----------|-------|\n"
        "| date | date | yes | |\n"
    )
    schema = _emit(doc)
    jd = schema.model("JobDescription")
    assert jd.field("statusHistory") is not None              # custom reverse-list name
    assert jd.field("statusHistory").type == "JobStatusEntry"
    assert jd.field("statusHistory").is_list
    assert jd.field("jobStatusEntries") is None               # convention name NOT used
    # the child still carries its FK + relation object (unchanged)
    assert schema.model("JobStatusEntry").field("jobDescriptionId") is not None


def test_without_as_clause_falls_back_to_convention():
    doc = (
        "## Entities\n\n### JobDescription\n"
        "| Field | Type | Required | Notes |\n|-------|------|----------|-------|\n"
        "| title | text | no | |\n\n"
        "Relationships: a JobDescription **has many** JobStatusEntry.\n\n"
        "### JobStatusEntry\n"
        "| Field | Type | Required | Notes |\n|-------|------|----------|-------|\n"
        "| date | date | yes | |\n"
    )
    jd = _emit(doc).model("JobDescription")
    assert jd.field("jobStatusEntries") is not None           # plural convention preserved
    assert jd.field("statusHistory") is None


def test_as_clause_on_belongs_to():
    # The child's-perspective phrasing also names the parent's reverse list (same plumbing).
    doc = (
        "## Entities\n\n### JobStatusEntry\n"
        "| Field | Type | Required | Notes |\n|-------|------|----------|-------|\n"
        "| date | date | yes | |\n\n"
        "Relationships: a JobStatusEntry **belongs to** JobDescription **as** statusHistory.\n\n"
        "### JobDescription\n"
        "| Field | Type | Required | Notes |\n|-------|------|----------|-------|\n"
        "| title | text | no | |\n"
    )
    jd = _emit(doc).model("JobDescription")
    assert jd.field("statusHistory") is not None
    assert jd.field("statusHistory").type == "JobStatusEntry"
