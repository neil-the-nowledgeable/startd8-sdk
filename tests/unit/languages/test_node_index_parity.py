"""Node/JS/TS structure→OTel index (FR-1..FR-6). Imports-only; analyzer owns the ESM/CJS import regex.

Spec: docs/design/REQ-crosswalk-node-structure-to-otel-comm-domains.md
Pattern: dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from startd8.languages.nodejs_parser import parse_nodejs_source
from startd8.languages.manifest_adapter import PARSER_KIND_SETS

REPO = Path(__file__).resolve().parents[3]
_GEN_PATH = REPO / "scripts" / "gen_node_structure_comm_index.py"
_PY_CROSSWALK = REPO / "docs" / "design" / "python-capability-index" / "communication-crosswalk.json"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_gen = _load(_GEN_PATH, "gen_node_structure_comm_index")
_ANALYZER = _load(REPO / "scripts" / "analyze_node_comm_coverage.py", "analyze_node_comm_coverage")
_FORMS = _gen._node_structure_forms()
_XWALK = _gen._communication_crosswalk()
_FLOOR = _gen._detectability_floor()
_COMPOSITES_DOC = _gen._language_composites()
_COMPOSITES = _COMPOSITES_DOC["composites"]
_FORM_IDS = {f["id"] for f in _FORMS}
_ACHIEVABLE = [p for p in _XWALK if not p.get("floor")]
_NODE_KINDS = PARSER_KIND_SETS["nodejs"]


def _suffix(pid): return pid.split("-OTEL-", 1)[1]


class TestL1:
    def test_forms_subset_of_parser_kinds(self):
        assert {f["parser_kind"] for f in _FORMS} <= _NODE_KINDS

    def test_every_kind_covered(self):
        assert _NODE_KINDS <= {f["parser_kind"] for f in _FORMS}

    def test_regex_emits_only_covered_kinds(self):
        src = ("import express from 'express';\nexport class Svc { h(){} }\n"
               "export function make(){}\nexport const a = ()=>{};\n"
               "export interface I { x:number }\nexport type T = string;\n")
        seen = {e.kind for e in parse_nodejs_source(src)}
        assert seen and (seen - {f["parser_kind"] for f in _FORMS}) == set()


class TestL4ParityAndImportsOnly:
    def _py(self): return json.loads(_PY_CROSSWALK.read_text(encoding="utf-8"))["patterns"]

    def test_id_suffixes_match_python(self):
        assert {_suffix(p["id"]) for p in _XWALK} == {_suffix(p["id"]) for p in self._py()}

    def test_semconv_domains_match_python(self):
        assert {p["semconv_domain"] for p in _XWALK} == {p["semconv_domain"] for p in self._py()}

    def test_exactly_15(self):
        assert len(_XWALK) == 16 == len({p["id"] for p in _XWALK})

    def test_imports_only_no_annotation_axis(self):
        # NR-2: Node is imports-only by design. No entry may carry annotation_signatures.
        for p in _XWALK:
            assert "annotation_signatures" not in p, f"{p['id']} has an annotation axis (NR-2 violated)"

    def test_every_non_floor_has_import_signature(self):
        for p in _XWALK:
            if not p.get("floor"):
                assert p.get("import_signatures"), f"{p['id']} non-floor but no import_signatures"

    def test_floor_and_resolution_pending(self):
        assert {f["id"] for f in _FLOOR} == {"NODE-OTEL-5.2-HTTP-METRICS", "NODE-OTEL-5.7-CICD"}
        assert "scip-typescript" in _gen.RESOLUTION_PENDING["unlock"]


class TestL3Composites:
    def test_no_ast_nodes_and_forms_exist(self):
        for co in _COMPOSITES:
            assert "ast_nodes" not in co
            assert all(fid in _FORM_IDS for fid in co["node_forms"])

    def test_decorator_recorded_not_witnessable(self):
        names = {n["name"] for n in _COMPOSITES_DOC["not_witnessable"]}
        assert "decorator" in names  # the Java-lesson-driven omission is documented


class TestImportExtractor:
    def test_esm_named_default_and_type(self):
        imps = _ANALYZER.extract_imports(
            "import express from 'express';\nimport { z } from 'zod';\nimport type { X } from '@scope/pkg';\n")
        assert {"express", "zod", "@scope/pkg"} <= imps

    def test_esm_bare_and_cjs(self):
        imps = _ANALYZER.extract_imports("import './side-effect';\nconst g = require('@grpc/grpc-js');\n")
        assert "./side-effect" in imps and "@grpc/grpc-js" in imps

    def test_subpath_and_scope_matching(self):
        # @modelcontextprotocol/sdk/... hits the mcp signature (reclassified out of rpc, 2026-08-15).
        h = _ANALYZER._hyp({"@modelcontextprotocol/sdk/server/index.js", "express"}, _ACHIEVABLE)
        assert "NODE-OTEL-5.3-MCP" in h and "NODE-OTEL-5.1-HTTP" in h


class TestCoverageOverFixture:
    def test_analyze_detects_and_excludes_floor(self, tmp_path):
        (tmp_path / "a.ts").write_text("import express from 'express';\nimport { pg } from 'pg';\n")
        (tmp_path / "b.mjs").write_text("import { Server } from '@modelcontextprotocol/sdk/server/index.js';\n")
        r = _ANALYZER.analyze(tmp_path)
        assert r["files_analyzed"] == 2
        assert "NODE-OTEL-5.1-HTTP" in r["detected"] and "NODE-OTEL-5.3-MCP" in r["detected"]
        floor = {f["id"] for f in _FLOOR}
        for f in r["per_file_hyp"]:
            assert floor.isdisjoint(f["hyp"])
        assert r["coverage"]["achievable_patterns"] == len(_XWALK) - len(_FLOOR)


class TestDriftGuard:
    def test_in_sync(self):
        assert _gen.main(["--check"]) == 0

    def test_index_doc_banner(self):
        md = (REPO / "docs" / "design" / _gen.INDEX_DOC).read_text(encoding="utf-8")
        assert "GENERATED by" in md and "NODE-OTEL-5.1-HTTP" in md
