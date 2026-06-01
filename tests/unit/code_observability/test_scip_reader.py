"""Inc-0 reader tests (REQ-CKG-210/220) — synthetic SCIP index, no Node/binary fixture."""

from __future__ import annotations

import pytest

pytest.importorskip("google.protobuf")  # reader needs the [code-observability] extra

from startd8.code_observability import scip_pb2  # noqa: E402
from startd8.code_observability.scip_reader import ScipReader, parse_symbol  # noqa: E402

_DEF = scip_pb2.SymbolRole.Definition
_READ = scip_pb2.SymbolRole.ReadAccess

# Real external descriptors (zod, @prisma/client) as scip-typescript emits them.
_ZOD = "scip-typescript npm zod 3.25.76 v3/`types.d.cts`/ZodObject#extend()."
_PRISMA = "scip-typescript npm @prisma/client 5.22.0 `default.d.ts`/PrismaClient#"
# A project-owned symbol — also npm-managed, but DEFINED in-index, so NOT external.
_PROJ = "scip-typescript npm value-app 0.1.0 `lib/schemas.ts`/WidgetSchema."


def _occ(doc, symbol, roles=0):
    o = doc.occurrences.add()
    o.symbol = symbol
    o.symbol_roles = roles


def _index() -> scip_pb2.Index:
    idx = scip_pb2.Index()
    idx.metadata.tool_info.name = "scip-typescript"
    idx.metadata.tool_info.version = "0.4.0"

    d1 = idx.documents.add()
    d1.relative_path = "lib/schemas.ts"
    _occ(d1, _ZOD, _READ)    # external ref
    _occ(d1, _PROJ, _DEF)    # project def
    _occ(d1, "local 0")      # local (ignored)

    d2 = idx.documents.add()
    d2.relative_path = "app/api/widgets/route.ts"
    _occ(d2, _PROJ, _READ)   # cross-file ref to the project symbol
    _occ(d2, _PRISMA, _READ)  # external ref
    return idx


def _reader() -> ScipReader:
    return ScipReader.from_bytes(_index().SerializeToString())


def test_parse_symbol_global_and_local():
    ps = parse_symbol(_ZOD)
    assert ps is not None and ps.manager == "npm" and ps.package == "zod"
    assert ps.descriptor.endswith("ZodObject#extend().")
    assert parse_symbol("local 7") is None
    assert parse_symbol("") is None


def test_documents_and_tool():
    r = _reader()
    assert set(r.documents()) == {"lib/schemas.ts", "app/api/widgets/route.ts"}
    assert r.tool() == ("scip-typescript", "0.4.0")


def test_external_member_refs_excludes_project_symbols():
    r = _reader()
    by_pkg = r.external_symbols_by_package()
    # External packages surfaced via occurrences (the empty external_symbols table is NOT used).
    assert set(by_pkg) == {"zod", "@prisma/client"}
    assert any(d.endswith("ZodObject#extend().") for d in by_pkg["zod"])
    # The project's own npm symbol (defined in-index) must NOT appear as external.
    assert "value-app" not in by_pkg


def test_cross_file_edges_def_in_one_ref_in_another():
    edges = _reader().cross_file_edges()
    assert any(
        e.symbol == _PROJ and e.def_file == "lib/schemas.ts" and e.ref_file == "app/api/widgets/route.ts"
        for e in edges
    )
    # External symbols (no in-index Definition) produce no edges.
    assert all("zod" not in e.symbol and "@prisma/client" not in e.symbol for e in edges)


def test_routes_detects_app_router_handlers():
    assert _reader().routes() == ["app/api/widgets/route.ts"]
