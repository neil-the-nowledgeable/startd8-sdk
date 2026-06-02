"""Inc 5 — strtd8 acceptance gate (FR-9, the headline).

Regenerates the Zod schema from the **real** strtd8 `prisma/schema.prisma` (committed as a
fixture) and proves:

1. By construction — the render passes both gates (symmetry + fidelity) with zero violations.
2. Coverage — one schema + one `z.infer` alias per model (join tables included); the composite
   `ValueModelSchema` is NOT generated (out of v1 scope).
3. Equivalence — on every model the committed `value-model.ts` covers, the render reproduces
   each field's exact Zod expression.
4. **Drift caught** (the real payoff) — the committed hand-authored file is *stale*: it omits
   `Artifact.dataJson` and three whole models the schema has since grown. The deterministic
   render includes them — i.e. it is provably MORE correct than the file the LLM produced.
5. RUN-011 — `outcomeId` is a real column on the join models but is **per-model impossible**
   to invent onto `OutcomeSchema`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.frontend_codegen import (
    assert_symmetric,
    render_zod_schema,
    verify_render_fidelity,
)
from startd8.frontend_codegen.gates import _extract_field_exprs
from startd8.languages.prisma_parser import parse_prisma_schema

pytestmark = pytest.mark.unit

_FIX = Path(__file__).parent / "fixtures"
SCHEMA = (_FIX / "strtd8_schema.prisma").read_text(encoding="utf-8")
COMMITTED = (_FIX / "strtd8_value-model.ts").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# 1. By construction — both gates clean
# --------------------------------------------------------------------------- #


def test_render_passes_symmetry_gate():
    rendered = render_zod_schema(SCHEMA).text
    assert assert_symmetric(rendered, SCHEMA) == []


def test_render_passes_fidelity_gate():
    rendered = render_zod_schema(SCHEMA).text
    assert verify_render_fidelity(rendered, SCHEMA) == []


def test_render_has_no_unrenderable_fields():
    assert render_zod_schema(SCHEMA).unrenderable == ()


# --------------------------------------------------------------------------- #
# 2. Coverage — one schema + one alias per model; composite excluded
# --------------------------------------------------------------------------- #


def test_one_schema_and_alias_per_model():
    r = render_zod_schema(SCHEMA)
    schema = parse_prisma_schema(SCHEMA)
    assert len(schema.models) == 15
    for name in schema.models:
        assert f"export const {name}Schema = z.object({{" in r.text
        assert f"export type {name} = z.infer<typeof {name}Schema>;" in r.text


def test_join_tables_are_rendered():
    r = render_zod_schema(SCHEMA).text
    for jt in ("ProofPointCapability", "ProofPointOutcome", "CapabilityOutcome"):
        assert f"export const {jt}Schema = z.object({{" in r


def test_composite_value_model_schema_not_generated():
    # The cross-model aggregate is not derivable from a single model — out of v1 scope.
    r = render_zod_schema(SCHEMA).text
    assert "ValueModelSchema = z.object" not in r
    assert "ValueModel" not in _extract_field_exprs(r)


# --------------------------------------------------------------------------- #
# 3. Equivalence on the shared surface — exact expression match
# --------------------------------------------------------------------------- #


def test_reproduces_committed_shared_models_expression_for_expression():
    mine = _extract_field_exprs(render_zod_schema(SCHEMA).text)
    committed = _extract_field_exprs(COMMITTED)
    for entity, fields in committed.items():
        if entity == "ValueModel":  # composite, handled above
            continue
        assert entity in mine, f"{entity} absent from render"
        mine_fields = dict(mine[entity])
        for fname, expr in fields:
            assert fname in mine_fields, f"{entity}.{fname} absent from render"
            assert (
                mine_fields[fname] == expr
            ), f"{entity}.{fname}: render '{mine_fields[fname]}' != committed '{expr}'"


# --------------------------------------------------------------------------- #
# 4. Drift caught — the deterministic render is MORE correct than the stale file
# --------------------------------------------------------------------------- #


def test_render_includes_dropped_column_the_committed_file_omits():
    # Artifact.dataJson is in the schema but missing from the committed (LLM-authored) file.
    mine = _extract_field_exprs(render_zod_schema(SCHEMA).text)
    committed = _extract_field_exprs(COMMITTED)
    assert "dataJson" in dict(mine["Artifact"])
    assert "dataJson" not in dict(committed["Artifact"])


def test_render_includes_models_the_committed_file_never_added():
    # The schema grew three models the committed file never picked up (staleness, FR-11).
    mine = _extract_field_exprs(render_zod_schema(SCHEMA).text)
    committed = _extract_field_exprs(COMMITTED)
    for grown in ("JobDescription", "TailoredMatch", "TailoredAsset"):
        assert grown in mine
        assert grown not in committed


# --------------------------------------------------------------------------- #
# 5. RUN-011 — per-model invention impossibility
# --------------------------------------------------------------------------- #


def test_outcome_id_is_per_model_not_global():
    mine = _extract_field_exprs(render_zod_schema(SCHEMA).text)
    # Real columns on the join models...
    assert "outcomeId" in dict(mine["ProofPointOutcome"])
    assert "outcomeId" in dict(mine["CapabilityOutcome"])
    # ...but impossible on OutcomeSchema (the RUN-011 invention).
    assert "outcomeId" not in dict(mine["Outcome"])
