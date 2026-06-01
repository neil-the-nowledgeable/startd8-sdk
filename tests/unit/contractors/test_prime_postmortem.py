"""Tests for Prime Contractor Post-Mortem evaluation."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from startd8.contractors.prime_postmortem import (
    CrossFeaturePattern,
    ElementPostMortem,
    FeaturePostMortem,
    MicroPrimeAnalysis,
    PipelineStage,
    PipelineStageAttribution,
    PrimePostMortemEvaluator,
    PrimePostMortemReport,
    RootCause,
    RootCauseClassifier,
    launch_prime_postmortem_async,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_result_dict(
    history: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Build a minimal result_dict."""
    return {
        "status": "complete",
        "history": history or [],
    }


def _make_history_entry(
    feature_id: str,
    success: bool = True,
    error: str = "",
    cost_usd: float = 0.001,
    generation_metadata: Dict | None = None,
) -> Dict[str, Any]:
    return {
        "feature_id": feature_id,
        "feature_name": feature_id.replace("-", " ").title(),
        "success": success,
        "error": error,
        "cost_usd": cost_usd,
        "generation_metadata": generation_metadata or {},
    }


def _make_queue_state(
    features: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Build queue state from {feature_id: overrides}."""
    state = {}
    for fid, overrides in features.items():
        entry = {
            "id": fid,
            "name": overrides.get("name", fid),
            "status": overrides.get("status", "complete"),
            "error_message": overrides.get("error_message", ""),
            "target_files": overrides.get("target_files", []),
            "generated_files": overrides.get("generated_files", []),
            "dependencies": [],
            "metadata": {},
        }
        entry.update(overrides)
        state[fid] = entry
    return state


# ---------------------------------------------------------------------------
# TestRootCauseClassifier
# ---------------------------------------------------------------------------


class TestRootCauseClassifier:
    """Tests for RootCauseClassifier."""

    @pytest.fixture
    def classifier(self):
        return RootCauseClassifier()

    @pytest.mark.parametrize(
        "error_msg, expected_cause, expected_stage",
        [
            ("F811 redefinition of unused 'os'", RootCause.DUPLICATE_IMPORT, PipelineStage.REPAIR),
            ("NotImplementedError in generated code", RootCause.UNFILLED_STUB, PipelineStage.OLLAMA_GENERATION),
            ("nested class corruption detected", RootCause.SCOPE_CORRUPTION, PipelineStage.SPLICER),
            ("No module named 'phantom_lib'", RootCause.PHANTOM_IMPORT, PipelineStage.OLLAMA_GENERATION),
            ("skeleton not found for target", RootCause.SKELETON_MISSING, PipelineStage.SKELETON),
            ("request timed out after 30s", RootCause.OLLAMA_TIMEOUT, PipelineStage.OLLAMA_GENERATION),
            ("empty response from model", RootCause.OLLAMA_EMPTY_RESPONSE, PipelineStage.OLLAMA_GENERATION),
            ("circuit breaker tripped", RootCause.OLLAMA_CIRCUIT_BREAKER, PipelineStage.OLLAMA_GENERATION),
            ("max repair attempts exhausted", RootCause.REPAIR_EXHAUSTED, PipelineStage.REPAIR),
            ("splice mismatch: expected 5 elements", RootCause.SPLICER_MISMATCH, PipelineStage.SPLICER),
            ("size regression guard rejected", RootCause.SIZE_REGRESSION, PipelineStage.INTEGRATION),
            ("ast validation failed: invalid syntax", RootCause.AST_FAILURE, PipelineStage.REPAIR),
            ("blocked by failed dependency: feat-1", RootCause.DEPENDENCY_BLOCKED, PipelineStage.INTEGRATION),
            ("generation error: model refused", RootCause.GENERATION_ERROR, PipelineStage.OLLAMA_GENERATION),
        ],
    )
    def test_classify_feature_error_patterns(
        self, classifier, error_msg, expected_cause, expected_stage
    ):
        feature_dict = {"error_message": error_msg, "status": "failed"}
        cause, stage = classifier.classify_feature(feature_dict)
        assert cause == expected_cause
        assert stage == expected_stage

    @pytest.mark.parametrize(
        "error_msg, should_match",
        [
            # RUN-011 Gap C: TS231x/232x/234x are real type-class errors → attribute.
            ("synthesize-value-props.ts:273:55 error TS2345: Argument of type "
             "'Set<unknown>' is not assignable to parameter of type 'Set<string>'.", True),
            ("x.ts(1,1): error TS2322: Type 'string' is not assignable to type 'number'.", True),
            ("x.ts(1,1): error TS2314: Generic type requires type arguments.", True),
            # Must NOT match: module-resolution (230x) + target/lib (280x) are
            # handled/stripped elsewhere, not type-class mismatches.
            ("error TS2307: Cannot find module 'zod'", False),
            ("error TS2802: Set can only be iterated with --downlevelIteration", False),
        ],
    )
    def test_classify_type_class_mismatch(self, classifier, error_msg, should_match):
        cause, stage = classifier.classify_feature(
            {"error_message": error_msg, "status": "failed"}
        )
        if should_match:
            assert cause == RootCause.TYPE_CLASS_MISMATCH
            assert stage == PipelineStage.TYPECHECK
        else:
            assert cause != RootCause.TYPE_CLASS_MISMATCH

    def test_classify_feature_blocked_status(self, classifier):
        feature_dict = {"status": "blocked", "error_message": ""}
        cause, stage = classifier.classify_feature(feature_dict)
        assert cause == RootCause.DEPENDENCY_BLOCKED
        assert stage == PipelineStage.INTEGRATION

    def test_classify_feature_unknown(self, classifier):
        feature_dict = {"status": "failed", "error_message": "something weird"}
        cause, stage = classifier.classify_feature(feature_dict)
        assert cause == RootCause.UNKNOWN
        assert stage == PipelineStage.UNKNOWN

    @pytest.mark.parametrize(
        "escalation_reason, expected_cause, expected_stage",
        [
            ("ast_failure", RootCause.AST_FAILURE, PipelineStage.REPAIR),
            ("structural_mismatch", RootCause.SPLICER_MISMATCH, PipelineStage.SPLICER),
            ("tier_too_high", RootCause.TIER_ESCALATION, PipelineStage.CLASSIFICATION),
            ("repair_exhausted", RootCause.REPAIR_EXHAUSTED, PipelineStage.REPAIR),
            ("empty_response", RootCause.OLLAMA_EMPTY_RESPONSE, PipelineStage.OLLAMA_GENERATION),
            ("timeout", RootCause.OLLAMA_TIMEOUT, PipelineStage.OLLAMA_GENERATION),
            ("circuit_breaker", RootCause.OLLAMA_CIRCUIT_BREAKER, PipelineStage.OLLAMA_GENERATION),
        ],
    )
    def test_classify_element_escalation(
        self, classifier, escalation_reason, expected_cause, expected_stage
    ):
        element = {
            "success": False,
            "escalation": {"reason": escalation_reason, "detail": "test"},
        }
        cause, stage = classifier.classify_element(element)
        assert cause == expected_cause
        assert stage == expected_stage

    def test_classify_element_success(self, classifier):
        element = {"success": True}
        cause, stage = classifier.classify_element(element)
        assert cause == RootCause.UNKNOWN
        assert stage == PipelineStage.UNKNOWN

    def test_classify_from_code_duplicate_import(self, classifier):
        code = "import os\nimport os  # F811"
        error = "F811 redefinition of unused 'os'"
        cause, stage = classifier.classify_from_code(code, error)
        assert cause == RootCause.DUPLICATE_IMPORT

    def test_classify_from_code_unfilled_stub(self, classifier):
        code = 'def foo():\n    raise NotImplementedError("stub")'
        cause, stage = classifier.classify_from_code(code)
        assert cause == RootCause.UNFILLED_STUB

    def test_classify_from_code_phantom_import(self, classifier):
        code = "from phantom_lib import helper"
        error = "No module named 'phantom_lib'"
        cause, stage = classifier.classify_from_code(code, error)
        assert cause == RootCause.PHANTOM_IMPORT

    def test_classify_from_code_scope_corruption(self, classifier):
        code = "class Outer:\n class Inner:"
        cause, stage = classifier.classify_from_code(code)
        assert cause == RootCause.SCOPE_CORRUPTION

    def test_classify_from_code_clean(self, classifier):
        code = "def hello():\n    return 'world'"
        cause, stage = classifier.classify_from_code(code)
        assert cause == RootCause.UNKNOWN


# ---------------------------------------------------------------------------
# TestPrimePostMortemEvaluator
# ---------------------------------------------------------------------------


class TestPrimePostMortemEvaluator:
    """Tests for PrimePostMortemEvaluator."""

    @pytest.fixture
    def evaluator(self):
        return PrimePostMortemEvaluator()

    def test_all_succeeded(self, evaluator, tmp_path):
        history = [
            _make_history_entry("feat-1", success=True),
            _make_history_entry("feat-2", success=True),
        ]
        result_dict = _make_result_dict(history)
        queue_state = _make_queue_state({
            "feat-1": {"status": "complete"},
            "feat-2": {"status": "complete"},
        })

        report = evaluator.evaluate(result_dict, queue_state, output_dir=str(tmp_path))

        assert report.total_features == 2
        assert report.successful_features == 2
        assert report.failed_features == 0
        assert report.aggregate_score == 1.0
        assert report.aggregate_verdict == "PASS"

    def test_with_failures(self, evaluator, tmp_path):
        history = [
            _make_history_entry("feat-1", success=True),
            _make_history_entry(
                "feat-2",
                success=False,
                error="F811 redefinition of unused 'os'",
            ),
        ]
        result_dict = _make_result_dict(history)
        queue_state = _make_queue_state({
            "feat-1": {"status": "complete"},
            "feat-2": {
                "status": "failed",
                "error_message": "F811 redefinition of unused 'os'",
            },
        })

        report = evaluator.evaluate(result_dict, queue_state, output_dir=str(tmp_path))

        assert report.total_features == 2
        assert report.successful_features == 1
        assert report.failed_features == 1
        assert report.aggregate_score == 0.5

        failed = [f for f in report.features if not f.success]
        assert len(failed) == 1
        assert failed[0].root_cause == RootCause.DUPLICATE_IMPORT
        assert failed[0].pipeline_stage == PipelineStage.REPAIR

    def test_with_micro_prime_data(self, evaluator, tmp_path):
        gen_meta = {
            "micro_prime_file_results": [
                {
                    "file_path": "src/main.py",
                    "element_results": [
                        {
                            "element_name": "foo",
                            "file_path": "src/main.py",
                            "tier": "simple",
                            "success": True,
                            "template_used": False,
                            "repair_steps_applied": ["fence_strip"],
                            "generation_time_ms": 150.0,
                        },
                        {
                            "element_name": "bar",
                            "file_path": "src/main.py",
                            "tier": "moderate",
                            "success": False,
                            "escalation": {
                                "reason": "repair_exhausted",
                                "detail": "3 attempts",
                            },
                            "repair_steps_applied": [],
                            "generation_time_ms": 500.0,
                        },
                    ],
                }
            ]
        }
        history = [
            _make_history_entry("feat-1", success=False, error="repair exhausted",
                                generation_metadata=gen_meta),
        ]
        result_dict = _make_result_dict(history)
        queue_state = _make_queue_state({
            "feat-1": {"status": "failed", "error_message": "repair exhausted"},
        })

        report = evaluator.evaluate(result_dict, queue_state, output_dir=str(tmp_path))

        assert report.micro_prime_analysis is not None
        mpa = report.micro_prime_analysis
        assert mpa.total_elements == 2
        assert mpa.successful_elements == 1
        assert mpa.escalated_elements == 1
        assert mpa.tier_distribution.get("simple") == 1
        assert mpa.tier_distribution.get("moderate") == 1

    def test_pipeline_attribution(self, evaluator, tmp_path):
        history = [
            _make_history_entry("f1", success=False, error="F811 dup import"),
            _make_history_entry("f2", success=False, error="repair exhausted"),
        ]
        result_dict = _make_result_dict(history)
        queue_state = _make_queue_state({
            "f1": {"status": "failed", "error_message": "F811 dup import"},
            "f2": {"status": "failed", "error_message": "repair exhausted"},
        })

        report = evaluator.evaluate(result_dict, queue_state, output_dir=str(tmp_path))

        assert len(report.pipeline_attribution) >= 1
        # Both should map to REPAIR stage
        repair_attr = [
            a for a in report.pipeline_attribution
            if a.stage == PipelineStage.REPAIR
        ]
        assert len(repair_attr) == 1
        assert repair_attr[0].failure_count == 2

    def test_cross_feature_patterns(self, evaluator, tmp_path):
        history = [
            _make_history_entry("f1", success=False, error="F811 redefinition"),
            _make_history_entry("f2", success=False, error="F811 redefinition"),
            _make_history_entry("f3", success=True),
        ]
        result_dict = _make_result_dict(history)
        queue_state = _make_queue_state({
            "f1": {"status": "failed", "error_message": "F811 redefinition"},
            "f2": {"status": "failed", "error_message": "F811 redefinition"},
            "f3": {"status": "complete"},
        })

        report = evaluator.evaluate(result_dict, queue_state, output_dir=str(tmp_path))

        repeated = [
            p for p in report.cross_feature_patterns
            if p.pattern_type == "repeated_root_cause"
        ]
        assert len(repeated) >= 1
        assert "f1" in repeated[0].affected_features
        assert "f2" in repeated[0].affected_features

    def test_escalation_pattern_subtyped_by_reason(self, evaluator, tmp_path):
        """REQ-KZ-401a: escalation patterns are subtyped and use dual threshold."""
        # Build 4 features with ast_failure escalation across 3 features, 6 elements
        def _elem(esc_reason=""):
            e = {"element_name": "fn", "success": not esc_reason, "tier": "SIMPLE"}
            if esc_reason:
                e["escalation"] = {"reason": esc_reason}
            return e

        def _file_results(elements):
            return {"micro_prime_file_results": [{"file_path": "x.py", "element_results": elements}]}

        history = [
            _make_history_entry("f1", success=True, generation_metadata=_file_results(
                [_elem("ast_failure"), _elem("ast_failure")],
            )),
            _make_history_entry("f2", success=True, generation_metadata=_file_results(
                [_elem("ast_failure"), _elem("ast_failure")],
            )),
            _make_history_entry("f3", success=True, generation_metadata=_file_results(
                [_elem("ast_failure"), _elem("ast_failure")],
            )),
            _make_history_entry("f4", success=True),
        ]
        result_dict = _make_result_dict(history)
        queue_state = _make_queue_state({
            "f1": {"status": "complete"}, "f2": {"status": "complete"},
            "f3": {"status": "complete"}, "f4": {"status": "complete"},
        })

        report = evaluator.evaluate(result_dict, queue_state, output_dir=str(tmp_path))

        esc = [p for p in report.cross_feature_patterns
               if p.pattern_type.startswith("repeated_escalation:")]
        assert len(esc) == 1
        assert esc[0].pattern_type == "repeated_escalation:ast_failure"
        # Frequency = total element escalations (6), not feature count (3)
        assert esc[0].frequency == 6
        assert esc[0].affected_feature_count == 3
        assert set(esc[0].affected_features) == {"f1", "f2", "f3"}

    def test_escalation_below_threshold_suppressed(self, evaluator, tmp_path):
        """REQ-KZ-401a: 2 features with 2 elements should NOT trigger (below threshold)."""
        def _elem(esc_reason=""):
            e = {"name": "fn", "success": not esc_reason, "tier": "SIMPLE"}
            if esc_reason:
                e["escalation"] = {"reason": esc_reason}
            return e

        history = [
            _make_history_entry("f1", success=True, generation_metadata={
                "element_results": [_elem("ast_failure")],
            }),
            _make_history_entry("f2", success=True, generation_metadata={
                "element_results": [_elem("ast_failure")],
            }),
        ]
        result_dict = _make_result_dict(history)
        queue_state = _make_queue_state({
            "f1": {"status": "complete"}, "f2": {"status": "complete"},
        })

        report = evaluator.evaluate(result_dict, queue_state, output_dir=str(tmp_path))

        esc = [p for p in report.cross_feature_patterns
               if p.pattern_type.startswith("repeated_escalation:")]
        assert len(esc) == 0  # Below both thresholds

    def test_per_feature_error_guard(self, evaluator, tmp_path):
        """A feature that raises during evaluation should not crash the report."""
        history = [
            _make_history_entry("good", success=True),
            _make_history_entry("bad", success=False),
        ]
        result_dict = _make_result_dict(history)
        # Deliberately malformed queue state for 'bad'
        queue_state = {
            "good": {"id": "good", "name": "Good", "status": "complete"},
            "bad": None,  # Will cause AttributeError in _evaluate_feature
        }

        # Should not raise
        report = evaluator.evaluate(result_dict, queue_state, output_dir=str(tmp_path))
        assert report.total_features == 2

    def test_unprocessed_features_excluded(self, evaluator, tmp_path):
        """Features in queue but not in history should not be evaluated."""
        history = [
            _make_history_entry("feat-1", success=True),
        ]
        result_dict = _make_result_dict(history)
        # Queue has 3 features but only 1 was processed
        queue_state = _make_queue_state({
            "feat-1": {"status": "complete"},
            "feat-2": {"status": "pending"},
            "feat-3": {"status": "pending"},
        })

        report = evaluator.evaluate(result_dict, queue_state, output_dir=str(tmp_path))

        assert report.total_features == 1
        assert report.successful_features == 1
        assert report.aggregate_score == 1.0
        assert report.aggregate_verdict == "PASS"

    def test_write_outputs(self, evaluator, tmp_path):
        history = [_make_history_entry("feat-1", success=True)]
        result_dict = _make_result_dict(history)
        queue_state = _make_queue_state({"feat-1": {"status": "complete"}})

        evaluator.evaluate(result_dict, queue_state, output_dir=str(tmp_path))

        assert (tmp_path / "prime-postmortem-report.json").is_file()
        assert (tmp_path / "prime-postmortem-summary.md").is_file()

        # Verify JSON is valid
        report_json = json.loads(
            (tmp_path / "prime-postmortem-report.json").read_text()
        )
        assert report_json["aggregate_verdict"] == "PASS"

    def test_empty_history(self, evaluator, tmp_path):
        result_dict = _make_result_dict([])
        queue_state = _make_queue_state({})

        report = evaluator.evaluate(result_dict, queue_state, output_dir=str(tmp_path))

        assert report.total_features == 0
        assert report.aggregate_score == 0.0

    def test_cost_outlier_pattern(self, evaluator, tmp_path):
        history = [
            _make_history_entry("cheap-1", success=True, cost_usd=0.001),
            _make_history_entry("cheap-2", success=True, cost_usd=0.001),
            _make_history_entry("expensive", success=True, cost_usd=0.01),
        ]
        result_dict = _make_result_dict(history)
        queue_state = _make_queue_state({
            "cheap-1": {"status": "complete"},
            "cheap-2": {"status": "complete"},
            "expensive": {"status": "complete"},
        })

        report = evaluator.evaluate(result_dict, queue_state, output_dir=str(tmp_path))

        cost_patterns = [
            p for p in report.cross_feature_patterns
            if p.pattern_type == "cost_outlier"
        ]
        assert len(cost_patterns) == 1
        assert "expensive" in cost_patterns[0].affected_features


# ---------------------------------------------------------------------------
# TestLaunchPrimePostmortemAsync
# ---------------------------------------------------------------------------


class TestLaunchPrimePostmortemAsync:
    """Tests for the async launcher."""

    def test_thread_completes(self, tmp_path):
        history = [_make_history_entry("feat-1", success=True)]
        result_dict = _make_result_dict(history)

        queue = MagicMock()
        queue.features = {
            "feat-1": MagicMock(
                to_dict=MagicMock(return_value={
                    "id": "feat-1", "name": "Feat 1", "status": "complete",
                    "error_message": "", "target_files": [], "generated_files": [],
                    "dependencies": [], "metadata": {},
                })
            ),
        }

        thread = launch_prime_postmortem_async(
            result_dict=result_dict,
            queue=queue,
            output_dir=str(tmp_path),
        )
        thread.join(timeout=10)

        assert not thread.is_alive()
        assert (tmp_path / "prime-postmortem-report.json").is_file()

    def test_failure_logged_not_raised(self, tmp_path):
        """Errors inside the thread should be logged, not propagated."""
        result_dict = {"history": [{"feature_id": "x", "success": True, "cost_usd": 0}]}
        queue = MagicMock()
        queue.features = {}

        # Should not raise even with minimal/broken inputs
        thread = launch_prime_postmortem_async(
            result_dict=result_dict,
            queue=queue,
            output_dir=str(tmp_path),
        )
        thread.join(timeout=10)
        assert not thread.is_alive()

    def test_deep_copies_result(self, tmp_path):
        """Verify result_dict is deep-copied (caller can mutate after launch)."""
        history = [_make_history_entry("feat-1", success=True)]
        result_dict = _make_result_dict(history)

        queue = MagicMock()
        queue.features = {}

        thread = launch_prime_postmortem_async(
            result_dict=result_dict,
            queue=queue,
            output_dir=str(tmp_path),
        )

        # Mutate original after launch — should not affect thread
        result_dict["history"].clear()
        thread.join(timeout=10)
        assert not thread.is_alive()

    def test_with_seed_path(self, tmp_path):
        """Verify seed_path is loaded for requirement matching."""
        seed_data = {
            "tasks": [
                {
                    "task_id": "feat-1",
                    "title": "Test Feature",
                    "config": {"task_description": "Build a test"},
                }
            ]
        }
        seed_file = tmp_path / "seed.json"
        seed_file.write_text(json.dumps(seed_data))

        history = [_make_history_entry("feat-1", success=True)]
        result_dict = _make_result_dict(history)

        queue = MagicMock()
        queue.features = {
            "feat-1": MagicMock(
                to_dict=MagicMock(return_value={
                    "id": "feat-1", "name": "Test", "status": "complete",
                    "error_message": "", "target_files": [], "generated_files": [],
                    "dependencies": [], "metadata": {},
                })
            ),
        }

        thread = launch_prime_postmortem_async(
            result_dict=result_dict,
            queue=queue,
            seed_path=str(seed_file),
            output_dir=str(tmp_path),
        )
        thread.join(timeout=10)
        assert not thread.is_alive()
        assert (tmp_path / "prime-postmortem-report.json").is_file()


# ---------------------------------------------------------------------------
# TestMissingFilesPathNormalization
# ---------------------------------------------------------------------------


class TestMissingFilesPathNormalization:
    """Verify missing_files handles absolute-vs-relative path comparison."""

    def _evaluate(self, queue_state, result_dict):
        evaluator = PrimePostMortemEvaluator()
        return evaluator.evaluate(result_dict, queue_state)

    def test_absolute_generated_matches_relative_target(self):
        """Generated file with absolute path should match relative target."""
        queue_state = _make_queue_state({
            "feat-1": {
                "target_files": ["src/emailservice/email_server.py"],
                "generated_files": [
                    "/abs/path/to/generated/src/emailservice/email_server.py"
                ],
            },
        })
        result_dict = _make_result_dict(
            history=[_make_history_entry("feat-1", success=True)]
        )
        report = self._evaluate(queue_state, result_dict)
        feat = report.features[0]
        assert feat.missing_files == [], (
            f"Expected no missing files but got {feat.missing_files}"
        )

    def test_exact_match_still_works(self):
        """Identical relative paths should still match."""
        queue_state = _make_queue_state({
            "feat-1": {
                "target_files": ["src/app.py"],
                "generated_files": ["src/app.py"],
            },
        })
        result_dict = _make_result_dict(
            history=[_make_history_entry("feat-1", success=True)]
        )
        report = self._evaluate(queue_state, result_dict)
        assert report.features[0].missing_files == []

    def test_genuinely_missing_file_still_detected(self):
        """A file not present in generated_files should still be reported."""
        queue_state = _make_queue_state({
            "feat-1": {
                "target_files": ["src/missing.py", "src/present.py"],
                "generated_files": [
                    "/abs/generated/src/present.py"
                ],
            },
        })
        result_dict = _make_result_dict(
            history=[_make_history_entry("feat-1", success=True)]
        )
        report = self._evaluate(queue_state, result_dict)
        assert report.features[0].missing_files == ["src/missing.py"]

    def test_no_false_match_on_partial_suffix(self):
        """'ice.py' should not match 'service.py'."""
        queue_state = _make_queue_state({
            "feat-1": {
                "target_files": ["ice.py"],
                "generated_files": ["/abs/path/service.py"],
            },
        })
        result_dict = _make_result_dict(
            history=[_make_history_entry("feat-1", success=True)]
        )
        report = self._evaluate(queue_state, result_dict)
        assert report.features[0].missing_files == ["ice.py"]
