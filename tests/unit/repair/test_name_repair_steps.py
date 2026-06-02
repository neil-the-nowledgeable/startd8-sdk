"""Unit tests for the two name-repair steps + routing (Inc 4, FR-5/FR-6)."""

from __future__ import annotations

from pathlib import Path

from startd8.repair.config import RepairConfig
from startd8.repair.models import (
    MisnamedFieldDiagnostic,
    RepairContext,
    WrongImportPathDiagnostic,
)
from startd8.repair.routing import route_failures
from startd8.repair.steps.import_path_rename import ImportPathRenameStep
from startd8.repair.steps.prisma_field_rename import PrismaFieldRenameStep


class StubTruthSource:
    """In-memory truth source for deterministic step tests."""

    def __init__(self, fields=None, negatives=None, resolvable=None):
        self._fields = fields or {}
        self._negatives = negatives or {}
        self._resolvable = frozenset(resolvable or ())

    def prisma_fields(self, model):
        return frozenset(self._fields.get(model, ()))

    def module_paths(self):
        return dict(self._negatives)

    def resolvable_specifiers(self):
        return self._resolvable


_DIFF_FIELDS = {"Differentiator": ["id", "name", "category", "description", "evidence", "notes"]}
_CAP_FIELDS = {"Capability": ["id", "name", "category", "description"]}
_METRIC_FIELDS = {"Metric": ["id", "name", "value", "unit", "timeframe", "description"]}


def _ctx(diags, project_root=None):
    return RepairContext(diagnostics=diags, project_root=Path(project_root or "."))


# ── prisma_field_rename ─────────────────────────────────────────────────────

def test_field_rename_rewrites_near_match():
    code = "await db.differentiator.create({ data: { supportingEvidence: ev, name: n } })\n"
    diag = MisnamedFieldDiagnostic(category="content_contract", message="", file="lib/d.ts",
                                   field="supportingEvidence", model="Differentiator")
    step = PrismaFieldRenameStep(StubTruthSource(fields=_DIFF_FIELDS))
    res = step(code, _ctx([diag]), Path("lib/d.ts"))
    assert res.modified
    assert "evidence: ev" in res.code
    assert "supportingEvidence" not in res.code
    assert res.metrics["rewrites"][0]["to"] == "evidence"


def test_field_rename_abstains_on_synonym():
    code = "await db.differentiator.create({ data: { title: t } })\n"
    diag = MisnamedFieldDiagnostic(category="content_contract", message="", file="lib/d.ts",
                                   field="title", model="Differentiator")
    res = PrismaFieldRenameStep(StubTruthSource(fields=_DIFF_FIELDS))(code, _ctx([diag]), Path("lib/d.ts"))
    assert not res.modified
    assert res.code == code
    assert res.metrics["abstains"][0]["reason"] == "no_candidates"


def test_field_rename_abstains_on_structural_fk():
    code = "await db.metric.create({ data: { outcomeId: o, name: n } })\n"
    diag = MisnamedFieldDiagnostic(category="content_contract", message="", file="lib/m.ts",
                                   field="outcomeId", model="Metric")
    res = PrismaFieldRenameStep(StubTruthSource(fields=_METRIC_FIELDS))(code, _ctx([diag]), Path("lib/m.ts"))
    assert not res.modified
    assert res.metrics["abstains"][0]["reason"] == "no_candidates"


def test_field_rename_never_touches_nested_key():
    # `descriptio` would rewrite if top-level, but here it is nested -> abstain.
    code = "await db.capability.create({ data: { nested: { descriptio: x } } })\n"
    diag = MisnamedFieldDiagnostic(category="content_contract", message="", file="lib/c.ts",
                                   field="descriptio", model="Capability")
    res = PrismaFieldRenameStep(StubTruthSource(fields=_CAP_FIELDS))(code, _ctx([diag]), Path("lib/c.ts"))
    assert not res.modified
    assert res.code == code
    assert res.metrics["abstains"][0]["reason"] == "unbounded_construct"


def test_field_rename_multi_model_binds_per_call_site():
    # descriptio on Capability must rewrite against Capability only; Metric.name untouched.
    code = (
        "await db.capability.create({ data: { descriptio: a } });\n"
        "await db.metric.update({ where: { id }, data: { name: b } });\n"
    )
    diag = MisnamedFieldDiagnostic(category="content_contract", message="", file="lib/x.ts",
                                   field="descriptio", model="Capability")
    ts = StubTruthSource(fields={**_CAP_FIELDS, **_METRIC_FIELDS})
    res = PrismaFieldRenameStep(ts)(code, _ctx([diag]), Path("lib/x.ts"))
    assert "db.capability.create({ data: { description: a } })" in res.code
    assert "db.metric.update({ where: { id }, data: { name: b } })" in res.code


def test_field_rename_matches_prisma_client_prefix():
    """The rewriter must match the same `db.`/`prisma.` prefixes the detector flags."""
    code = "await prisma.capability.create({ data: { descriptio: a } })\n"
    diag = MisnamedFieldDiagnostic(category="content_contract", message="", file="lib/x.ts",
                                   field="descriptio", model="Capability")
    res = PrismaFieldRenameStep(StubTruthSource(fields=_CAP_FIELDS))(code, _ctx([diag]), Path("lib/x.ts"))
    assert res.modified
    assert "prisma.capability.create({ data: { description: a } })" in res.code


def test_field_rename_is_idempotent():
    code = "await db.capability.create({ data: { descriptio: a } })\n"
    diag = MisnamedFieldDiagnostic(category="content_contract", message="", file="lib/x.ts",
                                   field="descriptio", model="Capability")
    step = PrismaFieldRenameStep(StubTruthSource(fields=_CAP_FIELDS))
    once = step(code, _ctx([diag]), Path("lib/x.ts"))
    twice = step(once.code, _ctx([diag]), Path("lib/x.ts"))
    assert once.modified and not twice.modified


# ── import_path_rename ──────────────────────────────────────────────────────

_RESOLVABLE = ["@/lib/db", "@/lib/logger", "@/lib/ai/service", "@/lib/value-model"]
_NEGATIVES = {"@/lib/prisma": "@/lib/db", "@/lib/ai/client": "@/lib/ai/service"}


def _import_ctx():
    return _ctx([])  # diagnostics supplied per-test


def test_import_rename_seeded_negative():
    code = "import { db } from '@/lib/prisma'\n"
    diag = WrongImportPathDiagnostic(category="content_contract", message="", file="lib/x.ts", specifier="@/lib/prisma")
    ts = StubTruthSource(negatives=_NEGATIVES, resolvable=_RESOLVABLE)
    res = ImportPathRenameStep(ts)(code, _ctx([diag]), Path("lib/x.ts"))
    assert "from '@/lib/db'" in res.code
    assert "@/lib/prisma" not in res.code


def test_import_rename_subpath_collapse():
    code = "import { caps } from '@/lib/db/capabilities'\n"
    diag = WrongImportPathDiagnostic(category="content_contract", message="", file="lib/x.ts",
                                     specifier="@/lib/db/capabilities")
    ts = StubTruthSource(negatives=_NEGATIVES, resolvable=_RESOLVABLE)
    res = ImportPathRenameStep(ts)(code, _ctx([diag]), Path("lib/x.ts"))
    assert "from '@/lib/db'" in res.code


def test_import_rename_typo_nearest_match():
    code = "import { log } from '@/lib/loggr'\n"
    diag = WrongImportPathDiagnostic(category="content_contract", message="", file="lib/x.ts", specifier="@/lib/loggr")
    ts = StubTruthSource(negatives=_NEGATIVES, resolvable=_RESOLVABLE)
    res = ImportPathRenameStep(ts)(code, _ctx([diag]), Path("lib/x.ts"))
    assert "from '@/lib/logger'" in res.code


def test_import_rename_only_touches_import_positions():
    """Bug fix: a specifier in a string literal/comment must NOT be rewritten."""
    code = (
        "import { db } from '@/lib/prisma'\n"
        "const note = \"see '@/lib/prisma' for details\"\n"
        "// also '@/lib/prisma' in a comment\n"
        "export { x } from '@/lib/prisma'\n"
    )
    diag = WrongImportPathDiagnostic(category="content_contract", message="", file="lib/x.ts", specifier="@/lib/prisma")
    ts = StubTruthSource(negatives=_NEGATIVES, resolvable=_RESOLVABLE)
    res = ImportPathRenameStep(ts)(code, _ctx([diag]), Path("lib/x.ts"))
    # The import and the export-from are rewritten:
    assert "import { db } from '@/lib/db'" in res.code
    assert "export { x } from '@/lib/db'" in res.code
    # The string literal and comment are untouched:
    assert "const note = \"see '@/lib/prisma' for details\"" in res.code
    assert "// also '@/lib/prisma' in a comment" in res.code


def test_import_rename_handles_require_and_dynamic_import():
    code = "const m = require('@/lib/prisma'); const d = import('@/lib/prisma');\n"
    diag = WrongImportPathDiagnostic(category="content_contract", message="", file="lib/x.ts", specifier="@/lib/prisma")
    ts = StubTruthSource(negatives=_NEGATIVES, resolvable=_RESOLVABLE)
    res = ImportPathRenameStep(ts)(code, _ctx([diag]), Path("lib/x.ts"))
    assert "require('@/lib/db')" in res.code
    assert "import('@/lib/db')" in res.code
    assert "@/lib/prisma" not in res.code


def test_import_rename_abstains_when_no_candidate():
    code = "import { z } from '@/lib/totallyunrelatedxyz'\n"
    diag = WrongImportPathDiagnostic(category="content_contract", message="", file="lib/x.ts",
                                     specifier="@/lib/totallyunrelatedxyz")
    ts = StubTruthSource(negatives=_NEGATIVES, resolvable=_RESOLVABLE)
    res = ImportPathRenameStep(ts)(code, _ctx([diag]), Path("lib/x.ts"))
    assert not res.modified
    assert res.code == code


# ── routing ─────────────────────────────────────────────────────────────────

def test_routing_content_contract_returns_name_repair_steps():
    diag = MisnamedFieldDiagnostic(category="content_contract", message="", file="lib/x.ts",
                                   field="aiRefId", model="Capability")
    route = route_failures([diag], RepairConfig(), language_id="nodejs")
    assert "prisma_field_rename" in route.steps
    assert "import_path_rename" in route.steps
    # canonical order: rename steps precede the JS syntax gate
    assert route.steps.index("prisma_field_rename") < route.steps.index("js_syntax_validate")


def test_routing_skips_content_contract_when_category_disabled():
    cfg = RepairConfig(repairable_categories=frozenset({"syntax", "import"}))
    diag = WrongImportPathDiagnostic(category="content_contract", message="", file="lib/x.ts", specifier="@/lib/prisma")
    route = route_failures([diag], cfg, language_id="nodejs")
    assert route.steps == []
