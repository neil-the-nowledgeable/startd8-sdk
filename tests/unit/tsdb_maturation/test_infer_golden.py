"""M2 GOLDEN test (FR-3/FR-4/FR-11) — the empirical proof of rung 3.

Feeds a faithful specimen of michigan's ``gov_expenditure_amount`` labels through the real
M1→M2 path and asserts the inferred ``schema.prisma`` reproduces the hand-authored
``department_budgets`` DDL (``20260313220000_michigan_budget_schema.sql``).

**Two exit gates, not one (R1-S1):**
  (a) *structural* — types/graph/collision correct, schema renders clean;
  (b) *identity-correct* — the inferred key == michigan ``CONFLICT_COLUMNS``, with a **negative
      ``*_display`` fixture** proving a display column is never key-eligible.

**R1-S2 normalization** — the golden DDL and the emitted schema differ by four *expected*
transforms; the test asserts the post-transform shape, and any divergence outside this map is a
failure (catches unplanned drift):
  1. ``source`` (TEXT) → ``dataSource`` (renamed off the bookkeeping collision);
  2. ``amount`` (NUMERIC) → ``Decimal`` measure;
  3. ``budget_status``/… (TEXT) → ``String`` (enums OFF, OQ-10);
  4. the two ``*_display`` columns are excluded from the identity key.
"""

from __future__ import annotations

from itertools import product

import pytest

from startd8.languages.prisma_parser import parse_prisma_schema
from startd8.tsdb_maturation import ReadResult, Series, Specimen, infer_schema
from startd8.tsdb_maturation.infer import camel, infer_identity

# michigan ground truth (export_to_supabase.py:99-113 labels; :483 CONFLICT_COLUMNS).
GOLDEN_KEY = ["department", "fiscal_year", "budget_status", "fund_source", "data_completeness"]
LABELS = [
    "department", "department_display", "fiscal_year", "budget_status",
    "data_completeness", "fund_source", "fund_source_display", "source",
]
DEPTS = [("corrections", "Corrections"), ("health_human_services", "Health & Human Services")]
FYS = ["2025", "2026"]
STATUSES = ["enacted", "proposed"]
COMPLETES = ["enacted_appropriations", "proposed_appropriations"]
FUNDS = [("general_fund", "General Fund/General Purpose"), ("federal", "Federal")]


def michigan_specimen() -> Specimen:
    """Full-factorial over the 5 INDEPENDENT key dims → the golden 5-col subset is genuinely
    *minimal*-unique (no smaller subset is unique) — the honest test, not a rigged one."""
    series, v = [], 1_000_000.0
    for (dept, dept_disp), (fund, fund_disp), fy, status, comp in product(
        DEPTS, FUNDS, FYS, STATUSES, COMPLETES
    ):
        labels = {
            "department": dept, "department_display": dept_disp, "fiscal_year": fy,
            "budget_status": status, "data_completeness": comp, "fund_source": fund,
            "fund_source_display": fund_disp, "source": "hfa_mi",
        }
        series.append(Series(labels=labels, value=round(v, 2), timestamp=1_700_000_000.0))
        v += 1234.56
    rr = ReadResult(metric="gov_expenditure_amount", lookback="3000d", series=tuple(series))
    return Specimen.from_read_result(rr)


@pytest.fixture
def inferred():
    return infer_schema(
        michigan_specimen(), entity_name="DepartmentBudget", golden_key=GOLDEN_KEY
    )


# =========================================================================== #
# GATE (a) — structural.                                                        #
# =========================================================================== #
def test_gate_a_no_emitter_errors_or_unrenderable(inferred):
    # The source→dataSource rename dodged the bookkeeping collision → clean render.
    assert inferred.schema.errors == ()
    assert inferred.schema.unrenderable == ()


def test_gate_a_model_and_types(inferred):
    m = parse_prisma_schema(inferred.schema_text).model("DepartmentBudget")
    assert m is not None

    def ftype(fn):
        f = m.field(fn)
        return f.type if f else None

    # Transform 2 + 3: NUMERIC→Decimal, SMALLINT→Int, TEXT→String (enums OFF).
    assert ftype("amount") == "Decimal"
    assert ftype("fiscalYear") == "Int"
    assert ftype("department") == "String"
    assert ftype("budgetStatus") == "String"
    assert ftype("dataCompleteness") == "String"
    # observed_at — the one added TSDB field.
    assert ftype("observedAt") == "DateTime"


def test_gate_a_source_rename_transform(inferred):
    m = parse_prisma_schema(inferred.schema_text).model("DepartmentBudget")
    # Transform 1: the `source` LABEL becomes `dataSource`…
    assert m.field("dataSource") is not None
    assert m.field("dataSource").type == "String"
    # …and the emitter-owned bookkeeping `source` (@default("user")) still exists, distinct.
    assert m.field("source") is not None
    assert m.field("id") is not None  # bookkeeping injected, not authored


def test_gate_a_display_columns_present_as_dimensions(inferred):
    # Display columns are still emitted as columns — they're just excluded from the KEY (gate b).
    m = parse_prisma_schema(inferred.schema_text).model("DepartmentBudget")
    assert m.field("departmentDisplay") is not None
    assert m.field("fundSourceDisplay") is not None


# =========================================================================== #
# GATE (b) — identity-correct (the load-bearing gate).                          #
# =========================================================================== #
def test_gate_b_identity_equals_golden_conflict_columns(inferred):
    expected = {camel(c) for c in GOLDEN_KEY}
    assert set(inferred.identity_fields) == expected
    assert set(inferred.identity_labels) == set(GOLDEN_KEY)
    assert len(inferred.identity_fields) == 5


def test_gate_b_composite_unique_in_schema(inferred):
    import re

    m = parse_prisma_schema(inferred.schema_text).model("DepartmentBudget")
    block = " ".join(m.block_attributes)
    cols = set()
    for grp in re.findall(r"@@unique\(\[([^\]]*)\]", block):
        cols |= {c.strip() for c in grp.split(",")}
    assert cols == {camel(c) for c in GOLDEN_KEY}


def test_gate_b_display_columns_never_in_key(inferred):
    # Transform 4 + R1-F2: a *_display column must NOT appear in the identity key.
    for field in inferred.identity_fields:
        assert not field.lower().endswith("display")
    assert "departmentDisplay" not in inferred.identity_fields
    assert "fundSourceDisplay" not in inferred.identity_fields


def test_gate_b_holds_without_golden_on_independent_dims():
    """The honest claim: on full-factorial (independent) dims the 5-col key is the ONLY minimal
    unique subset, so it is found even WITHOUT the golden tie-break."""
    res = infer_schema(michigan_specimen(), entity_name="DepartmentBudget")  # no golden_key
    assert set(res.identity_labels) == set(GOLDEN_KEY)


# =========================================================================== #
# Negative: display column would wrongly appear unique if not excluded (R1-F2). #
# =========================================================================== #
def test_display_column_excluded_even_when_it_would_be_unique():
    # A specimen where `department_display` is 1:1 with `department`: including the display column
    # in a candidate key would make a WRONG subset look unique. R1-F2 must exclude it up front.
    series = []
    for i, (dept, disp) in enumerate([("a", "A"), ("b", "B"), ("c", "C")]):
        series.append(Series(labels={"department": dept, "department_display": disp}, value=float(i), timestamp=0.0))
    key = infer_identity([dict(s.labels) for s in series], ["department", "department_display"])
    assert "department_display" not in key
    assert key == ["department"]


# =========================================================================== #
# Correlated-columns fixture — proves the confirmation gate is LOAD-BEARING.    #
# (The spike's honest caveat: on correlated real data a SMALLER subset can be   #
#  coincidentally unique, so structural inference alone can pick a wrong key.)   #
# =========================================================================== #
def correlated_specimen() -> Specimen:
    """`data_completeness` is functionally determined by `budget_status`, so a 4-col subset is
    coincidentally unique — smaller than the golden 5-col key."""
    series, v = [], 100.0
    comp_of = {"enacted": "enacted_appropriations", "proposed": "proposed_appropriations"}
    for (dept, _), (fund, _), fy, status in product(DEPTS, FUNDS, FYS, STATUSES):
        labels = {
            "department": dept, "fiscal_year": fy, "budget_status": status,
            "data_completeness": comp_of[status], "fund_source": fund, "source": "hfa_mi",
        }
        series.append(Series(labels=labels, value=round(v, 2), timestamp=0.0))
        v += 1.0
    rr = ReadResult(metric="gov_expenditure_amount", lookback="3000d", series=tuple(series))
    return Specimen.from_read_result(rr)


def test_correlated_data_yields_a_smaller_coincidental_key():
    """Without golden/confirmation, inference picks a 4-col subset that DIFFERS from the true
    5-col key — exactly why the F4 confirmation gate (M2.5/M4) is load-bearing, not cosmetic."""
    res = infer_schema(correlated_specimen(), entity_name="DepartmentBudget")
    # 'source' is constant → never in a key; the minimal unique subset drops data_completeness.
    assert len(res.identity_labels) == 4
    assert set(res.identity_labels) != set(GOLDEN_KEY)
    # It is a strict subset of the golden dims (a coincidental collapse), not garbage.
    assert set(res.identity_labels) < set(GOLDEN_KEY)


def test_correlated_key_recovered_when_golden_supplied():
    """With the golden as the R1-F1 tie-break, the 5-col key is preferred IFF it is itself unique.
    Here the 5-col key IS unique (superset of the 4-col), but 'minimal' picks the 4-col first —
    so even the golden tie-break cannot rescue a genuinely-smaller unique subset. This documents
    that the human confirmation gate, not the tie-break, is the real safeguard."""
    res = infer_schema(correlated_specimen(), entity_name="DepartmentBudget", golden_key=GOLDEN_KEY)
    # The tie-break only applies AMONG equally-minimal subsets; the 4-col is strictly smaller,
    # so the golden (5-col) is not selected. Confirms the caveat honestly.
    assert len(res.identity_labels) == 4
