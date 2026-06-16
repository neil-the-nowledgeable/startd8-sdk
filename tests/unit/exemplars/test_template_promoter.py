"""Tests for exemplar-to-template promotion (Layer 4)."""

import pytest

from startd8.exemplars.models import ConfigFingerprint, ExemplarEntry, ExemplarScores
from startd8.exemplars.registry import ExemplarRegistry
from startd8.exemplars.template_promoter import (
    PromotedTemplate,
    _lcs_lines,
    _multi_lcs,
    _normalize_line,
    _normalize_lines,
    promote_exemplars_to_templates,
)


def _make_exemplar(fp_str, code, maturity=3, run_id="run-001", feature_id="f-001"):
    fp = ConfigFingerprint.from_string(fp_str)
    return ExemplarEntry(
        id=ExemplarEntry.make_id(fp, run_id, feature_id),
        fingerprint=fp,
        maturity=maturity,
        source_run_id=run_id,
        source_feature_id=feature_id,
        spec_artifact_path="",
        code_artifact_path="",
        draft_artifact_path="",
        seed_task_digest="abc",
        scores=ExemplarScores(disk_quality_score=1.0),
        code_summary=code,
    )


# --- Normalization tests ---


class TestNormalization:
    def test_normalize_service_name(self):
        line = "grpcServer := grpc.NewServer(CurrencyService)"
        norm, params = _normalize_line(line)
        assert "CurrencyService" in params
        assert "{param_0}" in norm

    def test_normalize_blank_line(self):
        norm, params = _normalize_line("")
        assert norm == ""
        assert params == []

    def test_normalize_comment(self):
        norm, params = _normalize_line("// Create server")
        assert norm == "// Create server"
        assert params == []

    def test_normalize_whitespace(self):
        norm, _ = _normalize_line("  foo   bar  baz  ")
        assert "  " not in norm  # multiple spaces collapsed

    def test_normalize_lines_skips_blanks(self):
        code = "line1\n\nline2\n\nline3"
        norm, _ = _normalize_lines(code)
        assert len(norm) == 3

    def test_normalize_lines_collects_params(self):
        code = "CurrencyService.Start()\nPaymentHandler.Handle()"
        norm, params = _normalize_lines(code)
        assert "CurrencyService" in params
        assert "PaymentHandler" in params


# --- LCS tests ---


class TestLCS:
    def test_identical(self):
        a = ["line1", "line2", "line3"]
        assert _lcs_lines(a, a) == a

    def test_one_different(self):
        a = ["line1", "line2", "line3"]
        b = ["line1", "DIFF", "line3"]
        assert _lcs_lines(a, b) == ["line1", "line3"]

    def test_empty(self):
        assert _lcs_lines([], ["a"]) == []
        assert _lcs_lines(["a"], []) == []

    def test_both_empty(self):
        assert _lcs_lines([], []) == []

    def test_multi_lcs(self):
        a = ["a", "b", "c", "d"]
        b = ["a", "x", "c", "d"]
        c = ["a", "b", "y", "d"]
        result = _multi_lcs([a, b, c])
        assert "a" in result
        assert "d" in result

    def test_multi_lcs_empty_input(self):
        assert _multi_lcs([]) == []

    def test_multi_lcs_single(self):
        a = ["a", "b", "c"]
        assert _multi_lcs([a]) == a

    def test_multi_lcs_no_common(self):
        a = ["a"]
        b = ["b"]
        c = ["c"]
        assert _multi_lcs([a, b, c]) == []


# --- Promotion tests ---


class TestPromoteExemplars:
    def test_promotes_above_threshold(self):
        """3 exemplars with 85%+ identical lines -> template."""
        shared = (
            "server := grpc.NewServer()\n"
            "pb.RegisterService(server)\n"
            "server.Serve(lis)\n"
            'log.Println("serving")\n'
            "server.GracefulStop()"
        )

        e1 = _make_exemplar(
            "go:source:grpc:grpc_server", shared + "\n// extra1", run_id="run-001"
        )
        e2 = _make_exemplar(
            "go:source:grpc:grpc_server", shared + "\n// extra2", run_id="run-002"
        )
        e3 = _make_exemplar(
            "go:source:grpc:grpc_server", shared + "\n// extra3", run_id="run-003"
        )

        templates = promote_exemplars_to_templates([e1, e2, e3])
        assert len(templates) == 1
        assert templates[0].fingerprint == "go:source:grpc:grpc_server"
        assert templates[0].invariant_ratio >= 0.80

    def test_below_threshold(self):
        """3 exemplars with <80% identical lines -> no template."""
        e1 = _make_exemplar(
            "go:source:none:source_module",
            "line1\nline2\nline3\nline4\nline5",
            run_id="run-001",
        )
        e2 = _make_exemplar(
            "go:source:none:source_module",
            "lineA\nlineB\nlineC\nlineD\nlineE",
            run_id="run-002",
        )
        e3 = _make_exemplar(
            "go:source:none:source_module",
            "lineX\nlineY\nlineZ\nlineW\nlineV",
            run_id="run-003",
        )

        templates = promote_exemplars_to_templates([e1, e2, e3])
        assert len(templates) == 0

    def test_insufficient_exemplars(self):
        """Fewer than 3 exemplars -> no promotion."""
        code = "server := grpc.NewServer()\nserver.Serve(lis)"
        e1 = _make_exemplar("go:source:grpc:grpc_server", code, run_id="run-001")
        e2 = _make_exemplar("go:source:grpc:grpc_server", code, run_id="run-002")

        templates = promote_exemplars_to_templates([e1, e2])
        assert len(templates) == 0

    def test_skips_non_level3(self):
        """Only level-3 exemplars are considered."""
        code = "server := grpc.NewServer()\nserver.Serve(lis)"
        e1 = _make_exemplar(
            "go:source:grpc:grpc_server", code, maturity=2, run_id="run-001"
        )
        e2 = _make_exemplar(
            "go:source:grpc:grpc_server", code, maturity=2, run_id="run-002"
        )
        e3 = _make_exemplar(
            "go:source:grpc:grpc_server", code, maturity=2, run_id="run-003"
        )

        templates = promote_exemplars_to_templates([e1, e2, e3])
        assert len(templates) == 0

    def test_skips_empty_code_summary(self):
        """Exemplars with empty code_summary are ignored."""
        e1 = _make_exemplar("go:source:grpc:grpc_server", "", run_id="run-001")
        e2 = _make_exemplar("go:source:grpc:grpc_server", "", run_id="run-002")
        e3 = _make_exemplar("go:source:grpc:grpc_server", "", run_id="run-003")

        templates = promote_exemplars_to_templates([e1, e2, e3])
        assert len(templates) == 0

    def test_multiple_fingerprints(self):
        """Exemplars from different fingerprints are grouped separately."""
        shared_a = "server := grpc.NewServer()\nserver.Serve(lis)"
        shared_b = "client := grpc.Dial(addr)\nclient.Close()"

        exemplars = [
            _make_exemplar("go:source:grpc:grpc_server", shared_a, run_id="r1"),
            _make_exemplar("go:source:grpc:grpc_server", shared_a, run_id="r2"),
            _make_exemplar("go:source:grpc:grpc_server", shared_a, run_id="r3"),
            _make_exemplar("go:source:grpc:grpc_client", shared_b, run_id="r1"),
            _make_exemplar("go:source:grpc:grpc_client", shared_b, run_id="r2"),
            _make_exemplar("go:source:grpc:grpc_client", shared_b, run_id="r3"),
        ]

        templates = promote_exemplars_to_templates(exemplars)
        assert len(templates) == 2
        fps = {t.fingerprint for t in templates}
        assert "go:source:grpc:grpc_server" in fps
        assert "go:source:grpc:grpc_client" in fps

    def test_custom_threshold(self):
        """Lower threshold allows promotion with more variation."""
        shared = "line1\nline2\nline3\nline4\nline5"
        e1 = _make_exemplar(
            "go:source:none:source_module", shared, run_id="run-001"
        )
        e2 = _make_exemplar(
            "go:source:none:source_module",
            shared + "\nextra1\nextra2",
            run_id="run-002",
        )
        e3 = _make_exemplar(
            "go:source:none:source_module",
            shared + "\nextra3\nextra4",
            run_id="run-003",
        )

        # With default 80% threshold
        templates = promote_exemplars_to_templates([e1, e2, e3])
        # With lower threshold
        templates_low = promote_exemplars_to_templates(
            [e1, e2, e3], threshold=0.50
        )
        assert len(templates_low) >= len(templates)

    def test_render_with_substitutions(self):
        tmpl = PromotedTemplate(
            fingerprint="go:source:grpc:grpc_server",
            template_lines=(
                "server := grpc.NewServer()",
                "{param_0}.Serve(lis)",
            ),
            param_names=("MyService",),
            source_exemplar_ids=("ex-1", "ex-2", "ex-3"),
            invariant_ratio=0.85,
        )
        rendered = tmpl.render({"param_0": "CurrencyServer"})
        assert "CurrencyServer.Serve(lis)" in rendered

    def test_render_without_substitutions(self):
        tmpl = PromotedTemplate(
            fingerprint="go:source:grpc:grpc_server",
            template_lines=("line1", "line2"),
            param_names=(),
            source_exemplar_ids=("ex-1", "ex-2", "ex-3"),
            invariant_ratio=0.90,
        )
        rendered = tmpl.render()
        assert rendered == "line1\nline2"

    def test_render_preserves_unmatched_placeholders(self):
        tmpl = PromotedTemplate(
            fingerprint="go:source:grpc:grpc_server",
            template_lines=("{param_0} = {param_1}",),
            param_names=("Foo", "Bar"),
            source_exemplar_ids=("ex-1", "ex-2", "ex-3"),
            invariant_ratio=0.90,
        )
        rendered = tmpl.render({"param_0": "X"})
        assert rendered == "X = {param_1}"


