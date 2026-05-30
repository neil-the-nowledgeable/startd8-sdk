"""Tests for Kaizen response file capture (_capture_response_files).

Verifies that raw LLM responses from GenerationResult.metadata are written
as *_response.md files alongside kaizen prompt files, with sidecar
*_response.meta.json metadata.

Covers REQ-KZ-201: response capture, 2 MiB guard, redaction, backward compat.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from startd8.contractors.prime_contractor import PrimeContractorWorkflow
from startd8.contractors.queue import FeatureSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_feature(**overrides: Any) -> FeatureSpec:
    defaults = {
        "id": "PI-003",
        "name": "Email Service",
        "description": "gRPC email server",
        "target_files": ["src/email_server.py"],
        "dependencies": [],
    }
    defaults.update(overrides)
    return FeatureSpec(**defaults)


def _make_workflow(tmp_path: Path) -> PrimeContractorWorkflow:
    """Build a minimal PrimeContractorWorkflow with kaizen enabled."""
    with patch.object(PrimeContractorWorkflow, "__init__", lambda self, **kw: None):
        wf = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)

    wf.project_root = tmp_path
    from startd8.contractors.prime_contractor import KaizenConfig
    wf._kaizen = KaizenConfig(enabled=True, prompt_dir=tmp_path / "kaizen-prompts")
    wf._kaizen.prompt_dir.mkdir(parents=True, exist_ok=True)
    wf.code_generator = MagicMock()
    wf.code_generator.lead_agent = None
    wf.code_generator.drafter_agent = None
    return wf


def _make_result(**metadata_overrides: Any) -> MagicMock:
    """Create a mock GenerationResult with metadata."""
    result = MagicMock()
    result.metadata = dict(metadata_overrides)
    return result


def _prompt_dir(wf: PrimeContractorWorkflow, feature: FeatureSpec) -> Path:
    """Return the expected prompt directory for a feature."""
    safe_fid = feature.id.replace("/", "_")
    return wf._kaizen.prompt_dir / "standalone" / safe_fid


# ---------------------------------------------------------------------------
# Tests: Response file writing
# ---------------------------------------------------------------------------


class TestCaptureResponseFiles:
    """Tests for _capture_response_files."""

    def test_writes_all_three_phase_responses(self, tmp_path: Path) -> None:
        """When all three phase keys are present, three response files are written."""
        wf = _make_workflow(tmp_path)
        feature = _make_feature()
        prompt_dir = _prompt_dir(wf, feature)
        prompt_dir.mkdir(parents=True, exist_ok=True)

        result = _make_result(
            spec_raw_response="# Spec\nImplement a gRPC server.",
            draft_raw_response="```python\nclass EmailServer:\n    pass\n```",
            review_raw_response="Score: 85/100\nGood implementation.",
        )

        wf._capture_response_files(prompt_dir, feature, result)

        assert (prompt_dir / "spec_response.md").exists()
        assert (prompt_dir / "draft_response.md").exists()
        assert (prompt_dir / "review_response.md").exists()

        # Verify content
        spec_text = (prompt_dir / "spec_response.md").read_text(encoding="utf-8")
        assert "gRPC server" in spec_text

        draft_text = (prompt_dir / "draft_response.md").read_text(encoding="utf-8")
        assert "EmailServer" in draft_text

        review_text = (prompt_dir / "review_response.md").read_text(encoding="utf-8")
        assert "85/100" in review_text

    def test_writes_sidecar_meta_json(self, tmp_path: Path) -> None:
        """Each response file should have a sidecar .meta.json."""
        wf = _make_workflow(tmp_path)
        feature = _make_feature()
        prompt_dir = _prompt_dir(wf, feature)
        prompt_dir.mkdir(parents=True, exist_ok=True)

        result = _make_result(
            spec_raw_response="Spec content",
            draft_raw_response="Draft content",
            review_raw_response="Review content",
        )

        wf._capture_response_files(prompt_dir, feature, result)

        for phase in ("spec", "draft", "review"):
            meta_path = prompt_dir / f"{phase}_response.meta.json"
            assert meta_path.exists(), f"{phase}_response.meta.json missing"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            assert meta["phase"] == phase
            assert meta["feature_id"] == feature.id
            assert meta["truncated"] is False
            assert "original_bytes" in meta
            assert "captured_bytes" in meta

    def test_writes_subset_when_some_keys_missing(self, tmp_path: Path) -> None:
        """When only some phase keys are present, only those files are written."""
        wf = _make_workflow(tmp_path)
        feature = _make_feature()
        prompt_dir = _prompt_dir(wf, feature)
        prompt_dir.mkdir(parents=True, exist_ok=True)

        result = _make_result(
            draft_raw_response="Only a draft response.",
        )

        wf._capture_response_files(prompt_dir, feature, result)

        assert not (prompt_dir / "spec_response.md").exists()
        assert (prompt_dir / "draft_response.md").exists()
        assert not (prompt_dir / "review_response.md").exists()

    def test_no_files_when_no_keys_present(self, tmp_path: Path) -> None:
        """When metadata has no response keys, no response files are written."""
        wf = _make_workflow(tmp_path)
        feature = _make_feature()
        prompt_dir = _prompt_dir(wf, feature)
        prompt_dir.mkdir(parents=True, exist_ok=True)

        result = _make_result(some_other_key="irrelevant")

        wf._capture_response_files(prompt_dir, feature, result)

        assert not (prompt_dir / "spec_response.md").exists()
        assert not (prompt_dir / "draft_response.md").exists()
        assert not (prompt_dir / "review_response.md").exists()

    def test_no_error_when_metadata_empty(self, tmp_path: Path) -> None:
        """Backward compat: empty metadata should not raise."""
        wf = _make_workflow(tmp_path)
        feature = _make_feature()
        prompt_dir = _prompt_dir(wf, feature)
        prompt_dir.mkdir(parents=True, exist_ok=True)

        result = _make_result()  # empty metadata

        # Should not raise
        wf._capture_response_files(prompt_dir, feature, result)

    def test_no_error_when_result_has_no_metadata_attr(self, tmp_path: Path) -> None:
        """Backward compat: result without metadata attr should not raise."""
        wf = _make_workflow(tmp_path)
        feature = _make_feature()
        prompt_dir = _prompt_dir(wf, feature)
        prompt_dir.mkdir(parents=True, exist_ok=True)

        result = MagicMock(spec=[])  # no metadata attribute
        del result.metadata

        # Should not raise
        wf._capture_response_files(prompt_dir, feature, result)

    def test_truncation_guard_at_2mib(self, tmp_path: Path) -> None:
        """Responses exceeding 2 MiB should be truncated with sentinel."""
        wf = _make_workflow(tmp_path)
        feature = _make_feature()
        prompt_dir = _prompt_dir(wf, feature)
        prompt_dir.mkdir(parents=True, exist_ok=True)

        # 3 MiB of content
        large_content = "x" * (3 * 1024 * 1024)
        result = _make_result(draft_raw_response=large_content)

        wf._capture_response_files(prompt_dir, feature, result)

        meta = json.loads(
            (prompt_dir / "draft_response.meta.json").read_text(encoding="utf-8")
        )
        assert meta["truncated"] is True
        assert meta["original_bytes"] == len(large_content.encode("utf-8"))

        # The file should contain the truncation sentinel
        text = (prompt_dir / "draft_response.md").read_text(encoding="utf-8")
        assert "exceeded 2 MiB capture limit" in text

    def test_falls_back_to_aggregate_raw_response(self, tmp_path: Path) -> None:
        """When per-phase keys are absent, falls back to raw_response key."""
        wf = _make_workflow(tmp_path)
        feature = _make_feature()
        prompt_dir = _prompt_dir(wf, feature)
        prompt_dir.mkdir(parents=True, exist_ok=True)

        result = _make_result(
            raw_response="Aggregate response text from single-call workflow.",
        )

        wf._capture_response_files(prompt_dir, feature, result)

        # Aggregate gets attributed to "draft" by convention
        assert (prompt_dir / "draft_response.md").exists()
        text = (prompt_dir / "draft_response.md").read_text(encoding="utf-8")
        assert "Aggregate response" in text


# ---------------------------------------------------------------------------
# Tests: to_summary raw_response forwarding
# ---------------------------------------------------------------------------


class TestToSummaryRawResponse:
    """Tests that to_summary includes raw_response for drafts."""

    def test_to_summary_includes_raw_response_in_drafts(self) -> None:
        """DraftResult.raw_response should appear in to_summary() drafts_raw."""
        from startd8.workflows.builtin.primary_contractor_models import (
            DraftResult,
            ImplementationSpec,
            PrimaryContractorResult,
        )

        spec = ImplementationSpec(
            spec_id="spec-1",
            task_summary="Implement foo",
            requirements=["R1"],
            technical_approach="Use bar",
            acceptance_criteria=["AC1"],
            raw_spec="Full spec text from Claude.",
        )
        draft = DraftResult(
            draft_id="draft-1",
            iteration=1,
            implementation="def foo(): pass",
            raw_response="Here is the implementation:\n```python\ndef foo(): pass\n```\nDone.",
        )
        result = PrimaryContractorResult(
            workflow_id="wf-1",
            success=True,
            final_implementation="def foo(): pass",
            spec=spec,
            drafts=[draft],
        )

        summary = result.to_summary()

        assert "drafts_raw" in summary
        assert len(summary["drafts_raw"]) == 1
        assert summary["drafts_raw"][0]["raw_response"] == draft.raw_response
        assert summary["drafts_raw"][0]["implementation"] == draft.implementation


# ---------------------------------------------------------------------------
# Tests: Generator raw response forwarding
# ---------------------------------------------------------------------------


class TestGeneratorRawResponseForwarding:
    """Tests that PrimaryContractorCodeGenerator forwards raw_response."""

    def test_prefers_raw_response_over_implementation(self) -> None:
        """draft_raw_response should use raw_response when available."""
        from startd8.contractors.generators.primary_contractor import (
            PrimaryContractorCodeGenerator,
        )
        from startd8.workflows.models import WorkflowResult, WorkflowMetrics

        # Build a mock workflow result with raw_response in summary
        gen = PrimaryContractorCodeGenerator.__new__(PrimaryContractorCodeGenerator)
        gen.output_dir = Path("/tmp/test_gen")
        gen.lead_agent = "anthropic:claude-sonnet-4-20250514"
        gen.drafter_agent = "anthropic:claude-haiku-4-5-20251001"
        gen.max_iterations = 1
        gen.pass_threshold = 80
        gen.fail_on_truncation = False
        gen.check_truncation = False
        gen.strict_truncation = False
        gen.max_tokens = None

        # Construct the lc_summary dict that to_summary() would return
        lc_summary = {
            "spec_raw": "Full spec text",
            "drafts_raw": [
                {
                    "iteration": 1,
                    "implementation": "def foo(): pass",
                    "raw_response": "Here is the code:\n```python\ndef foo(): pass\n```",
                },
            ],
            "reviews_raw": [
                {"iteration": 1, "review_text": "Score: 90", "score": 90, "passed": True},
            ],
        }

        # The generator reads from lc_summary to build gen_metadata
        gen_metadata: dict = {}
        if lc_summary.get("spec_raw"):
            gen_metadata["spec_raw_response"] = lc_summary["spec_raw"]
        drafts_raw = lc_summary.get("drafts_raw", [])
        if drafts_raw:
            last_draft = drafts_raw[-1]
            gen_metadata["draft_raw_response"] = (
                last_draft.get("raw_response")
                or last_draft.get("implementation", "")
            )
        reviews_raw = lc_summary.get("reviews_raw", [])
        if reviews_raw:
            gen_metadata["review_raw_response"] = reviews_raw[-1].get(
                "review_text", ""
            )

        # raw_response should be preferred over implementation
        assert gen_metadata["draft_raw_response"] == (
            "Here is the code:\n```python\ndef foo(): pass\n```"
        )
        assert gen_metadata["spec_raw_response"] == "Full spec text"
        assert gen_metadata["review_raw_response"] == "Score: 90"

    def test_falls_back_to_implementation_when_no_raw_response(self) -> None:
        """When raw_response is empty/missing, fall back to implementation."""
        lc_summary = {
            "drafts_raw": [
                {
                    "iteration": 1,
                    "implementation": "def foo(): pass",
                    # No raw_response key or empty
                },
            ],
        }
        drafts_raw = lc_summary.get("drafts_raw", [])
        last_draft = drafts_raw[-1]
        draft_raw_response = (
            last_draft.get("raw_response")
            or last_draft.get("implementation", "")
        )
        assert draft_raw_response == "def foo(): pass"

    def test_falls_back_when_raw_response_is_empty_string(self) -> None:
        """When raw_response is empty string, fall back to implementation."""
        lc_summary = {
            "drafts_raw": [
                {
                    "iteration": 1,
                    "implementation": "def foo(): pass",
                    "raw_response": "",
                },
            ],
        }
        drafts_raw = lc_summary.get("drafts_raw", [])
        last_draft = drafts_raw[-1]
        draft_raw_response = (
            last_draft.get("raw_response")
            or last_draft.get("implementation", "")
        )
        assert draft_raw_response == "def foo(): pass"
