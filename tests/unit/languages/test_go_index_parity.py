"""IT-1 parity — Go structure→OTel index L1 (FR-1).

The Go structural-element surface (L1) is HAND-AUTHORED (advisory tier, no reflectable grammar),
so it can drift from what go_parser.py actually emits. These tests are that drift's only guard:

  1. authored forms' parser_kind ⊆ PARSER_KIND_SETS["go"]   (no invented kind)
  2. every parser kind is covered by ≥1 form                (completeness)
  3. EMPIRICAL: parse_go_source on real Go fixtures emits only kinds the forms cover
  4. the on-disk index matches the generator (--check drift guard)

Spec: docs/design/REQ-crosswalk-go-structure-to-otel-comm-domains.md · FR-1
Pattern: dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from startd8.languages.go_parser import parse_go_source
from startd8.languages.manifest_adapter import PARSER_KIND_SETS

import json

REPO = Path(__file__).resolve().parents[3]
_GEN_PATH = REPO / "scripts" / "gen_go_structure_comm_index.py"
_FIXTURE_DIR = REPO / "tests" / "unit" / "benchmark_matrix" / "behavioral" / "fixtures"
_PY_CROSSWALK = REPO / "docs" / "design" / "python-capability-index" / "communication-crosswalk.json"


def _suffix(pattern_id: str) -> str:
    # "PY-OTEL-5.1-HTTP" / "GO-OTEL-5.1-HTTP" -> "5.1-HTTP"
    return pattern_id.split("-OTEL-", 1)[1]


def _load_gen():
    spec = importlib.util.spec_from_file_location("gen_go_structure_comm_index", _GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_gen = _load_gen()
_FORMS = _gen._go_structure_forms()
_GO_KINDS = PARSER_KIND_SETS["go"]


class TestL1FormParity:
    def test_form_kinds_subset_of_parser_kinds(self):
        # (1) no authored form claims a kind the Go parser never emits.
        authored = {f["parser_kind"] for f in _FORMS}
        stray = authored - _GO_KINDS
        assert not stray, f"forms claim kinds go_parser never emits: {stray}"

    def test_every_parser_kind_is_covered(self):
        # (2) completeness — each parser kind has at least one form.
        authored = {f["parser_kind"] for f in _FORMS}
        missing = _GO_KINDS - authored
        assert not missing, f"parser kinds with no L1 form: {missing}"

    def test_form_ids_unique_and_well_formed(self):
        ids = [f["id"] for f in _FORMS]
        assert len(ids) == len(set(ids)), "duplicate GO-STRUCT ids"
        assert all(i.startswith("GO-STRUCT-") for i in ids)

    def test_struct_interface_share_class_kind(self):
        # The one non-1:1 mapping: struct + interface both parser_kind=class, split by discriminator.
        class_forms = [f for f in _FORMS if f["parser_kind"] == "class"]
        assert {f["form"] for f in class_forms} == {"struct", "interface"}
        assert all("discriminator" in f for f in class_forms)


class TestL1EmpiricalAgainstRealGo:
    def test_real_fixtures_emit_only_covered_kinds(self):
        # (3) the load-bearing test: run the ACTUAL parser on ACTUAL Go and confirm every kind
        # it produces is covered by an authored form. This catches drift the static sets can't.
        go_files = sorted(_FIXTURE_DIR.glob("*/main.go"))
        assert go_files, f"no Go fixtures under {_FIXTURE_DIR}"
        authored = {f["parser_kind"] for f in _FORMS}
        seen: set[str] = set()
        for gf in go_files:
            for el in parse_go_source(gf.read_text(encoding="utf-8")):
                seen.add(el.kind)
        assert seen, "parser emitted no elements on the fixtures"
        uncovered = seen - authored
        assert not uncovered, f"parser emitted kinds no L1 form covers: {uncovered}"


_XWALK = _gen._communication_crosswalk()
_FLOOR = _gen._detectability_floor()
_COMPOSITES_DOC = _gen._language_composites()
_COMPOSITES = _COMPOSITES_DOC["composites"]
_FORM_IDS = {f["id"] for f in _FORMS}


class TestL3Composites:
    """FR-3 — composites keyed on go_forms (not ast_nodes), referencing real L1 forms."""

    def test_no_composite_has_ast_nodes(self):
        # The deliberate schema divergence from Python: Go has no AST nodes.
        for co in _COMPOSITES:
            assert "ast_nodes" not in co, f"{co['id']} leaks an ast_nodes field"

    def test_every_go_form_ref_exists(self):
        for co in _COMPOSITES:
            for fid in co["go_forms"]:
                assert fid in _FORM_IDS, f"{co['id']} references unknown form {fid}"

    def test_composite_ids_unique_and_wellformed(self):
        ids = [co["id"] for co in _COMPOSITES]
        assert len(ids) == len(set(ids))
        assert all(i.startswith("GO-LC-") for i in ids)

    def test_body_level_idioms_are_recorded_not_witnessable(self):
        # goroutine/channel/defer are un-witnessable at advisory tier — must be recorded, not silently dropped.
        names = {n["name"] for n in _COMPOSITES_DOC["not_witnessable"]}
        assert {"goroutine", "channel", "defer"} <= names
        composite_names = {co["name"] for co in _COMPOSITES}
        assert composite_names.isdisjoint({"goroutine", "channel", "defer"})
        for n in _COMPOSITES_DOC["not_witnessable"]:
            assert n.get("reason")


class TestL4CrosswalkParityWithPython:
    """FR-2 — the invariant: Go's 15 §5 keys are key-for-key identical to the Python pilot."""

    def _py_patterns(self):
        return json.loads(_PY_CROSSWALK.read_text(encoding="utf-8"))["patterns"]

    def test_pattern_id_suffixes_match_python(self):
        go = {_suffix(p["id"]) for p in _XWALK}
        py = {_suffix(p["id"]) for p in self._py_patterns()}
        assert go == py, f"id-suffix drift vs Python: go-py={go - py}, py-go={py - go}"

    def test_semconv_domain_set_matches_python(self):
        go = {p["semconv_domain"] for p in _XWALK}
        py = {p["semconv_domain"] for p in self._py_patterns()}
        assert go == py, f"semconv domain drift: go-py={go - py}, py-go={py - go}"

    def test_exactly_15_patterns(self):
        assert len(_XWALK) == 16
        assert len({p["id"] for p in _XWALK}) == 16


class TestL4DetectorAndFloor:
    """FR-2 / FR-5 — import-only detector + the detectability floor is honest."""

    def test_every_non_floor_pattern_has_a_signature(self):
        for p in _XWALK:
            if p.get("floor"):
                continue
            sigs = p.get("import_signatures") or []
            assert sigs, f"{p['id']} is not floor but has no import_signatures"

    def test_floor_patterns_carry_no_signatures(self):
        # A floor pattern must be un-witnessable — it cannot smuggle in a signature.
        for p in _XWALK:
            if p.get("floor"):
                assert not p.get("import_signatures"), f"{p['id']} floor but has signatures"

    def test_floor_block_matches_flagged_patterns(self):
        flagged = {p["id"] for p in _XWALK if p.get("floor")}
        blocked = {f["id"] for f in _FLOOR}
        assert flagged == blocked, f"floor flag/block mismatch: flag={flagged} block={blocked}"

    def test_floor_is_metrics_and_cicd_not_genai(self):
        # The IT-3 reclassification: GENAI is import-detectable; CICD is not.
        blocked = {f["id"] for f in _FLOOR}
        assert blocked == {"GO-OTEL-5.2-HTTP-METRICS", "GO-OTEL-5.7-CICD"}
        genai = next(p for p in _XWALK if p["id"] == "GO-OTEL-5.6-GENAI")
        assert not genai.get("floor") and genai.get("import_signatures")

    def test_floor_entries_cite_a_reason(self):
        for f in _FLOOR:
            assert f.get("reason") and f.get("tier") == "advisory"


def _load_analyzer():
    spec = importlib.util.spec_from_file_location(
        "analyze_go_comm_coverage", REPO / "scripts" / "analyze_go_comm_coverage.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_ANALYZER = _load_analyzer()
_ACHIEVABLE = [p for p in _XWALK if not p.get("floor")]
_FLOOR_IDS = {f["id"] for f in _FLOOR}


class TestCoverageMatcher:
    """FR-4 — import-only detection, collision-safe."""

    def test_net_http_is_http_not_dns(self):
        # The reason 'net' was removed from DNS: prefix-match must not let net/http become DNS.
        hyp = set(_ANALYZER._hyp(["net/http"], _ACHIEVABLE))
        assert "GO-OTEL-5.1-HTTP" in hyp
        assert "GO-OTEL-5.1-DNS" not in hyp

    def test_subpackage_matches(self):
        # A real Thanos object-store import is a sub-package of the signature.
        hyp = set(_ANALYZER._hyp(["github.com/thanos-io/objstore/providers/s3"], _ACHIEVABLE))
        assert "GO-OTEL-5.1-OBJECT-STORE" in hyp

    def test_unrelated_import_matches_nothing(self):
        assert _ANALYZER._hyp(["context", "fmt", "strings"], _ACHIEVABLE) == []


class TestCoverageOverRealGoFixtures:
    """FR-4 — runs the analyzer on in-repo Go and confirms the FR-4 verify + floor exclusion.

    Corpus-independent: uses the benchmark Go fixtures, NOT OSS/Thanos (which lives outside the repo).
    """

    def test_analyze_detects_rpc_and_http_and_excludes_floor(self):
        r = _ANALYZER.analyze(_FIXTURE_DIR)
        assert r["files_analyzed"] > 0
        assert "GO-OTEL-5.3-RPC" in r["detected"], "grpc fixtures should evidence RPC"
        assert "GO-OTEL-5.1-HTTP" in r["detected"], "frontend fixture imports net/http"
        # floor patterns must NEVER appear in any file's hypothesis (correct-absence).
        for f in r["per_file_hyp"]:
            assert _FLOOR_IDS.isdisjoint(f["hyp"]), f"floor pattern leaked into hyp: {f}"
        # achievable denominator excludes floor.
        assert r["coverage"]["achievable_patterns"] == len(_XWALK) - len(_FLOOR)
        assert set(r["coverage"]["floor_patterns_excluded"]) == _FLOOR_IDS


class TestDriftGuard:
    def test_on_disk_index_in_sync(self):
        # --check must pass — the committed JSON + .md match the generator (Kagami: no hand-edit).
        assert _gen.main(["--check"]) == 0, "go index on disk is stale — run gen_go_structure_comm_index.py"

    def test_index_doc_generated_with_banner(self):
        # IT-4: the .md is a derived artifact and says so.
        md = (REPO / "docs" / "design" / _gen.INDEX_DOC).read_text(encoding="utf-8")
        assert "GENERATED by" in md and "do not edit" in md
        assert "GO-STRUCT-001" in md and "GO-OTEL-5.1-HTTP" in md
