"""Tests for Node.js post-generation and postmortem (Phase 4).

Covers REQ-NODE-300 (prettier best-effort), REQ-NODE-501 (language mismatch
postmortem pattern), and REQ-MLT-401 (shared mismatch pattern).
"""

import dataclasses
from pathlib import Path
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# REQ-NODE-300: Prettier post-generation formatting
# ---------------------------------------------------------------------------


class TestPrettierPostGeneration:
    """Test NodeLanguageProfile.post_generation_cleanup()."""

    def _profile(self):
        from startd8.languages.nodejs import NodeLanguageProfile
        return NodeLanguageProfile()

    def test_formats_js_files_when_prettier_available(self, tmp_path):
        # REQ-PLI-NODE-P1: post_generation_cleanup runs prettier best-effort and
        # returns a list of WARNING strings (empty on success), consumed by the
        # integration engine as ``cleanup_warnings``. A successful run (exit 0)
        # produces no warnings.
        js_file = tmp_path / "server.js"
        js_file.write_text("const x=1;")
        profile = self._profile()

        with mock.patch("shutil.which", return_value="/usr/bin/prettier"):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                result = profile.post_generation_cleanup([js_file], tmp_path)

        assert result == []  # no warnings on success
        mock_run.assert_called_once()
        assert "prettier" in mock_run.call_args[0][0][0]

    def test_skips_non_js_files(self, tmp_path):
        py_file = tmp_path / "main.py"
        py_file.write_text("x = 1")
        profile = self._profile()

        with mock.patch("shutil.which", return_value="/usr/bin/prettier"):
            with mock.patch("subprocess.run") as mock_run:
                result = profile.post_generation_cleanup([py_file], tmp_path)

        assert result == []
        mock_run.assert_not_called()

    def test_returns_empty_when_prettier_unavailable(self, tmp_path):
        js_file = tmp_path / "app.js"
        js_file.write_text("const x=1;")
        profile = self._profile()

        with mock.patch("shutil.which", return_value=None):
            result = profile.post_generation_cleanup([js_file], tmp_path)

        assert result == []

    def test_handles_timeout_gracefully(self, tmp_path):
        import subprocess
        js_file = tmp_path / "slow.js"
        js_file.write_text("const x=1;")
        profile = self._profile()

        with mock.patch("shutil.which", return_value="/usr/bin/prettier"):
            with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("prettier", 30)):
                result = profile.post_generation_cleanup([js_file], tmp_path)

        # Timeout is silently skipped — no crash, empty result
        assert result == []


# ---------------------------------------------------------------------------
# REQ-NODE-501 / REQ-MLT-401: Language mismatch postmortem pattern
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class FakeDiskCompliance:
    error: str = ""


@dataclasses.dataclass
class FakeFeaturePostMortem:
    feature_id: str = "F-001"
    success: bool = True
    root_cause: str = "UNKNOWN"
    cost_usd: float = 0.0
    target_files: list = dataclasses.field(default_factory=list)
    generated_files: list = dataclasses.field(default_factory=list)
    elements: list = dataclasses.field(default_factory=list)
    disk_compliance: object = None
    per_file_disk: list = dataclasses.field(default_factory=list)
    disk_quality_score: float = None


class TestLanguageMismatchPattern:
    """Test _detect_cross_feature_patterns for language mismatch."""

    def _evaluator(self):
        from startd8.contractors.prime_postmortem import PrimePostMortemEvaluator
        return PrimePostMortemEvaluator.__new__(PrimePostMortemEvaluator)

    def test_detects_mismatch_across_features(self):
        evaluator = self._evaluator()
        features = [
            FakeFeaturePostMortem(
                feature_id="F-001",
                disk_compliance=FakeDiskCompliance(error="language_mismatch:python_content_in_html"),
            ),
            FakeFeaturePostMortem(
                feature_id="F-002",
                disk_compliance=FakeDiskCompliance(error="language_mismatch:python_content_in_json"),
            ),
        ]
        patterns = evaluator._detect_cross_feature_patterns(features)
        mismatch = [p for p in patterns if p.pattern_type == "language_mismatch_in_generation"]
        assert len(mismatch) == 1
        assert mismatch[0].severity == "medium"
        assert set(mismatch[0].affected_features) == {"F-001", "F-002"}

    def test_high_severity_for_three_plus(self):
        evaluator = self._evaluator()
        features = [
            FakeFeaturePostMortem(
                feature_id=f"F-{i:03d}",
                disk_compliance=FakeDiskCompliance(error="language_mismatch:python_content_in_go_mod"),
            )
            for i in range(4)
        ]
        patterns = evaluator._detect_cross_feature_patterns(features)
        mismatch = [p for p in patterns if p.pattern_type == "language_mismatch_in_generation"]
        assert len(mismatch) == 1
        assert mismatch[0].severity == "high"

    def test_no_pattern_for_single_mismatch(self):
        evaluator = self._evaluator()
        features = [
            FakeFeaturePostMortem(
                feature_id="F-001",
                disk_compliance=FakeDiskCompliance(error="language_mismatch:python_content_in_html"),
            ),
            FakeFeaturePostMortem(
                feature_id="F-002",
                disk_compliance=FakeDiskCompliance(error=""),
            ),
        ]
        patterns = evaluator._detect_cross_feature_patterns(features)
        mismatch = [p for p in patterns if p.pattern_type == "language_mismatch_in_generation"]
        assert len(mismatch) == 0

    def test_no_pattern_when_no_disk_compliance(self):
        evaluator = self._evaluator()
        features = [
            FakeFeaturePostMortem(feature_id="F-001", disk_compliance=None),
            FakeFeaturePostMortem(feature_id="F-002", disk_compliance=None),
        ]
        patterns = evaluator._detect_cross_feature_patterns(features)
        mismatch = [p for p in patterns if p.pattern_type == "language_mismatch_in_generation"]
        assert len(mismatch) == 0


# ---------------------------------------------------------------------------
# REQ-MLT-401: Kaizen picks up language mismatch suggestion
# ---------------------------------------------------------------------------


class TestLanguageMismatchKaizen:
    """Test that CAUSE_TO_SUGGESTION includes the mismatch pattern."""

    def test_kaizen_mapping_exists(self):
        from startd8.contractors.prime_postmortem import CAUSE_TO_SUGGESTION
        assert "language_mismatch_in_generation" in CAUSE_TO_SUGGESTION
        entry = CAUSE_TO_SUGGESTION["language_mismatch_in_generation"]
        assert "phase" in entry
        assert "hint" in entry
        assert "Non-Python" in entry["hint"]
