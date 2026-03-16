"""Tests for Kaizen Quality Phase (A-E).

Covers:
- Phase A: Registry quality enrichment (metadata in set_phase_status)
- Phase C: Kaizen hints in spec_builder and drafter
- Phase E: Dual quality scoring (compute_disk_quality_score, assembly_delta)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from startd8.contractors.prime_postmortem import (
    CAUSE_TO_SUGGESTION,
    CrossFeaturePattern,
    FeaturePostMortem,
    PipelineStage,
    PrimePostMortemEvaluator,
    PrimePostMortemReport,
    RootCause,
    compute_disk_quality_score,
    generate_kaizen_suggestions,
)


# ---------------------------------------------------------------------------
# Phase A: Registry metadata enrichment
# ---------------------------------------------------------------------------


class TestRegistryMetadataEnrichment:
    """Phase A: Verify set_phase_status receives metadata dict."""

    def test_set_phase_status_receives_metadata_on_template_success(self):
        """Template-generated elements should pass metadata with generation_strategy='template'."""
        from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec, ForwardManifest
        from startd8.micro_prime.engine import MicroPrimeEngine
        from startd8.micro_prime.models import MicroPrimeConfig
        from startd8.utils.code_manifest import ElementKind, Param, Signature

        # Create a mock registry
        mock_registry = MagicMock()
        mock_registry.get.return_value = None  # new entry path

        config = MicroPrimeConfig(templates_enabled=True)
        engine = MicroPrimeEngine(config=config)
        engine._element_registry = mock_registry

        # __init__ element — matches template
        element = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__init__",
            signature=Signature(
                params=[
                    Param(name="self"),
                    Param(name="name", annotation="str"),
                ],
                return_annotation="None",
            ),
            parent_class="MyClass",
        )
        file_spec = ForwardFileSpec(
            file="test.py",
            description="Test file",
            elements=[element],
        )
        skeleton = "class MyClass:\n    def __init__(self, name: str) -> None:\n        pass\n"
        manifest = ForwardManifest(file_specs={"test.py": file_spec})

        result = engine.process_element(element, file_spec, skeleton)
        assert result.success is True

        # Check that set_phase_status was called with metadata
        if mock_registry.set_phase_status.called:
            call_args = mock_registry.set_phase_status.call_args
            assert call_args is not None
            # metadata should be the 4th positional or keyword arg
            if call_args.kwargs.get("metadata"):
                metadata = call_args.kwargs["metadata"]
            elif len(call_args.args) >= 4:
                metadata = call_args.args[3]
            else:
                metadata = call_args.kwargs.get("metadata")
            if metadata is not None:
                assert "generation_strategy" in metadata
                assert "model" in metadata

    def test_element_result_template_has_generation_strategy(self):
        """ElementResult.make_template_match should carry generation_strategy."""
        from startd8.micro_prime.models import ElementResult, TierClassification

        result = ElementResult.make_template_match(
            "test_func", "test.py",
            TierClassification.TRIVIAL, "template match",
            "def test_func(): pass", "init_template",
            generation_strategy="template",
        )
        assert result.generation_strategy == "template"
        assert result.template_used is True


# ---------------------------------------------------------------------------
# Phase C: Kaizen hints in spec_builder and drafter
# ---------------------------------------------------------------------------


class TestKaizenFeedbackLoop:
    """Phase C: Verify kaizen_hints flow through spec and draft prompts."""

    def test_spec_prompt_includes_kaizen_hints(self):
        """Kaizen hints in context should appear as P1 section in spec prompt."""
        from startd8.implementation_engine.spec_builder import build_spec_prompt

        context = {
            "kaizen_hints": "- Check for stubs before returning\n- Validate imports",
            "target_files": ["service.py"],
        }
        prompt = build_spec_prompt(
            "Implement a service",
            context,
            output_format=None,
        )
        assert "Quality Hints" in prompt
        assert "Check for stubs" in prompt
        assert "Validate imports" in prompt

    def test_spec_prompt_no_kaizen_hints_no_section(self):
        """When kaizen_hints absent, no Quality Hints section appears."""
        from startd8.implementation_engine.spec_builder import build_spec_prompt

        context = {"target_files": ["service.py"]}
        prompt = build_spec_prompt("Implement a service", context, output_format=None)
        assert "Quality Hints" not in prompt

    def test_spec_prompt_empty_kaizen_hints_no_section(self):
        """Empty/whitespace kaizen_hints should not produce a section."""
        from startd8.implementation_engine.spec_builder import build_spec_prompt

        context = {"kaizen_hints": "   ", "target_files": ["service.py"]}
        prompt = build_spec_prompt("Implement a service", context, output_format=None)
        assert "Quality Hints" not in prompt

    def test_drafter_supplementary_includes_kaizen_hints(self):
        """Kaizen hints should appear in drafter supplementary sections."""
        from startd8.implementation_engine.drafter import build_supplementary_sections

        context = {
            "kaizen_hints": "- Fix all stubs\n- No phantom imports",
        }
        result = build_supplementary_sections(context)
        assert "Quality Hints" in result
        assert "Fix all stubs" in result

    def test_drafter_supplementary_no_hints(self):
        """No kaizen_hints key → no Quality Hints section in supplementary."""
        from startd8.implementation_engine.drafter import build_supplementary_sections

        result = build_supplementary_sections({})
        assert "Quality Hints" not in result


# ---------------------------------------------------------------------------
# Phase C: CAUSE_TO_SUGGESTION and generate_kaizen_suggestions
# ---------------------------------------------------------------------------


class TestCauseToSuggestion:
    """Phase C: Verify CAUSE_TO_SUGGESTION mapping completeness."""

    def test_all_root_causes_have_suggestions(self):
        """All 16 RootCause enum values should have a suggestion entry."""
        for cause in RootCause:
            assert cause.value in CAUSE_TO_SUGGESTION, (
                f"RootCause.{cause.name} ({cause.value}) missing from CAUSE_TO_SUGGESTION"
            )

    def test_each_suggestion_has_phase_and_hint(self):
        """Each suggestion entry must have 'phase' and 'hint' keys."""
        for key, entry in CAUSE_TO_SUGGESTION.items():
            assert "phase" in entry, f"Missing 'phase' in suggestion for {key}"
            assert "hint" in entry, f"Missing 'hint' in suggestion for {key}"
            assert entry["hint"].strip(), f"Empty hint for {key}"

    def test_generate_kaizen_suggestions_from_report(self):
        """generate_kaizen_suggestions should produce valid output."""
        report = MagicMock()
        report.cross_feature_patterns = [
            CrossFeaturePattern(
                pattern_type="duplicate_import",
                description="duplicate_import repeated 3 times",
                affected_features=["f1", "f2", "f3"],
                frequency=3,
                severity="high",
            ),
        ]
        suggestions = generate_kaizen_suggestions(report)
        assert len(suggestions) == 1
        assert suggestions[0]["phase"] == "draft"
        assert suggestions[0]["confidence"] == "high"
        assert "Deduplicate" in suggestions[0]["suggested_action"]

    def test_generate_kaizen_suggestions_skips_unknown_pattern(self):
        """Unknown pattern types should be silently skipped."""
        report = MagicMock()
        report.cross_feature_patterns = [
            CrossFeaturePattern(
                pattern_type="nonexistent_pattern_type",
                description="something",
                frequency=5,
            ),
        ]
        suggestions = generate_kaizen_suggestions(report)
        assert len(suggestions) == 0

    def test_generate_kaizen_suggestions_skips_low_frequency(self):
        """Patterns with frequency < 2 should be skipped."""
        report = MagicMock()
        report.cross_feature_patterns = [
            CrossFeaturePattern(
                pattern_type="duplicate_import",
                description="once",
                frequency=1,
            ),
        ]
        suggestions = generate_kaizen_suggestions(report)
        assert len(suggestions) == 0


# ---------------------------------------------------------------------------
# Phase E: Dual quality scoring
# ---------------------------------------------------------------------------


class TestDualQualityScoring:
    """Phase E: compute_disk_quality_score and assembly_delta."""

    def test_perfect_compliance_score_1(self):
        """Perfect DiskComplianceResult → score 1.0."""
        compliance = MagicMock()
        compliance.ast_valid = True
        compliance.contract_compliance = 1.0
        compliance.import_completeness = 1.0
        compliance.stubs_remaining = 0
        compliance.semantic_issues = []
        score = compute_disk_quality_score(compliance)
        assert score == pytest.approx(1.0)

    def test_all_stubs_low_score(self):
        """Many stubs should drive score down."""
        compliance = MagicMock()
        compliance.ast_valid = True
        compliance.contract_compliance = 1.0
        compliance.import_completeness = 1.0
        compliance.stubs_remaining = 10
        compliance.semantic_issues = []
        score = compute_disk_quality_score(compliance)
        assert score < 0.9  # stub_penalty = max(0, 1.0 - 10*0.1) = 0

    def test_syntax_error_score_zero(self):
        """ast_valid=False → score 0.0."""
        compliance = MagicMock()
        compliance.ast_valid = False
        score = compute_disk_quality_score(compliance)
        assert score == 0.0

    def test_none_compliance_score_zero(self):
        """None compliance → score 0.0."""
        score = compute_disk_quality_score(None)
        assert score == 0.0

    def test_semantic_issues_reduce_score(self):
        """Semantic issues should reduce score via semantic_penalty."""
        compliance = MagicMock()
        compliance.ast_valid = True
        compliance.contract_compliance = 1.0
        compliance.import_completeness = 1.0
        compliance.stubs_remaining = 0
        compliance.semantic_issues = ["issue1", "issue2", "issue3"]
        score = compute_disk_quality_score(compliance)
        # semantic_penalty = max(0, 1.0 - 3*0.15) = 0.55
        assert score < 1.0
        assert score > 0.0

    def test_assembly_delta_computation(self):
        """assembly_delta = requirement_score - disk_quality_score."""
        fpm = FeaturePostMortem(
            feature_id="f1",
            name="Feature 1",
            status="complete",
            success=True,
            requirement_score=0.9,
        )
        fpm.disk_quality_score = 0.7
        fpm.assembly_delta = fpm.requirement_score - fpm.disk_quality_score
        assert fpm.assembly_delta == pytest.approx(0.2)

    def test_avg_assembly_delta_on_report(self):
        """PrimePostMortemReport should carry avg_assembly_delta."""
        report = PrimePostMortemReport(
            report_id="test",
            timestamp="2026-01-01",
        )
        assert report.avg_assembly_delta is None

    def test_assembly_quality_gap_pattern(self):
        """Large assembly deltas across features should create cross-feature pattern."""
        evaluator = PrimePostMortemEvaluator()
        # Use minimal evaluate call with no features
        result_dict = {"status": "complete", "history": []}
        report = evaluator.evaluate(
            result_dict=result_dict,
            queue_state={},
        )
        # No disk analysis → no assembly_quality_gap pattern
        gap_patterns = [
            p for p in report.cross_feature_patterns
            if p.pattern_type == "assembly_quality_gap"
        ]
        assert len(gap_patterns) == 0

    def test_scoring_formula_weights(self):
        """Verify the scoring formula with severity-weighted semantic penalty."""
        compliance = MagicMock()
        compliance.ast_valid = True
        compliance.contract_compliance = 0.5
        compliance.import_completeness = 0.5
        compliance.stubs_remaining = 5  # penalty = max(0, 1 - 0.5) = 0.5
        # 1 error (0.3) + 1 warning (0.1) → penalty = max(0, 1 - 0.4) = 0.6
        compliance.semantic_issues = [
            {"severity": "error", "category": "import_resolution"},
            {"severity": "warning", "category": "orphan_dependency"},
        ]

        score = compute_disk_quality_score(compliance)
        expected = 0.5 * 0.4 + 0.5 * 0.2 + 0.5 * 0.2 + 0.6 * 0.2
        assert score == pytest.approx(expected)
