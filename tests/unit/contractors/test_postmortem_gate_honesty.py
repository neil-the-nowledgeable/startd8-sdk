"""F-3 gate-honesty fixes (strtd8 RUN-006/RUN-008 evidence).

RUN-006 scored PASS / 1.00 with 0 of 1 features successful: the failed feature generated
nothing, so disk validation fell back to its ``target_files`` and scored the PRE-EXISTING
seam file on disk a vacuous 1.0, which the disk-score recompute averaged into a perfect
run. Companion attribution vacuum: ``pipeline_stage/root_cause: unknown`` and
``agent/model/provider: null`` on a perfectly legible provider-400.

Covered here:
* the zero-success verdict floor (no completions can never be PASS / 1.00);
* the vacuous disk-score guard (failed + nothing generated -> no disk score);
* provider-error / truncation root-cause classification;
* agent/model/provider attribution threading (history entry and queue-state metadata).
"""

from __future__ import annotations

from typing import Any, Dict, List

from startd8.contractors.prime_postmortem import (
    PipelineStage,
    PrimePostMortemEvaluator,
    RootCause,
    RootCauseClassifier,
)

# RUN-006's exact error (docs/P3_RUN_006_POSTMORTEM.md §2) — the most legible error in
# the catalog, which the classifier nonetheless filed as unknown/unknown.
_RUN_006_ERROR = (
    "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
    "'message': 'Your credit balance is too low to access the Anthropic API. Please go "
    "to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011C'}"
)

# RUN-008 PI-001b's truncation error (docs/P3_RUN_008_POSTMORTEM.md §2).
_RUN_008_TRUNCATION = (
    "Draft was truncated at iteration 3 (source: api). Output tokens: 14525. Consider: "
    "(1) increasing max_tokens, (2) decomposing the task, or (3) setting "
    "fail_on_api_truncation=False to continue anyway."
)


def _result_dict(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"status": "complete", "history": history}


def _queue_feature(fid: str, **overrides: Any) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "id": fid,
        "name": fid,
        "status": "failed",
        "error_message": "",
        "target_files": [],
        "generated_files": [],
        "dependencies": [],
        "metadata": {},
    }
    entry.update(overrides)
    return entry


# ---------------------------------------------------------------------------
# Classifier: provider errors and truncation are no longer unknown/unknown
# ---------------------------------------------------------------------------


class TestProviderAndTruncationClassification:
    def test_run_006_provider_400_is_classified(self):
        cause, stage = RootCauseClassifier().classify_feature(
            {"error_message": _RUN_006_ERROR, "status": "failed"}
        )
        assert cause == RootCause.PROVIDER_ERROR
        assert stage == PipelineStage.GENERATION

    def test_provider_400_wrapped_in_exception_prefix_still_classified(self):
        # develop_feature's except wraps with "Exception during code generation: ..." —
        # the provider pattern must win over the generic catch-all.
        cause, stage = RootCauseClassifier().classify_feature(
            {
                "error_message": f"Exception during code generation: {_RUN_006_ERROR}",
                "status": "failed",
            }
        )
        assert cause == RootCause.PROVIDER_ERROR
        assert stage == PipelineStage.GENERATION

    def test_run_008_truncation_is_classified(self):
        cause, stage = RootCauseClassifier().classify_feature(
            {"error_message": _RUN_008_TRUNCATION, "status": "failed"}
        )
        assert cause == RootCause.TRUNCATION
        assert stage == PipelineStage.GENERATION


# ---------------------------------------------------------------------------
# Verdict floor: zero successful completions can NEVER produce PASS / 1.00
# ---------------------------------------------------------------------------


class TestZeroSuccessVerdictFloor:
    def _run_006_shaped_evaluation(self, tmp_path):
        """Reproduce RUN-006's shape: 1 failed feature, $0, nothing generated,
        target file pre-existing (and healthy) at the project root."""
        project_root = tmp_path / "proj"
        (project_root / "app").mkdir(parents=True)
        # The pre-existing, healthy seam file the run never touched.
        (project_root / "app" / "user_routers.py").write_text(
            "from typing import List\n\nuser_routers: List = []\n", encoding="utf-8"
        )

        history = [
            {
                "feature_id": "PI-001a",
                "feature_name": "PI-001a",
                "success": False,
                "error": _RUN_006_ERROR,
                "cost_usd": 0.0,
                "generation_metadata": {},
            }
        ]
        queue_state = {
            "PI-001a": _queue_feature(
                "PI-001a",
                error_message=_RUN_006_ERROR,
                target_files=["app/user_routers.py"],
            )
        }
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        return PrimePostMortemEvaluator().evaluate(
            _result_dict(history),
            queue_state,
            output_dir=str(out_dir),
            project_root=str(project_root),
        )

    def test_run_006_false_green_is_now_fail(self, tmp_path):
        report = self._run_006_shaped_evaluation(tmp_path)
        assert report.total_features == 1
        assert report.successful_features == 0
        assert report.aggregate_verdict == "FAIL"
        assert report.aggregate_score == 0.0

    def test_failed_feature_with_nothing_generated_gets_no_vacuous_disk_score(
        self, tmp_path
    ):
        report = self._run_006_shaped_evaluation(tmp_path)
        fpm = report.features[0]
        assert fpm.success is False
        # The pre-existing target file must NOT be scored as the feature's output.
        assert fpm.disk_quality_score is None
        assert fpm.disk_compliance is None

    def test_floor_applies_without_project_root_too(self, tmp_path):
        history = [
            {
                "feature_id": "F-1",
                "feature_name": "F-1",
                "success": False,
                "error": "boom",
                "cost_usd": 0.0,
            }
        ]
        queue_state = {"F-1": _queue_feature("F-1", error_message="boom")}
        report = PrimePostMortemEvaluator().evaluate(
            _result_dict(history), queue_state, output_dir=str(tmp_path)
        )
        assert report.aggregate_verdict == "FAIL"
        assert report.aggregate_score == 0.0

    def test_successful_run_still_passes(self, tmp_path):
        history = [
            {
                "feature_id": "F-1",
                "feature_name": "F-1",
                "success": True,
                "cost_usd": 0.01,
            }
        ]
        queue_state = {"F-1": _queue_feature("F-1", status="complete")}
        report = PrimePostMortemEvaluator().evaluate(
            _result_dict(history), queue_state, output_dir=str(tmp_path)
        )
        assert report.successful_features == 1
        assert report.aggregate_verdict == "PASS"


# ---------------------------------------------------------------------------
# Attribution: failed calls carry agent/model/provider + stage when known
# ---------------------------------------------------------------------------


class TestFailureAttribution:
    def test_attribution_from_history_entry(self, tmp_path):
        history = [
            {
                "feature_id": "PI-001a",
                "feature_name": "PI-001a",
                "success": False,
                "error": "something weird",  # no classifier pattern match
                "cost_usd": 0.0,
                "agent": "anthropic:claude-sonnet-4-6",
                "model": "claude-sonnet-4-6",
                "provider": "anthropic",
                "pipeline_stage": "generation",
            }
        ]
        queue_state = {
            "PI-001a": _queue_feature("PI-001a", error_message="something weird")
        }
        report = PrimePostMortemEvaluator().evaluate(
            _result_dict(history), queue_state, output_dir=str(tmp_path)
        )
        fpm = report.features[0]
        assert fpm.agent == "anthropic:claude-sonnet-4-6"
        assert fpm.model == "claude-sonnet-4-6"
        assert fpm.provider == "anthropic"
        # Stage threaded from the failure site when the classifier can't tell.
        assert fpm.pipeline_stage == PipelineStage.GENERATION

    def test_attribution_from_queue_state_metadata(self, tmp_path):
        history = [
            {
                "feature_id": "PI-001a",
                "feature_name": "PI-001a",
                "success": False,
                "error": "something weird",
                "cost_usd": 0.0,
            }
        ]
        queue_state = {
            "PI-001a": _queue_feature(
                "PI-001a",
                error_message="something weird",
                metadata={
                    "failure_attribution": {
                        "stage": "generation",
                        "agent": "gemini:gemini-2.5-pro",
                        "model": "gemini-2.5-pro",
                        "provider": "gemini",
                    }
                },
            )
        }
        report = PrimePostMortemEvaluator().evaluate(
            _result_dict(history), queue_state, output_dir=str(tmp_path)
        )
        fpm = report.features[0]
        assert fpm.agent == "gemini:gemini-2.5-pro"
        assert fpm.model == "gemini-2.5-pro"
        assert fpm.provider == "gemini"
        assert fpm.pipeline_stage == PipelineStage.GENERATION

    def test_classifier_stage_wins_over_metadata_fallback(self, tmp_path):
        # When the error message classifies, the classifier's stage is kept.
        history = [
            {
                "feature_id": "PI-001a",
                "feature_name": "PI-001a",
                "success": False,
                "error": _RUN_006_ERROR,
                "cost_usd": 0.0,
                "agent": "anthropic:claude-sonnet-4-6",
                "model": "claude-sonnet-4-6",
                "provider": "anthropic",
            }
        ]
        queue_state = {
            "PI-001a": _queue_feature("PI-001a", error_message=_RUN_006_ERROR)
        }
        report = PrimePostMortemEvaluator().evaluate(
            _result_dict(history), queue_state, output_dir=str(tmp_path)
        )
        fpm = report.features[0]
        assert fpm.root_cause == RootCause.PROVIDER_ERROR
        assert fpm.pipeline_stage == PipelineStage.GENERATION
        assert fpm.provider == "anthropic"


# ---------------------------------------------------------------------------
# Failure-site stamping (prime contractor side)
# ---------------------------------------------------------------------------


class TestStampFailureAttribution:
    def test_stamp_uses_result_model_and_parses_spec(self):
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow
        from startd8.contractors.queue import FeatureSpec

        feature = FeatureSpec(id="F-1", name="F-1")

        class _Stub:
            code_generator = None

        stub = _Stub()
        PrimeContractorWorkflow._stamp_failure_attribution(
            stub, feature, stage="generation", model="anthropic:claude-sonnet-4-6",
        )
        attr = feature.metadata["failure_attribution"]
        assert attr == {
            "stage": "generation",
            "agent": "anthropic:claude-sonnet-4-6",
            "model": "claude-sonnet-4-6",
            "provider": "anthropic",
        }

    def test_stamp_falls_back_to_lead_agent(self):
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow
        from startd8.contractors.queue import FeatureSpec

        feature = FeatureSpec(id="F-1", name="F-1")

        class _Gen:
            lead_agent = "gemini:gemini-2.5-flash"

        class _Stub:
            code_generator = _Gen()

        PrimeContractorWorkflow._stamp_failure_attribution(_Stub(), feature, stage="generation")
        attr = feature.metadata["failure_attribution"]
        assert attr["agent"] == "gemini:gemini-2.5-flash"
        assert attr["provider"] == "gemini"

    def test_stamp_never_fabricates(self):
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow
        from startd8.contractors.queue import FeatureSpec

        feature = FeatureSpec(id="F-1", name="F-1")

        class _Stub:
            code_generator = None

        PrimeContractorWorkflow._stamp_failure_attribution(_Stub(), feature, stage="generation")
        attr = feature.metadata["failure_attribution"]
        assert attr["agent"] is None
        assert attr["model"] is None
        assert attr["provider"] is None
        assert attr["stage"] == "generation"
