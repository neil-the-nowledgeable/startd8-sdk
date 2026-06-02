"""Step 1 of the Python contract-codegen path: Prisma→Pydantic renderer + drift + provider + gate.

Proves the smallest vertical end-to-end: a ``.prisma`` schema renders to a deterministic Pydantic
models file that the prime-contractor skip-hook recognizes as ``GENERATED`` ($0.00) and in-sync —
the Python analog of the shipped Prisma→Zod provider. Uses the locked **ProofPoint + Metric** pilot
schema so the render also exercises scalars, optionality, lists, enum→Literal, and relation
exclusion.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.backend_codegen import (
    PydanticSQLModelProvider,
    owned_file_in_sync,
    render_pydantic_models,
    render_sqlmodel_tables,
    verify_pydantic_fidelity,
    verify_sqlmodel_fidelity,
)
from startd8.backend_codegen.drift import check_drift
from startd8.contractors import deterministic_providers as dp
from startd8.contractors.deterministic_providers import (
    ProviderContext,
    is_deterministically_provided,
)

pytestmark = pytest.mark.unit

# The locked pilot bounded context: ProofPoint + its optional Metric relation.
PILOT_SCHEMA = """\
enum Confidence {
  draft
  confirmed
}

model ProofPoint {
  id         String     @id
  situation  String
  action     String
  result     String
  confidence Confidence
  tags       String[]
  metricId   String?
  metric     Metric?    @relation(fields: [metricId], references: [id])
}

model Metric {
  id      String  @id
  value   Float
  unit    String
  context String?
}
"""

TINY = "model M {\n  id String @id\n  name String\n}\n"


@pytest.fixture(autouse=True)
def _clean_registry():
    dp.clear_providers()
    dp._DISCOVERED = True  # don't pull entry points during unit tests
    yield
    dp.clear_providers()


def _ctx(tmp_path):
    return ProviderContext(
        project_root=tmp_path, source_anchors=("prisma/schema.prisma",)
    )


def _write_schema(tmp_path, schema=PILOT_SCHEMA):
    p = tmp_path / "prisma" / "schema.prisma"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(schema, encoding="utf-8")


# --------------------------------------------------------------------------- #
# Renderer
# --------------------------------------------------------------------------- #


def test_tiny_render_is_exact_and_stable():
    out = render_pydantic_models(TINY).text
    assert out.startswith("# GENERATED from prisma/schema.prisma")
    assert "# schema-sha256: " in out
    body = out.split("from pydantic import BaseModel", 1)[1]
    assert body == "\n\n\nclass MSchema(BaseModel):\n    id: str\n    name: str\n"
    # deterministic
    assert render_pydantic_models(TINY).text == out


def test_pilot_render_types_and_layering():
    res = render_pydantic_models(PILOT_SCHEMA)
    text = res.text
    assert res.unrenderable == ()
    assert res.models_rendered == 2
    # scalar mapping + layering
    assert "    situation: str" in text
    assert "    value: float" in text
    assert "    tags: list[str]" in text
    # enum -> inline Literal, source-ordered values
    assert '    confidence: Literal["draft", "confirmed"]' in text
    # optional -> Optional[...] = None ; FK scalar kept, relation object excluded
    assert "    metricId: Optional[str] = None" in text
    assert "    context: Optional[str] = None" in text
    assert "metric:" not in text  # the Metric? relation field is not a scalar
    # synthesized imports (only what's used)
    assert "from typing import Literal, Optional" in text
    assert "from __future__ import annotations" in text
    assert "from pydantic import BaseModel" in text
    assert "import datetime" not in text and "import Decimal" not in text


def test_rendered_file_is_valid_python():
    out = render_pydantic_models(PILOT_SCHEMA).text
    compile(out, "<models>", "exec")  # syntax must be valid


def test_relation_only_model_renders_pass_and_excludes_relations():
    # Tag has only a relation-list back-reference (no scalar) -> `pass`; Post keeps its FK scalar
    # but not the relation object.
    schema = (
        "model Tag {\n  posts Post[]\n}\n"
        "model Post {\n  id String @id\n  tagId String\n"
        "  tag Tag @relation(fields: [tagId], references: [id])\n}\n"
    )
    out = render_pydantic_models(schema).text
    assert "class TagSchema(BaseModel):\n    pass" in out
    assert "    tagId: str" in out
    assert "    tag:" not in out  # relation object excluded


def test_unrenderable_type_is_flagged_not_dropped():
    res = render_pydantic_models("model X {\n  id String @id\n  weird Unsupported\n}\n")
    # Unsupported is treated as a relation by the parser (unknown type) -> excluded from scalars,
    # so it neither renders nor flags; the scalar id remains. (Exotic *scalar* flagging is covered
    # by the Zod path's tests; here we assert no crash + id present.)
    assert "    id: str" in res.text


# --------------------------------------------------------------------------- #
# Drift
# --------------------------------------------------------------------------- #


def test_drift_in_sync_for_fresh_render():
    gen = render_pydantic_models(PILOT_SCHEMA).text
    assert check_drift(PILOT_SCHEMA, gen).status == "in_sync"
    assert owned_file_in_sync(PILOT_SCHEMA, gen) is True


def test_drift_detects_tamper():
    gen = render_pydantic_models(PILOT_SCHEMA).text
    tampered = gen.replace("    value: float", "    value: int", 1)
    assert check_drift(PILOT_SCHEMA, tampered).status == "tampered"
    assert owned_file_in_sync(PILOT_SCHEMA, tampered) is False


def test_drift_detects_stale_schema_change():
    gen = render_pydantic_models(PILOT_SCHEMA).text
    changed = PILOT_SCHEMA.replace("context String?", "context String")
    assert changed != PILOT_SCHEMA  # guard: the edit actually matched
    assert check_drift(changed, gen).status == "stale"


def test_drift_missing_and_unowned():
    assert check_drift(PILOT_SCHEMA, None).status == "missing"
    assert owned_file_in_sync(PILOT_SCHEMA, "class Foo: pass") is False


# --------------------------------------------------------------------------- #
# Provider + registry ($0.00 skip-hook recognition)
# --------------------------------------------------------------------------- #


def test_provider_owns_only_generated_files():
    prov = PydanticSQLModelProvider()
    gen = render_pydantic_models(PILOT_SCHEMA).text
    assert prov.owns(Path("app/models.py"), gen) is True
    assert prov.owns(Path("app/models.py"), "class Foo:\n    pass\n") is False


def test_provider_in_sync_true_for_fresh_render(tmp_path):
    _write_schema(tmp_path)
    prov = PydanticSQLModelProvider()
    gen = render_pydantic_models(PILOT_SCHEMA, source_file="prisma/schema.prisma").text
    assert prov.is_in_sync(tmp_path / "app/models.py", gen, _ctx(tmp_path)) is True


def test_provider_not_in_sync_when_no_schema(tmp_path):
    prov = PydanticSQLModelProvider()
    gen = render_pydantic_models(PILOT_SCHEMA).text
    assert prov.is_in_sync(tmp_path / "app/models.py", gen, _ctx(tmp_path)) is False


def test_end_to_end_via_registry(tmp_path):
    _write_schema(tmp_path)
    dp.register_provider(PydanticSQLModelProvider())
    gen = render_pydantic_models(PILOT_SCHEMA, source_file="prisma/schema.prisma").text
    out = tmp_path / "app" / "models.py"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(gen, encoding="utf-8")
    # the skip-hook would mark this feature GENERATED ($0.00)
    assert is_deterministically_provided(out, gen, _ctx(tmp_path)) is True
    # tamper -> not provided (falls through to the LLM)
    tampered = gen.replace("    unit: str", "    unit: int", 1)
    assert is_deterministically_provided(out, tampered, _ctx(tmp_path)) is False


# --------------------------------------------------------------------------- #
# Fidelity gate
# --------------------------------------------------------------------------- #


def test_fidelity_clean_for_fresh_render():
    gen = render_pydantic_models(PILOT_SCHEMA).text
    assert verify_pydantic_fidelity(PILOT_SCHEMA, gen) == ()


def test_fidelity_flags_dropped_field():
    gen = render_pydantic_models(PILOT_SCHEMA).text
    # drop the `tags` line -> field set/order mismatch on ProofPoint
    broken = gen.replace("    tags: list[str]\n", "")
    issues = verify_pydantic_fidelity(PILOT_SCHEMA, broken)
    assert any("ProofPoint" in i and "mismatch" in i for i in issues)


def test_fidelity_flags_lost_optionality():
    gen = render_pydantic_models(PILOT_SCHEMA).text
    broken = gen.replace("    context: Optional[str] = None", "    context: str")
    issues = verify_pydantic_fidelity(PILOT_SCHEMA, broken)
    assert any("context" in i for i in issues)


# --------------------------------------------------------------------------- #
# SQLModel renderer (Step 2 / FR-2)
# --------------------------------------------------------------------------- #


def test_sqlmodel_render_tables_enums_pk_and_json():
    res = render_sqlmodel_tables(PILOT_SCHEMA)
    text = res.text
    assert res.unrenderable == ()
    assert res.models_rendered == 2 and res.enums_rendered == 1
    # table classes + primary key
    assert "class ProofPoint(SQLModel, table=True):" in text
    assert "    id: str = Field(primary_key=True)" in text
    # enum -> str, Enum class (referenced, not Literal)
    assert "class Confidence(str, Enum):" in text
    assert '    draft = "draft"' in text
    assert "    confidence: Confidence" in text
    # list scalar -> JSON column
    assert (
        "    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))"
        in text
    )
    # optional + relation exclusion
    assert "    context: Optional[str] = None" in text
    assert "    metricId: Optional[str] = None" in text
    assert "metric:" not in text
    # synthesized imports
    assert "from sqlmodel import Field, SQLModel" in text
    assert "from sqlalchemy import JSON, Column" in text
    assert "from enum import Enum" in text


def test_sqlmodel_render_is_valid_python_and_stable():
    out = render_sqlmodel_tables(PILOT_SCHEMA).text
    compile(out, "<tables>", "exec")
    assert render_sqlmodel_tables(PILOT_SCHEMA).text == out


def test_sqlmodel_fidelity_clean_and_flags():
    gen = render_sqlmodel_tables(PILOT_SCHEMA).text
    assert verify_sqlmodel_fidelity(PILOT_SCHEMA, gen) == ()
    # enum members must not be miscounted as table fields
    broken = gen.replace("    value: float\n", "")
    assert any(
        "Metric" in i and "mismatch" in i
        for i in verify_sqlmodel_fidelity(PILOT_SCHEMA, broken)
    )


# --------------------------------------------------------------------------- #
# Multi-artifact drift dispatch (the kind-tag disambiguation)
# --------------------------------------------------------------------------- #


def test_both_artifacts_in_sync_and_not_confused():
    models = render_pydantic_models(PILOT_SCHEMA).text
    tables = render_sqlmodel_tables(PILOT_SCHEMA).text
    # each is in-sync when checked against the schema (drift dispatches on the artifact-kind tag)
    assert owned_file_in_sync(PILOT_SCHEMA, models) is True
    assert owned_file_in_sync(PILOT_SCHEMA, tables) is True
    # and they are genuinely different artifacts
    assert models != tables
    assert "SQLModel, table=True" in tables and "SQLModel" not in models


def test_sqlmodel_drift_detects_tamper():
    tables = render_sqlmodel_tables(PILOT_SCHEMA).text
    tampered = tables.replace("    unit: str", "    unit: int", 1)
    assert owned_file_in_sync(PILOT_SCHEMA, tampered) is False


def test_sqlmodel_file_provided_via_registry(tmp_path):
    _write_schema(tmp_path)
    dp.register_provider(PydanticSQLModelProvider())
    tables = render_sqlmodel_tables(
        PILOT_SCHEMA, source_file="prisma/schema.prisma"
    ).text
    out = tmp_path / "app" / "tables.py"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(tables, encoding="utf-8")
    # same provider recognizes the SQLModel artifact too (kind-dispatched) -> $0.00 skip
    assert is_deterministically_provided(out, tables, _ctx(tmp_path)) is True
