"""IT-1 parity — Java structure→OTel index L1 (FR-1).

Java's L1 is HAND-AUTHORED, so it can drift from what java_parser emits. These tests guard it, and
additionally verify **per-parse tiering** (MULTILANG_MANIFEST_VALIDATION FR-5) empirically: with
javalang absent the regex-fallback path emits only the `witnessable_at="both"` forms.

Spec: docs/design/REQ-crosswalk-java-structure-to-otel-comm-domains.md · FR-1
Pattern: dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from startd8.languages.java_parser import parse_java_source
from startd8.languages.manifest_adapter import PARSER_KIND_SETS

REPO = Path(__file__).resolve().parents[3]
_GEN_PATH = REPO / "scripts" / "gen_java_structure_comm_index.py"

# Corpus-independent fixture (no in-repo .java files). Exercises every form.
_JAVA_FIXTURE = """
package a.b;
import io.grpc.Server;
import java.sql.Connection;

@Path("/x")
public class Svc implements Runnable {
  @GET public String get() { return null; }
  private int field;
  static final int C = 1;
  public Svc() {}
}
interface I {}
enum E { A, B }
"""


def _load_gen():
    spec = importlib.util.spec_from_file_location("gen_java_structure_comm_index", _GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_gen = _load_gen()
_FORMS = _gen._java_structure_forms()
_JAVA_KINDS = PARSER_KIND_SETS["java"]


class TestL1FormParity:
    def test_form_kinds_subset_of_parser_kinds(self):
        stray = {f["parser_kind"] for f in _FORMS} - _JAVA_KINDS
        assert not stray, f"forms claim kinds java_parser never emits: {stray}"

    def test_every_parser_kind_is_covered(self):
        missing = _JAVA_KINDS - {f["parser_kind"] for f in _FORMS}
        assert not missing, f"parser kinds with no L1 form: {missing}"

    def test_form_ids_unique_and_wellformed(self):
        ids = [f["id"] for f in _FORMS]
        assert len(ids) == len(set(ids))
        assert all(i.startswith("JAVA-STRUCT-") for i in ids)

    def test_witnessable_at_values_valid(self):
        assert all(f["witnessable_at"] in {"both", "authoritative"} for f in _FORMS)


class TestPerParseTiering:
    """FR-5 empirical: the regex-fallback path (javalang absent) emits a SUBSET = the 'both' forms."""

    def test_regex_emits_only_covered_kinds(self):
        seen = {el.kind for el in parse_java_source(_JAVA_FIXTURE)}
        assert seen, "parser emitted nothing"
        uncovered = seen - {f["parser_kind"] for f in _FORMS}
        assert not uncovered, f"parser emitted kinds no form covers: {uncovered}"

    def test_authoritative_only_forms_absent_on_regex_path(self):
        # field/constant are 'authoritative' — the regex path drops them. If this ever fails,
        # javalang got installed (tier upgraded) OR the regex parser gained field extraction —
        # either way the witnessable_at markers must be re-graded.
        seen = {el.kind for el in parse_java_source(_JAVA_FIXTURE)}
        regex_dropped = {f["parser_kind"] for f in _FORMS if f["witnessable_at"] == "authoritative"}
        leaked = seen & regex_dropped
        assert not leaked, f"authoritative-only kinds appeared on the regex path: {leaked} (re-grade witnessable_at)"

    def test_both_forms_are_witnessed(self):
        seen = {el.kind for el in parse_java_source(_JAVA_FIXTURE)}
        both = {f["parser_kind"] for f in _FORMS if f["witnessable_at"] == "both"}
        assert both <= seen, f"'both' forms not all witnessed on the fixture: {both - seen}"

    def test_annotation_signal_is_extracted(self):
        # The Java-specific axis: annotations ARE surfaced (the whole reason Java > Go).
        anns = {a for el in parse_java_source(_JAVA_FIXTURE) for a in el.annotations}
        assert "Path" in anns or "GET" in anns, f"no annotations extracted: {anns}"


import json

_XWALK = _gen._communication_crosswalk()
_FLOOR = _gen._detectability_floor()
_PY_CROSSWALK = REPO / "docs" / "design" / "python-capability-index" / "communication-crosswalk.json"


def _suffix(pid: str) -> str:
    return pid.split("-OTEL-", 1)[1]


class TestL4CrosswalkParityWithPython:
    def _py(self):
        return json.loads(_PY_CROSSWALK.read_text(encoding="utf-8"))["patterns"]

    def test_pattern_id_suffixes_match_python(self):
        go = {_suffix(p["id"]) for p in _XWALK}
        py = {_suffix(p["id"]) for p in self._py()}
        assert go == py, f"id-suffix drift: java-py={go - py}, py-java={py - go}"

    def test_semconv_domain_set_matches_python(self):
        assert {p["semconv_domain"] for p in _XWALK} == {p["semconv_domain"] for p in self._py()}

    def test_exactly_15_patterns(self):
        assert len(_XWALK) == 16 == len({p["id"] for p in _XWALK})


class TestL4AnnotationAxis:
    """FR-2 — the Java-specific signal: a §5 pattern fires on import OR annotation."""

    def test_every_non_floor_has_import_or_annotation(self):
        for p in _XWALK:
            if p.get("floor"):
                continue
            sigs = (p.get("import_signatures") or []) + (p.get("annotation_signatures") or [])
            assert sigs, f"{p['id']} non-floor but has neither import nor annotation signature"

    def test_annotation_axis_is_actually_used(self):
        # The whole point of Java over Go: at least the corpus HTTP/DB/RPC/CLI patterns carry annotations.
        annotated = {p["id"] for p in _XWALK if p.get("annotation_signatures")}
        assert {"JAVA-OTEL-5.1-HTTP", "JAVA-OTEL-5.5-DATABASE", "JAVA-OTEL-5.7-CLI"} <= annotated

    def test_floor_carries_no_signatures(self):
        for p in _XWALK:
            if p.get("floor"):
                assert not p.get("import_signatures") and not p.get("annotation_signatures")


class TestFloorAndResolutionPending:
    def test_floor_block_matches_flags(self):
        assert {p["id"] for p in _XWALK if p.get("floor")} == {f["id"] for f in _FLOOR}

    def test_floor_is_metrics_and_cicd(self):
        assert {f["id"] for f in _FLOOR} == {"JAVA-OTEL-5.2-HTTP-METRICS", "JAVA-OTEL-5.7-CICD"}

    def test_resolution_pending_cites_scip(self):
        rp = _gen.RESOLUTION_PENDING
        assert rp["status"] == "resolution-pending" and "scip" in rp["unlock"].lower()


_COMPOSITES_DOC = _gen._language_composites()
_COMPOSITES = _COMPOSITES_DOC["composites"]
_FORM_IDS = {f["id"] for f in _FORMS}


class TestL3Composites:
    def test_no_composite_has_ast_nodes(self):
        for co in _COMPOSITES:
            assert "ast_nodes" not in co

    def test_every_java_form_ref_exists(self):
        for co in _COMPOSITES:
            for fid in co["java_forms"]:
                assert fid in _FORM_IDS, f"{co['id']} references unknown form {fid}"

    def test_composites_key_on_real_javaelement_fields(self):
        # Guard against fabricated fields: each composite's `field` must be a real JavaElement attr.
        from startd8.languages.java_parser import JavaElement
        real = {f.name for f in __import__("dataclasses").fields(JavaElement)}
        for co in _COMPOSITES:
            assert co["field"] in real, f"{co['id']} keys on non-existent JavaElement.{co['field']}"

    def test_body_level_idioms_recorded_not_witnessable(self):
        names = {n["name"] for n in _COMPOSITES_DOC["not_witnessable"]}
        assert {"lambda_expression", "try_with_resources", "stream_pipeline"} <= names
        assert {co["name"] for co in _COMPOSITES}.isdisjoint(names)


def _load_analyzer():
    spec = importlib.util.spec_from_file_location(
        "analyze_java_comm_coverage", REPO / "scripts" / "analyze_java_comm_coverage.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_ANALYZER = _load_analyzer()
_ACHIEVABLE = [p for p in _XWALK if not p.get("floor")]
_FLOOR_IDS = {f["id"] for f in _FLOOR}


class TestCoverageMatcher:
    def test_import_subpackage_matches(self):
        h = _ANALYZER._hyp(["io.grpc.Server"], set(), _ACHIEVABLE)
        assert h.get("JAVA-OTEL-5.3-RPC") == "import"

    def test_annotation_only_path(self):
        # A file with @Path but no HTTP import → detected via ANNOTATION only (the axis's value).
        h = _ANALYZER._hyp([], {"Path"}, _ACHIEVABLE)
        assert h.get("JAVA-OTEL-5.1-HTTP") == "annotation"

    def test_both_signals(self):
        h = _ANALYZER._hyp(["javax.ws.rs.GET"], {"Path"}, _ACHIEVABLE)
        assert h.get("JAVA-OTEL-5.1-HTTP") == "both"

    def test_unrelated_matches_nothing(self):
        assert _ANALYZER._hyp(["java.util.List"], {"Override"}, _ACHIEVABLE) == {}


class TestCoverageOverFixture:
    """FR-4 — analyzer runs; floor excluded; the import-vs-annotation breakdown is populated.

    Corpus-independent: writes a tiny .java tree to a tmp dir (OSS/kestra is outside the repo).
    """

    def test_analyze_detects_and_splits_signals(self, tmp_path):
        (tmp_path / "A.java").write_text(
            'import io.grpc.Server;\n@Path("/x")\nclass A { @GET String g(){return null;} }\n')
        (tmp_path / "B.java").write_text('import java.sql.Connection;\n@Repository class B {}\n')
        r = _ANALYZER.analyze(tmp_path)
        assert r["files_analyzed"] == 2
        assert "JAVA-OTEL-5.3-RPC" in r["detected"]     # io.grpc (import)
        assert "JAVA-OTEL-5.1-HTTP" in r["detected"]    # @Path (annotation)
        assert "JAVA-OTEL-5.5-DATABASE" in r["detected"]  # java.sql + @Repository
        # floor never leaks
        for f in r["per_file_hyp"]:
            assert _FLOOR_IDS.isdisjoint(f["hyp"])
        assert r["coverage"]["achievable_patterns"] == len(_XWALK) - len(_FLOOR)
        # the breakdown is real: HTTP was annotation-driven here
        http = r["per_pattern_signal_counts"]["JAVA-OTEL-5.1-HTTP"]
        assert http["annotation"] + http["both"] >= 1


class TestDriftGuard:
    def test_on_disk_index_in_sync(self):
        assert _gen.main(["--check"]) == 0, "java index on disk is stale — run gen_java_structure_comm_index.py"

    def test_index_doc_generated_with_banner_and_annotation_column(self):
        md = (REPO / "docs" / "design" / _gen.INDEX_DOC).read_text(encoding="utf-8")
        assert "GENERATED by" in md and "do not edit" in md
        assert "JAVA-STRUCT-001" in md and "JAVA-OTEL-5.1-HTTP" in md
        assert "annotation signatures" in md and "@Path" in md  # the Java-specific column is rendered
