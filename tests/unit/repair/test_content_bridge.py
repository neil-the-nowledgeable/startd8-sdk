"""Unit tests for the content-contract bridge + additive model field (Inc 2, FR-4)."""

from __future__ import annotations

from startd8.repair.config import RepairConfig
from startd8.repair.content_bridge import scan_results_to_diagnostics
from startd8.repair.models import MisnamedFieldDiagnostic, WrongImportPathDiagnostic
from startd8.validators.cross_file_imports import scan_unresolvable_imports
from startd8.validators.prisma_usage import scan_prisma_usage

_SCHEMA = """
model Capability {
  id          String  @id @default(cuid())
  name        String?
  category    String?
  description String?
}
"""


def _write_schema(tmp_path):
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "schema.prisma").write_text(_SCHEMA, encoding="utf-8")


def test_config_default_includes_content_contract():
    assert "content_contract" in RepairConfig().repairable_categories


def test_prisma_violation_carries_structured_model(tmp_path):
    _write_schema(tmp_path)
    sources = {
        "lib/ai/enrich.ts": "await db.capability.create({ data: { aiRefId: x, name: y } })",
    }
    violations = scan_prisma_usage(sources, str(tmp_path))
    unknown = [v for v in violations if v.kind == "prisma_unknown_field"]
    assert unknown, "expected an unknown-field violation for aiRefId"
    assert unknown[0].field == "aiRefId"
    assert unknown[0].model == "Capability"  # additive structured field


def test_bridge_produces_misnamed_field_diagnostic(tmp_path):
    _write_schema(tmp_path)
    sources = {
        "lib/ai/enrich.ts": "await db.capability.create({ data: { aiRefId: x } })",
    }
    diags = scan_results_to_diagnostics(scan_prisma_usage(sources, str(tmp_path)), [])
    field_diags = [d for d in diags if isinstance(d, MisnamedFieldDiagnostic)]
    assert len(field_diags) == 1
    d = field_diags[0]
    assert d.category == "content_contract"
    assert d.field == "aiRefId"
    assert d.model == "Capability"
    assert d.file == "lib/ai/enrich.ts"


def test_bridge_produces_wrong_import_path_diagnostic(tmp_path):
    sources = {
        "lib/ai/enrich.ts": "import { db } from '@/lib/prisma'\n",
    }
    import_violations = scan_unresolvable_imports(sources, str(tmp_path))
    diags = scan_results_to_diagnostics([], import_violations)
    path_diags = [d for d in diags if isinstance(d, WrongImportPathDiagnostic)]
    assert len(path_diags) == 1
    assert path_diags[0].specifier == "@/lib/prisma"
    assert path_diags[0].category == "content_contract"


def test_bridge_ignores_out_of_scope_kinds(tmp_path):
    _write_schema(tmp_path)
    # A where-not-unique violation must NOT be bridged into the rename pipeline.
    sources = {
        "lib/x.ts": "await db.capability.findUnique({ where: { name: 'x' } })",
    }
    violations = scan_prisma_usage(sources, str(tmp_path))
    # name IS a field but not unique -> prisma_where_not_unique, out of v1 scope.
    assert any(v.kind == "prisma_where_not_unique" for v in violations)
    diags = scan_results_to_diagnostics(violations, [])
    assert diags == []
