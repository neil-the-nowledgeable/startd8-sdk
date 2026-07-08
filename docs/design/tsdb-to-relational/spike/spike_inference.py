#!/usr/bin/env python3
"""SPIKE — M2 inference core → michigan golden (rung 3 de-risk).

Proves the load-bearing claim: a minimal TSDB-schema inference (type + identity +
bookkeeping-collision rename + direct EntityGraph) reproduces michigan's hand-authored
`department_budgets` schema when fed a faithful specimen of that metric's labels.

Reuses the REAL SDK back-half verbatim: manifest_extraction.entities (EntityGraph/DocEntity/
DocField), manifest_extraction.prisma_emitter (render_prisma_schema, _BOOKKEEPING),
languages.prisma_parser (parse_prisma_schema) — the emitter is not re-implemented.

Run:  PYTHONPATH=src .venv/bin/python docs/design/tsdb-to-relational/spike/spike_inference.py
Exit 0 = all golden assertions pass.
"""
from __future__ import annotations

import re
import sys
from decimal import Decimal, InvalidOperation
from itertools import combinations

from startd8.manifest_extraction.entities import DocField, DocEntity, EntityGraph
from startd8.manifest_extraction.prisma_emitter import render_prisma_schema, _BOOKKEEPING
from startd8.languages.prisma_parser import parse_prisma_schema

RESERVED = {name for name, _ in _BOOKKEEPING}  # id, ownerId, source, confirmed, createdAt, updatedAt
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T")


# --------------------------------------------------------------------------- #
# 1. A faithful specimen of the michigan `gov_expenditure_amount` labels        #
#    (export_to_supabase.py:99-113). Full-factorial over the 5 INDEPENDENT key  #
#    dims so the golden 5-col subset is genuinely *minimal*-unique (no smaller   #
#    subset is unique) — the honest test, not a rigged one.                      #
# --------------------------------------------------------------------------- #
DEPTS = [("corrections", "Corrections"), ("health_human_services", "Health & Human Services")]
FYS = ["2025", "2026"]
STATUSES = ["enacted", "proposed"]
COMPLETES = ["enacted_appropriations", "proposed_appropriations"]
FUNDS = [("general_fund", "General Fund/General Purpose"), ("federal", "Federal")]
LABELS = ["department", "department_display", "fiscal_year", "budget_status",
          "data_completeness", "fund_source", "fund_source_display", "source"]
# The michigan ground-truth key (CONFLICT_COLUMNS["department_budgets"], export_to_supabase.py:483):
GOLDEN_KEY = ["department", "fiscal_year", "budget_status", "fund_source", "data_completeness"]


def build_specimen():
    rows, v = [], 1_000_000.0
    for dept, dept_disp in DEPTS:
        for fy in FYS:
            for status in STATUSES:
                for comp in COMPLETES:
                    for fund, fund_disp in FUNDS:
                        rows.append({
                            "department": dept, "department_display": dept_disp,
                            "fiscal_year": fy, "budget_status": status,
                            "data_completeness": comp, "fund_source": fund,
                            "fund_source_display": fund_disp, "source": "hfa_mi",
                            "value": round(v, 2),  # the metric value → the measure
                        })
                        v += 1234.56
    return rows


# --------------------------------------------------------------------------- #
# 2. Inference primitives (the rung-3 novelty — the real thing to prove)        #
# --------------------------------------------------------------------------- #
def infer_scalar_type(values) -> str:
    """FR-3: type a column by inspecting its (string) values. Enums OFF (OQ-10)."""
    vals = [str(v) for v in values if v not in (None, "")]
    if not vals:
        return "String"
    if all(re.fullmatch(r"-?\d+", v) for v in vals):
        return "Int"

    def _is_dec(v: str) -> bool:
        try:
            Decimal(v)
            return True
        except InvalidOperation:
            return False

    if all(_is_dec(v) for v in vals) and any("." in v for v in vals):
        return "Decimal"          # OQ-9: financial measure → Decimal
    if all(_ISO.match(v) for v in vals):
        return "DateTime"
    return "String"


def camel(snake: str) -> str:
    parts = snake.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def is_display_column(col: str, all_cols) -> bool:
    """R1-F2: a `x_display` column whose slug sibling `x` exists is a dimension, never key-eligible."""
    return col.endswith("_display") and col[: -len("_display")] in all_cols


def rename_if_reserved(col: str) -> str:
    """R1-F11/F10: rename a label colliding with the emitter's bookkeeping set; collision-check the rename."""
    cc = camel(col)
    if cc in RESERVED:
        renamed = "data" + cc[:1].upper() + cc[1:]   # source -> dataSource
        if renamed in RESERVED:                       # R1-F10: the rename must not itself re-collide
            raise ValueError(f"rename target {renamed!r} also reserved")
        return renamed
    return cc


def infer_identity(specimen, labels, golden=None):
    """FR-4: minimal label subset unique per (raw) series. Deterministic tie-break (R1-F1);
    exclude display columns (R1-F2). Reads the RAW specimen (R1-F9)."""
    n = len(specimen)
    cands = [c for c in labels if not is_display_column(c, labels)]
    for size in range(1, len(cands) + 1):
        unique = [combo for combo in combinations(cands, size)
                  if len({tuple(r[c] for c in combo) for r in specimen}) == n]
        if not unique:
            continue
        if golden:                                   # R1-F1 tie-break (a): match the golden if supplied
            gset = set(golden)
            for combo in unique:
                if set(combo) == gset:
                    return list(combo)
        return sorted(unique, key=lambda s: sorted(s))[0]  # (b): lexicographic
    return cands


# --------------------------------------------------------------------------- #
# 3. Build the EntityGraph DIRECTLY (the graph_from_prisma way, NOT extract_    #
#    entities) and render via the real emitter.                                 #
# --------------------------------------------------------------------------- #
def infer_and_render(specimen, metric_measure_name="amount"):
    col_type = {c: infer_scalar_type([r[c] for r in specimen]) for c in LABELS}
    colmap = {c: rename_if_reserved(c) for c in LABELS}   # label -> emitted field name

    fields = []
    for i, c in enumerate(LABELS):
        fields.append(DocField(name=colmap[c], plain_type=col_type[c], prisma_type=col_type[c],
                               required=True, notes="", human_only=False, row_index=i))
    # the metric VALUE → a measure column
    measure_type = infer_scalar_type([r["value"] for r in specimen])
    fields.append(DocField(name=metric_measure_name, plain_type=measure_type, prisma_type=measure_type,
                           required=True, notes="", human_only=False, row_index=len(LABELS)))
    # observed_at — the one added TSDB-specific field (FR-3)
    fields.append(DocField(name="observedAt", plain_type="DateTime", prisma_type="DateTime",
                           required=True, notes="", human_only=False, row_index=len(LABELS) + 1))

    graph = EntityGraph()
    graph.entities["DepartmentBudget"] = DocEntity(
        name="DepartmentBudget", fields=tuple(fields), heading_path=())

    id_cols = infer_identity(specimen, LABELS, golden=GOLDEN_KEY)
    id_emitted = tuple(colmap[c] for c in id_cols)
    graph.uniques["DepartmentBudget"] = [id_emitted]

    return render_prisma_schema(graph), id_cols, id_emitted, colmap


# --------------------------------------------------------------------------- #
# 4. Golden assertions (the department_budgets DDL is the ground truth)          #
# --------------------------------------------------------------------------- #
def main() -> int:
    specimen = build_specimen()
    result, id_cols, id_emitted, colmap = infer_and_render(specimen)

    print("=" * 70)
    print(f"specimen: {len(specimen)} rows (full-factorial 2x2x2x2x2)")
    print(f"inferred identity (raw labels): {id_cols}")
    print(f"inferred identity (emitted):    {list(id_emitted)}")
    print("=" * 70)
    print(result.text)
    print("=" * 70)

    checks = []

    def check(name, cond, detail=""):
        checks.append((name, bool(cond), detail))

    # No structural errors → proves the source->dataSource rename dodged the bookkeeping collision
    check("no emitter errors (source-collision dodged)", result.errors == (),
          f"errors={result.errors}")
    check("no unrenderable fields", result.unrenderable == (),
          f"unrenderable={result.unrenderable}")

    parsed = parse_prisma_schema(result.text)
    m = parsed.model("DepartmentBudget")
    check("model DepartmentBudget emitted", m is not None)

    if m:
        def ftype(fn):
            f = m.field(fn)
            return f.type if f else None

        # Type golden: fiscal_year SMALLINT->Int, amount NUMERIC->Decimal, slugs TEXT->String
        check("fiscalYear : Int      (golden SMALLINT)", ftype("fiscalYear") == "Int", ftype("fiscalYear"))
        check("amount     : Decimal  (golden NUMERIC)", ftype("amount") == "Decimal", ftype("amount"))
        check("department : String   (golden TEXT)", ftype("department") == "String", ftype("department"))
        check("budgetStatus : String (golden TEXT, enums OFF)", ftype("budgetStatus") == "String",
              ftype("budgetStatus"))
        # Rename golden: `source` label -> dataSource; NO bare `source` label field collision
        check("dataSource present (renamed label)", ftype("dataSource") == "String", ftype("dataSource"))
        # bookkeeping still injected (emitter-owned)
        check("bookkeeping id present", m.field("id") is not None)
        check("bookkeeping source present (@default, not the label)", m.field("source") is not None)
        # observed_at added
        check("observedAt : DateTime", ftype("observedAt") == "DateTime", ftype("observedAt"))

        # Identity golden: the 5-col composite @@unique, exactly michigan CONFLICT_COLUMNS (camelCased)
        expected_key = {camel(c) for c in GOLDEN_KEY}
        block = " ".join(m.block_attributes)
        uniq_cols = set(re.findall(r"@@unique\(\[([^\]]*)\]", block))
        got = set()
        for grp in uniq_cols:
            got |= {c.strip() for c in grp.split(",")}
        check("composite @@unique == golden 5-col key",
              got == expected_key and set(camel(c) for c in id_cols) == expected_key,
              f"got={sorted(got)} expected={sorted(expected_key)}")

    print("\nGOLDEN ASSERTIONS")
    print("-" * 70)
    all_pass = True
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        line = f"  [{mark}] {name}"
        if detail and not ok:
            line += f"   ({detail})"
        print(line)
    print("-" * 70)
    print("VERDICT:", "GREEN — inference reproduces the michigan golden" if all_pass
          else "RED — divergences above")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
