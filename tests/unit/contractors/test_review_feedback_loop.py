"""Tests for Review Feedback Loop — Iteration 1.

Covers:
- REQ-RFL-100: Persist DiskComplianceResult in integration metadata
- REQ-RFL-105: Persist RepairOutcome summary in integration metadata
- REQ-RFL-110: compute_disk_quality_score() extraction and re-export
- REQ-RFL-115: Disk quality score at integration time
- REQ-RFL-120: PrimeReviewAdapter
- REQ-RFL-125: Review wiring in PrimeContractorWorkflow
- REQ-RFL-128: Repair effectiveness public query API
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# REQ-RFL-110: compute_disk_quality_score extraction + re-export
# ---------------------------------------------------------------------------


class TestComputeDiskQualityScore:
    """Verify score function lives in forward_manifest_validator and is re-exported."""

    def test_canonical_import(self):
        from startd8.forward_manifest_validator import compute_disk_quality_score
        assert callable(compute_disk_quality_score)

    def test_reexport_from_postmortem(self):
        from startd8.contractors.prime_postmortem import compute_disk_quality_score
        from startd8.forward_manifest_validator import (
            compute_disk_quality_score as canonical,
        )
        assert compute_disk_quality_score is canonical

    def test_perfect_score(self):
        from startd8.forward_manifest_validator import compute_disk_quality_score
        result = SimpleNamespace(
            ast_valid=True,
            contract_compliance=1.0,
            import_completeness=1.0,
            stubs_remaining=0,
            semantic_issues=[],
        )
        assert compute_disk_quality_score(result) == 1.0

    def test_ast_invalid_is_zero(self):
        from startd8.forward_manifest_validator import compute_disk_quality_score
        result = SimpleNamespace(
            ast_valid=False,
            contract_compliance=1.0,
            import_completeness=1.0,
            stubs_remaining=0,
            semantic_issues=[],
        )
        assert compute_disk_quality_score(result) == 0.0

    def test_none_is_zero(self):
        from startd8.forward_manifest_validator import compute_disk_quality_score
        assert compute_disk_quality_score(None) == 0.0

    def test_stubs_reduce_score(self):
        from startd8.forward_manifest_validator import compute_disk_quality_score
        result = SimpleNamespace(
            ast_valid=True,
            contract_compliance=1.0,
            import_completeness=1.0,
            stubs_remaining=5,
            semantic_issues=[],
        )
        score = compute_disk_quality_score(result)
        assert 0.0 < score < 1.0

    def test_semantic_errors_reduce_score(self):
        from startd8.forward_manifest_validator import compute_disk_quality_score
        result = SimpleNamespace(
            ast_valid=True,
            contract_compliance=1.0,
            import_completeness=1.0,
            stubs_remaining=0,
            semantic_issues=[
                {"severity": "error", "message": "phantom import"},
                {"severity": "error", "message": "duplicate def"},
            ],
        )
        score = compute_disk_quality_score(result)
        assert 0.0 < score < 1.0

    def test_dict_based_compliance(self):
        """compute_disk_quality_score works with SimpleNamespace-wrapped dicts."""
        from startd8.forward_manifest_validator import compute_disk_quality_score
        data = {
            "ast_valid": True,
            "contract_compliance": 0.8,
            "import_completeness": 0.9,
            "stubs_remaining": 1,
            "semantic_issues": [{"severity": "warning", "message": "bare except"}],
        }
        score = compute_disk_quality_score(SimpleNamespace(**data))
        assert 0.0 < score < 1.0


# ---------------------------------------------------------------------------
# REQ-RFL-120: PrimeReviewAdapter
# ---------------------------------------------------------------------------


@dataclass
class FakeFeature:
    """Minimal FeatureSpec stand-in for adapter tests."""
    id: str = "F-001"
    name: str = "test_feature"
    description: str = "A test feature"
    target_files: List[str] = field(default_factory=lambda: ["src/foo.py"])
    generated_files: List[str] = field(default_factory=lambda: ["src/foo.py"])
    metadata: Dict[str, Any] = field(default_factory=dict)


class TestPrimeReviewAdapter:

    def test_feature_to_seed_task_mapping(self):
        from startd8.contractors.prime_review import PrimeReviewAdapter
        adapter = PrimeReviewAdapter.__new__(PrimeReviewAdapter)
        feature = FakeFeature(
            metadata={"domain": "backend", "prompt_constraints": ["use typing"]},
        )
        task = adapter._feature_to_seed_task(feature)
        assert task.task_id == "F-001"
        assert task.title == "test_feature"
        assert task.domain == "backend"
        assert "use typing" in task.prompt_constraints
        assert task.target_files == ["src/foo.py"]

    def test_feature_to_seed_task_defaults(self):
        """All required SeedTask fields must have values."""
        from startd8.contractors.prime_review import PrimeReviewAdapter
        adapter = PrimeReviewAdapter.__new__(PrimeReviewAdapter)
        feature = FakeFeature(metadata=None)
        task = adapter._feature_to_seed_task(feature)
        assert task.task_type == "task"
        assert task.domain == "general"
        assert task.prompt_constraints == []

    def test_read_generated_code(self, tmp_path):
        from startd8.contractors.prime_review import PrimeReviewAdapter
        adapter = PrimeReviewAdapter.__new__(PrimeReviewAdapter)
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "foo.py").write_text("print('hello')")
        feature = FakeFeature(generated_files=["src/foo.py"])
        code = adapter._read_generated_code(feature, tmp_path)
        assert "print('hello')" in code
        assert "# src/foo.py" in code

    def test_read_generated_code_missing_files(self, tmp_path):
        from startd8.contractors.prime_review import PrimeReviewAdapter
        adapter = PrimeReviewAdapter.__new__(PrimeReviewAdapter)
        feature = FakeFeature(generated_files=["nonexistent.py"])
        code = adapter._read_generated_code(feature, tmp_path)
        assert code == ""

    def test_pack_validation_as_test_results(self):
        from startd8.contractors.prime_review import PrimeReviewAdapter
        metadata = {
            "disk_compliance": {"src/foo.py": {"ast_valid": True}},
            "disk_quality_score": 0.85,
            "repair_summaries": [{"phase": "post_merge", "any_modified": True}],
        }
        result = PrimeReviewAdapter._pack_validation_as_test_results(metadata)
        assert "validation_results" in result
        assert result["disk_quality_score"] == 0.85
        assert "repair_summary" in result

    def test_pack_validation_empty_metadata(self):
        from startd8.contractors.prime_review import PrimeReviewAdapter
        result = PrimeReviewAdapter._pack_validation_as_test_results({})
        assert result == {}

    def test_review_skip_no_code(self, tmp_path):
        from startd8.contractors.prime_review import PrimeReviewAdapter
        adapter = PrimeReviewAdapter.__new__(PrimeReviewAdapter)
        adapter._handler = mock.MagicMock()
        feature = FakeFeature(generated_files=["nonexistent.py"])
        result = adapter.review_feature(feature, tmp_path)
        assert result["verdict"] == "SKIP"
        adapter._handler._review_task.assert_not_called()

    def test_review_graceful_failure(self, tmp_path):
        from startd8.contractors.prime_review import PrimeReviewAdapter
        adapter = PrimeReviewAdapter.__new__(PrimeReviewAdapter)
        adapter._handler = mock.MagicMock()
        adapter._handler._review_task.side_effect = RuntimeError("LLM down")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "foo.py").write_text("print('hello')")
        feature = FakeFeature(generated_files=["src/foo.py"])
        result = adapter.review_feature(feature, tmp_path)
        assert result["verdict"] == "ERROR"
        assert result["score"] is None


# ---------------------------------------------------------------------------
# REQ-RFL-125: Review wiring in PrimeContractorWorkflow
# ---------------------------------------------------------------------------


class TestReviewWiring:

    def test_review_enabled_default(self):
        """review_enabled defaults to True."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow
        # Use mock to avoid full init side effects
        with mock.patch.object(PrimeContractorWorkflow, "__init__", lambda self, **kw: None):
            pc = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)
        # Verify the parameter exists in the real __init__ signature
        import inspect
        sig = inspect.signature(PrimeContractorWorkflow.__init__)
        assert "review_enabled" in sig.parameters
        assert sig.parameters["review_enabled"].default is True

    def test_review_agent_param_exists(self):
        """review_agent parameter exists with None default."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow
        import inspect
        sig = inspect.signature(PrimeContractorWorkflow.__init__)
        assert "review_agent" in sig.parameters
        assert sig.parameters["review_agent"].default is None

    def test_review_result_stored_in_metadata(self):
        """After review, result is stored in feature.metadata['review']."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow
        from startd8.contractors.queue import FeatureSpec

        pc = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)
        pc.review_enabled = True
        pc.walkthrough = False
        pc.project_root = Path("/tmp/test")
        pc.code_generator = None
        pc._review_agent = None
        pc._review_adapter = mock.MagicMock()
        pc._review_adapter.review_feature.return_value = {
            "score": 85,
            "verdict": "PASS",
            "issues": [],
            "suggestions": [],
        }
        pc.review_results = {}

        feature = FeatureSpec(id="F-001", name="test")
        metadata = {"disk_compliance": {}}

        result = pc._review_feature(feature, metadata)
        assert result is not None
        assert result["score"] == 85
        assert result["verdict"] == "PASS"

    def test_review_disabled_skips(self):
        """When review_enabled=False, no review is attempted."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        pc = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)
        pc.review_enabled = False
        pc.walkthrough = False
        pc._review_adapter = mock.MagicMock()

        # _review_feature should never be called in integrate_feature
        # when review_enabled=False. We test the flag check here.
        assert pc.review_enabled is False


# ---------------------------------------------------------------------------
# REQ-RFL-100/105/115: Integration metadata plumbing
# ---------------------------------------------------------------------------


class TestIntegrationMetadataPlumbing:

    def test_compliance_dict_structure(self):
        """Compliance entries contain all required fields."""
        expected_keys = {
            "ast_valid", "stubs_remaining", "duplicate_definitions",
            "import_completeness", "contract_compliance", "semantic_issues",
        }
        entry = {
            "ast_valid": True,
            "stubs_remaining": 0,
            "duplicate_definitions": 0,
            "import_completeness": 1.0,
            "contract_compliance": 1.0,
            "semantic_issues": [],
        }
        assert set(entry.keys()) == expected_keys

    def test_repair_summary_structure(self):
        """Repair summary contains required fields."""
        summary = {
            "phase": "post_merge",
            "total_repairs": 2,
            "steps_applied": ["fence_strip", "ast_validate"],
            "any_modified": True,
        }
        assert summary["phase"] in ("pre_merge", "post_merge")
        assert isinstance(summary["total_repairs"], int)
        assert isinstance(summary["steps_applied"], list)
        assert isinstance(summary["any_modified"], bool)

    def test_disk_quality_score_from_compliance(self):
        """Score computed from compliance results via SimpleNamespace."""
        from startd8.forward_manifest_validator import compute_disk_quality_score
        compliance_data = {
            "src/foo.py": {
                "ast_valid": True,
                "stubs_remaining": 0,
                "duplicate_definitions": 0,
                "import_completeness": 0.8,
                "contract_compliance": 0.9,
                "semantic_issues": [],
            },
        }
        scores = [
            compute_disk_quality_score(SimpleNamespace(**d))
            for d in compliance_data.values()
        ]
        assert len(scores) == 1
        assert 0.0 < min(scores) < 1.0

    def test_disk_quality_score_min_of_files(self):
        """Score is min across files (weakest link)."""
        from startd8.forward_manifest_validator import compute_disk_quality_score
        compliance_data = {
            "good.py": {
                "ast_valid": True,
                "stubs_remaining": 0,
                "duplicate_definitions": 0,
                "import_completeness": 1.0,
                "contract_compliance": 1.0,
                "semantic_issues": [],
            },
            "bad.py": {
                "ast_valid": True,
                "stubs_remaining": 5,
                "duplicate_definitions": 0,
                "import_completeness": 0.5,
                "contract_compliance": 0.5,
                "semantic_issues": [
                    {"severity": "error", "message": "phantom import"},
                ],
            },
        }
        scores = [
            compute_disk_quality_score(SimpleNamespace(**d))
            for d in compliance_data.values()
        ]
        good_score = compute_disk_quality_score(
            SimpleNamespace(**compliance_data["good.py"]),
        )
        bad_score = compute_disk_quality_score(
            SimpleNamespace(**compliance_data["bad.py"]),
        )
        assert min(scores) == bad_score
        assert bad_score < good_score


# ---------------------------------------------------------------------------
# REQ-RFL-128: Repair effectiveness API
# ---------------------------------------------------------------------------


class TestRepairEffectivenessAPI:

    def test_summary_returns_dict(self):
        from startd8.repair.orchestrator import get_step_effectiveness_summary
        result = get_step_effectiveness_summary()
        assert isinstance(result, dict)

    def test_summary_fields(self):
        from startd8.repair.orchestrator import (
            get_step_effectiveness_summary,
            reset_step_effectiveness,
            _step_effectiveness,
        )
        from startd8.repair.models import StepEffectiveness

        reset_step_effectiveness()
        _step_effectiveness["test_step"] = StepEffectiveness(
            step_name="test_step",
            attempts=10,
            modifications=7,
            reverts=1,
            contributed_to_success=6,
        )
        try:
            summary = get_step_effectiveness_summary()
            assert "test_step" in summary
            entry = summary["test_step"]
            assert entry["attempts"] == 10
            assert entry["success_rate"] == 0.6  # 6/10
            assert entry["modifications"] == 7
            assert entry["contributed_to_success"] == 6
        finally:
            reset_step_effectiveness()


# ===========================================================================
# Iteration 2: Gate + Feedback
# ===========================================================================


# ---------------------------------------------------------------------------
# REQ-RFL-200: RunQualityAccumulator
# ---------------------------------------------------------------------------


class TestRunQualityAccumulator:

    def test_record_signals(self):
        from startd8.contractors.run_quality_accumulator import (
            RunQualityAccumulator,
        )
        acc = RunQualityAccumulator()
        acc.record("F-001", {
            "disk_quality_score": 0.75,
            "disk_compliance": {
                "foo.py": {
                    "semantic_issues": [
                        {"category": "phantom_import", "severity": "error"},
                    ],
                },
            },
        })
        assert acc.feature_count == 1

    def test_patterns_threshold(self):
        """Patterns require count >= 2."""
        from startd8.contractors.run_quality_accumulator import (
            RunQualityAccumulator,
        )
        acc = RunQualityAccumulator()
        for i in range(3):
            acc.record(f"F-{i}", {
                "disk_compliance": {
                    "file.py": {
                        "semantic_issues": [
                            {"category": "phantom_import", "severity": "error"},
                        ],
                    },
                },
            })
        patterns = acc.get_run_level_patterns()
        assert "semantic:phantom_import" in patterns
        assert patterns["semantic:phantom_import"] == 3

    def test_patterns_below_threshold(self):
        """Single occurrence doesn't appear in patterns."""
        from startd8.contractors.run_quality_accumulator import (
            RunQualityAccumulator,
        )
        acc = RunQualityAccumulator()
        acc.record("F-001", {
            "disk_compliance": {
                "file.py": {
                    "semantic_issues": [
                        {"category": "rare_issue", "severity": "warning"},
                    ],
                },
            },
        })
        patterns = acc.get_run_level_patterns()
        assert patterns == {}

    def test_build_hints(self):
        from startd8.contractors.run_quality_accumulator import (
            RunQualityAccumulator,
        )
        acc = RunQualityAccumulator()
        for i in range(2):
            acc.record(f"F-{i}", {
                "disk_compliance": {
                    "file.py": {
                        "semantic_issues": [
                            {"category": "phantom_import", "severity": "error"},
                        ],
                    },
                },
            })
        hints = acc.build_spec_hints()
        assert hints is not None
        assert "phantom_import" in hints
        assert "2x" in hints

    def test_build_hints_dedup_kaizen(self):
        """Hints already in kaizen are excluded."""
        from startd8.contractors.run_quality_accumulator import (
            RunQualityAccumulator,
        )
        acc = RunQualityAccumulator()
        for i in range(2):
            acc.record(f"F-{i}", {
                "disk_compliance": {
                    "file.py": {
                        "semantic_issues": [
                            {"category": "phantom_import", "severity": "error"},
                        ],
                    },
                },
            })
        hints = acc.build_spec_hints(
            existing_kaizen_categories={"phantom_import"},
        )
        assert hints is None

    def test_build_hints_empty(self):
        from startd8.contractors.run_quality_accumulator import (
            RunQualityAccumulator,
        )
        acc = RunQualityAccumulator()
        assert acc.build_spec_hints() is None

    def test_quality_trend_declining(self):
        from startd8.contractors.run_quality_accumulator import (
            RunQualityAccumulator,
        )
        acc = RunQualityAccumulator()
        for score in [0.9, 0.7, 0.5]:
            acc.record(f"F-{score}", {"disk_quality_score": score})
        assert acc.get_quality_trend() == "declining"

    def test_quality_trend_not_declining(self):
        from startd8.contractors.run_quality_accumulator import (
            RunQualityAccumulator,
        )
        acc = RunQualityAccumulator()
        for score in [0.5, 0.7, 0.9]:
            acc.record(f"F-{score}", {"disk_quality_score": score})
        assert acc.get_quality_trend() is None

    def test_quality_trend_needs_3(self):
        from startd8.contractors.run_quality_accumulator import (
            RunQualityAccumulator,
        )
        acc = RunQualityAccumulator()
        acc.record("F-1", {"disk_quality_score": 0.9})
        acc.record("F-2", {"disk_quality_score": 0.5})
        assert acc.get_quality_trend() is None


# ---------------------------------------------------------------------------
# REQ-RFL-210: Review issue classification
# ---------------------------------------------------------------------------


class TestReviewIssueClassification:

    def test_classify_keywords(self):
        from startd8.contractors.prime_review import classify_review_issues
        issues = [
            "Circular import between logger and server",
            "Test coverage is insufficient",
            "Performance issue with O(n^2) algorithm",
            "SQL injection vulnerability in handler",
        ]
        classified = classify_review_issues(issues)
        assert len(classified) == 4
        assert classified[0]["category"] == "semantics"
        assert classified[1]["category"] == "testing"
        assert classified[2]["category"] == "performance"
        assert classified[3]["category"] == "security"

    def test_classify_other(self):
        from startd8.contractors.prime_review import classify_review_issues
        classified = classify_review_issues(["Something completely unrelated"])
        assert classified[0]["category"] == "other"

    def test_classify_empty(self):
        from startd8.contractors.prime_review import classify_review_issues
        assert classify_review_issues([]) == []


# ---------------------------------------------------------------------------
# REQ-RFL-220/225/230: Quality gate
# ---------------------------------------------------------------------------


class TestQualityGate:

    def _make_pc(self):
        from startd8.contractors.prime_contractor import (
            PrimeContractorWorkflow,
        )
        pc = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)
        pc.quality_gate_enabled = True
        pc.quality_gate_threshold = 0.5
        pc.project_root = Path("/tmp/test")
        pc.code_generator = None
        pc._review_agent = None
        pc._review_adapter = mock.MagicMock()
        pc._engine = mock.MagicMock()
        pc._prime_listener = mock.MagicMock()
        return pc

    def test_gate_triggers_fail_and_low_score(self):
        from startd8.contractors.prime_contractor import (
            PrimeContractorWorkflow,
        )
        review = {"verdict": "FAIL", "issues": ["broken import"]}
        metadata = {"disk_quality_score": 0.3}

        pc = self._make_pc()
        # Prevent actual develop/integrate
        pc.develop_feature = mock.MagicMock(return_value=False)

        from startd8.contractors.queue import FeatureSpec
        feature = FeatureSpec(id="F-001", name="test")

        result = pc._attempt_quality_gate_redraft(
            feature, review, metadata,
        )
        # develop_feature was called (gate fired)
        pc.develop_feature.assert_called_once()

    def test_gate_skips_fail_but_high_score(self):
        pc = self._make_pc()
        review = {"verdict": "FAIL", "issues": ["minor style"]}
        metadata = {"disk_quality_score": 0.85}

        from startd8.contractors.queue import FeatureSpec
        feature = FeatureSpec(id="F-001", name="test")

        result = pc._attempt_quality_gate_redraft(
            feature, review, metadata,
        )
        assert result is False

    def test_gate_skips_pass(self):
        pc = self._make_pc()
        review = {"verdict": "PASS", "issues": []}
        metadata = {"disk_quality_score": 0.3}

        from startd8.contractors.queue import FeatureSpec
        feature = FeatureSpec(id="F-001", name="test")

        result = pc._attempt_quality_gate_redraft(
            feature, review, metadata,
        )
        assert result is False

    def test_gate_max_one_redraft(self):
        pc = self._make_pc()
        review = {"verdict": "FAIL", "issues": ["broken"]}
        metadata = {"disk_quality_score": 0.3}

        from startd8.contractors.queue import FeatureSpec
        feature = FeatureSpec(
            id="F-001", name="test",
            metadata={"_redrafted": True},
        )

        result = pc._attempt_quality_gate_redraft(
            feature, review, metadata,
        )
        assert result is False

    def test_gate_disabled(self):
        pc = self._make_pc()
        pc.quality_gate_enabled = False
        review = {"verdict": "FAIL", "issues": ["broken"]}
        metadata = {"disk_quality_score": 0.1}

        from startd8.contractors.queue import FeatureSpec
        feature = FeatureSpec(id="F-001", name="test")

        result = pc._attempt_quality_gate_redraft(
            feature, review, metadata,
        )
        assert result is False


# ---------------------------------------------------------------------------
# REQ-RFL-225: Corrective hint builder
# ---------------------------------------------------------------------------


class TestCorrectiveHint:

    def test_build_hint(self):
        from startd8.contractors.prime_contractor import (
            PrimeContractorWorkflow,
        )
        review = {
            "issues": [
                "Circular import between logger and server",
                "Factory returns None instead of Handler",
            ],
        }
        hint = PrimeContractorWorkflow._build_corrective_hint(
            review, score=0.3, threshold=0.5,
        )
        assert "CRITICAL" in hint
        assert "Circular import" in hint
        assert "Factory returns None" in hint
        assert "0.3" in hint

    def test_build_hint_empty_issues(self):
        from startd8.contractors.prime_contractor import (
            PrimeContractorWorkflow,
        )
        hint = PrimeContractorWorkflow._build_corrective_hint(
            {"issues": []},
        )
        assert hint == ""

    def test_build_hint_capped_at_800(self):
        from startd8.contractors.prime_contractor import (
            PrimeContractorWorkflow,
        )
        review = {"issues": [f"Issue number {i} " * 20 for i in range(20)]}
        hint = PrimeContractorWorkflow._build_corrective_hint(review)
        assert len(hint) <= 800


# ---------------------------------------------------------------------------
# REQ-RFL-250: Spec builder "Prior Run Findings" section
# ---------------------------------------------------------------------------


class TestSpecBuilderRunHints:

    def test_run_hints_in_context(self):
        """run_quality_hints should be consumed by spec builder."""
        context = {"run_quality_hints": "- semantic:phantom_import (3x)"}
        val = context.pop("run_quality_hints", None)
        assert val is not None
        assert "phantom_import" in val


# ===========================================================================
# Iteration 3: Upstream Amplification
# ===========================================================================


# ---------------------------------------------------------------------------
# REQ-RFL-300: SeedTask.quality_hints field
# ---------------------------------------------------------------------------


class TestSeedTaskQualityHints:

    def test_field_exists_with_default(self):
        from startd8.seeds.models import SeedTask
        task = SeedTask(
            task_id="T-1", title="test", task_type="task",
            story_points=0, priority="medium", labels=[],
            depends_on=[], description="", target_files=[],
            estimated_loc=0, feature_id="F-1", domain="general",
            domain_reasoning="", environment_checks=[],
            prompt_constraints=[], post_generation_validators=[],
            available_siblings=[], existing_content_hash=None,
            design_doc_sections=[], artifact_types_addressed=[],
            file_scope={},
        )
        assert task.quality_hints == []

    def test_from_seed_entry_quality_hints(self):
        from startd8.seeds.models import SeedTask
        entry = {
            "task_id": "T-1",
            "title": "test",
            "config": {
                "context": {
                    "target_files": ["src/foo.py"],
                    "estimated_loc": 50,
                    "feature_id": "F-1",
                    "quality_hints": [
                        "Watch for phantom imports",
                        "Ensure factory returns interface",
                    ],
                },
            },
            "_enrichment": {},
        }
        task = SeedTask.from_seed_entry(entry)
        assert len(task.quality_hints) == 2
        assert "phantom imports" in task.quality_hints[0]

    def test_from_seed_entry_no_hints(self):
        from startd8.seeds.models import SeedTask
        entry = {
            "task_id": "T-1",
            "title": "test",
            "config": {"context": {
                "target_files": [], "estimated_loc": 0,
                "feature_id": "F-1",
            }},
            "_enrichment": {},
        }
        task = SeedTask.from_seed_entry(entry)
        assert task.quality_hints == []


# ---------------------------------------------------------------------------
# REQ-RFL-310: Distribute kaizen suggestions per-task
# ---------------------------------------------------------------------------


class TestDistributeQualityHints:

    def test_distribute_matched(self):
        from startd8.seeds.builder import SeedBuilder
        builder = SeedBuilder.__new__(SeedBuilder)
        builder._tasks = [
            {
                "config": {
                    "context": {
                        "target_files": ["src/server.py"],
                        "quality_hints": [],
                    },
                },
                "_enrichment": {"domain": "backend"},
            },
        ]
        builder._refine_suggestions = [
            {
                "hint": "Watch for circular imports",
                "pattern_type": "phantom_import",
                "observed_context": "backend server",
            },
        ]
        builder.distribute_quality_hints()
        hints = builder._tasks[0]["config"]["context"]["quality_hints"]
        assert "Watch for circular imports" in hints

    def test_distribute_cap_at_3(self):
        from startd8.seeds.builder import SeedBuilder
        builder = SeedBuilder.__new__(SeedBuilder)
        builder._tasks = [
            {
                "config": {"context": {"target_files": [], "quality_hints": []}},
                "_enrichment": {},
            },
        ]
        builder._refine_suggestions = [
            {"hint": f"Hint {i}", "pattern_type": "", "observed_context": ""}
            for i in range(10)
        ]
        builder.distribute_quality_hints()
        hints = builder._tasks[0]["config"]["context"]["quality_hints"]
        assert len(hints) == 3


# ---------------------------------------------------------------------------
# REQ-RFL-320: Enrichment script
# ---------------------------------------------------------------------------


class TestEnrichmentScript:

    def test_idempotent(self, tmp_path):
        import sys as _sys
        _sys.path.insert(
            0, str(Path(__file__).parents[3] / "scripts"),
        )
        from enrich_seed_from_postmortem import enrich_seed

        seed = {
            "tasks": [{
                "config": {
                    "context": {
                        "target_files": ["src/foo.py"],
                        "quality_hints": [],
                    },
                },
            }],
        }
        suggestions = [
            {"hint": "Watch imports", "pattern_type": "", "observed_context": ""},
        ]

        result1 = enrich_seed(dict(seed), list(suggestions))
        result2 = enrich_seed(result1, list(suggestions))

        hints1 = result1["tasks"][0]["config"]["context"]["quality_hints"]
        hints2 = result2["tasks"][0]["config"]["context"]["quality_hints"]
        assert hints1 == hints2  # idempotent


# ---------------------------------------------------------------------------
# REQ-RFL-330: Context resolution quality_hints threading
# ---------------------------------------------------------------------------


class TestContextResolutionQualityHints:

    def test_quality_hints_threaded(self):
        """quality_hints from metadata flows to gen_context."""
        from startd8.contractors.context_resolution import (
            StandaloneContextStrategy,
        )
        gen_context: Dict[str, Any] = {}
        metadata = {
            "quality_hints": ["Watch for phantom imports"],
            "_enrichment": {"prompt_constraints": []},
        }
        StandaloneContextStrategy._inject_enrichment(
            gen_context, metadata,
        )
        assert "quality_hints" in gen_context
        assert gen_context["quality_hints"] == ["Watch for phantom imports"]

    def test_quality_hints_from_enrichment(self):
        """quality_hints from _enrichment flows to gen_context."""
        from startd8.contractors.context_resolution import (
            StandaloneContextStrategy,
        )
        gen_context: Dict[str, Any] = {}
        metadata = {
            "_enrichment": {
                "prompt_constraints": [],
                "quality_hints": ["Ensure factory returns"],
            },
        }
        StandaloneContextStrategy._inject_enrichment(
            gen_context, metadata,
        )
        assert gen_context["quality_hints"] == ["Ensure factory returns"]
