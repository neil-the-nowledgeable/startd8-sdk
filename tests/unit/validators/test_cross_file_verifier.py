"""Inc-4: unified cross-file Verifier registry (REQ-CKG-600/235)."""

from __future__ import annotations

import json

import pytest

from startd8.validators.cross_file_verifier import run_checks


def _project(tmp_path):
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "schema.prisma").write_text(
        "model Widget {\n  id String @id\n}\n"
    )
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"zod": "3"}}))
    return str(tmp_path)


def test_availability_scip_skipped_when_absent(tmp_path):
    res = run_checks({}, _project(tmp_path), scip=None)
    assert res.availability["external_type_presence"] == "skipped_unavailable"
    # toolchain-free checks always ran (never read as PASS-by-absence, REQ-CKG-230)
    for cid in ("zod_symmetry", "unresolvable_import", "missing_dependency",
                "prisma_usage", "tsconfig_paths"):
        assert res.availability[cid] == "ran"


def test_finding_contract_fields(tmp_path):
    # tsconfig alias to a nonexistent dir -> a cross-file finding with full contract.
    root = _project(tmp_path)
    (tmp_path / "tsconfig.json").write_text(json.dumps({"compilerOptions": {"paths": {"@/*": ["./src/*"]}}}))
    res = run_checks({}, root, scip=None)
    f = next(f for f in res.findings if f.check_id == "tsconfig_paths")
    assert f.kind == "tsconfig_alias_unresolved"
    assert f.scope == "cross_file"
    assert f.severity == "error"
    assert f.locus == "@/*"
    assert f.remediation and f.message  # remediation-grade
    assert res.has_error


def test_composes_toolchain_free_findings(tmp_path):
    # missing dependency (pino) is surfaced through the unified result.
    root = _project(tmp_path)
    sources = {"a.ts": "import pino from 'pino';\n"}
    res = run_checks(sources, root, scip=None)
    assert any(f.check_id == "missing_dependency" and f.locus == "pino" for f in res.errors)


def test_clean_project_no_errors(tmp_path):
    assert run_checks({}, _project(tmp_path), scip=None).errors == []


def test_scip_backed_external_check_runs_when_index_present(tmp_path):
    scip_pb2 = pytest.importorskip("startd8.code_observability.scip_pb2")
    from startd8.code_observability.scip_reader import ScipReader

    idx = scip_pb2.Index()
    d = idx.documents.add()
    d.relative_path = "_resolved.ts"
    o = d.occurrences.add()
    o.symbol = "scip-typescript npm next 14.0.0 `server.d.ts`/NextResponse#"
    o.symbol_roles = scip_pb2.SymbolRole.ReadAccess
    scip = ScipReader.from_bytes(idx.SerializeToString())

    sources = {"next.config.ts": "import { defineConfig } from 'next';\n"}
    res = run_checks(sources, _project(tmp_path), scip=scip)
    assert res.availability["external_type_presence"] == "ran"
    assert any(f.check_id == "external_type_presence" and f.locus == "next.defineConfig"
               for f in res.errors)
