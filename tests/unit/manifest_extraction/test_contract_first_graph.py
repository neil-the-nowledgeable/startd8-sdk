"""FR-CFE — the EntityGraph is built from an authored `schema.prisma` (contract-first projects).

`graph_from_prisma` reconstructs the resolution-supporting half of the graph (entities/fields/enums/
fk_parents/joins) so the assembly extractors (views/completeness/imports) resolve entity references
without a duplicate prose `## Entities` section. Pins: entity-vs-join classification, FK reconstruction,
enum carry-through, the prose-wins merge, and the end-to-end views resolution (acceptance #1/#2/#3).
"""

from __future__ import annotations

import yaml

from startd8.languages.prisma_parser import parse_prisma_schema
from startd8.manifest_extraction import Status, extract_manifests
from startd8.manifest_extraction.entities import (
    DocEntity,
    DocField,
    EntityGraph,
    graph_from_prisma,
    merge_contract_graph,
)

_SCHEMA = """
enum Color {
  RED
  GREEN
}

model Author {
  id    String @id @default(cuid())
  name  String
  books Book[]
}

model Book {
  id       String @id @default(cuid())
  title    String
  color    Color
  pages    Int?
  authorId String
  author   Author @relation(fields: [authorId], references: [id])
  tags     BookTag[]
}

model Tag {
  id    String @id @default(cuid())
  label String
  books BookTag[]
}

model BookTag {
  bookId String
  tagId  String
  book   Book @relation(fields: [bookId], references: [id])
  tag    Tag  @relation(fields: [tagId], references: [id])
  @@unique([bookId, tagId])
}
"""


def _graph():
    return graph_from_prisma(parse_prisma_schema(_SCHEMA))


# --------------------------------------------------------------------------- graph_from_prisma


def test_entities_exclude_join_models():
    g = _graph()
    assert set(g.entities) == {"Author", "Book", "Tag"}  # BookTag is a join, not an entity


def test_join_model_detected():
    g = _graph()
    assert g.join_names == ["BookTag"]
    j = g.join_between("Book", "Tag")
    assert j is not None and {j.left, j.right} == {"Book", "Tag"}
    assert j.fk_left in ("bookId", "tagId") and j.fk_right in ("bookId", "tagId")


def test_fk_parents_reconstructed():
    g = _graph()
    assert g.fk_parents.get("Book") == ["Author"]   # the 1:N FK
    assert "BookTag" not in g.fk_parents             # join FKs are not 1:N parents


def test_enums_and_fields_carried():
    g = _graph()
    assert g.enums["Color"] == ("RED", "GREEN")
    book = g.entities["Book"]
    fields = {f.name: f for f in book.fields}
    assert fields["title"].prisma_type == "String" and fields["title"].required
    assert fields["pages"].prisma_type == "Int" and not fields["pages"].required
    assert fields["color"].enum_values == ("RED", "GREEN")


def test_resolve_entity_handles_plural_and_case():
    g = _graph()
    assert g.resolve_entity("Authors") == "Author"
    assert g.resolve_entity("books") == "Book"
    assert g.resolve_entity("Nope") is None


# --------------------------------------------------------------------------- merge (prose wins)


def test_merge_is_prose_wins_and_additive():
    prose = EntityGraph()
    prose.entities["Author"] = DocEntity(
        name="Author",
        fields=(DocField("nickname", "text", "String", True, "", False, 0),),
        heading_path=("Entities", "Author"),
    )
    merge_contract_graph(prose, _graph())
    # prose's Author is untouched (its hand-authored field survives); contract fills Book/Tag.
    assert [f.name for f in prose.entities["Author"].fields] == ["nickname"]
    assert {"Author", "Book", "Tag"} <= set(prose.entities)
    assert prose.join_between("Book", "Tag") is not None


# --------------------------------------------------------------------------- end-to-end (acceptance)

_VIEWS_MD = """
## Views

### View: Library
- Kind: dashboard
- Root: Book
- Shows: counts of Tag per Book
""".strip()


def test_views_resolve_with_contract_not_without():
    # #2: no contract → the Root is unresolvable, no views.yaml.
    r0 = extract_manifests({"views.md": _VIEWS_MD})
    assert "views.yaml" not in r0.manifests
    # #1: with the contract → Root resolves and a views.yaml round-trips (extract would raise otherwise).
    r1 = extract_manifests({"views.md": _VIEWS_MD}, live_schema_text=_SCHEMA)
    views = yaml.safe_load(r1.manifests["views.yaml"])["views"]
    assert views[0]["root"] == "Book"
    assert r1.contract_diff == []  # contract-first ⇒ no prose entities ⇒ no drift noise


def test_prose_entities_only_is_unchanged_by_a_matching_contract():
    # #3 (FR-CFE-2): a project that authors ALL its referenced entities in prose extracts identically
    # with or without the contract — prose wins, the contract merge is a no-op (fully redundant).
    doc = (
        "## Entities\n\n"
        "### Book\n\n| Field | Type | Required | Notes |\n|--|--|--|--|\n| title | text | yes | |\n\n"
        "### Tag\n\n| Field | Type | Required | Notes |\n|--|--|--|--|\n| label | text | yes | |\n\n"
        + _VIEWS_MD
    )
    without = extract_manifests({"d.md": doc}).manifests.get("views.yaml")
    with_contract = extract_manifests({"d.md": doc}, live_schema_text=_SCHEMA).manifests.get("views.yaml")
    assert without == with_contract is not None
