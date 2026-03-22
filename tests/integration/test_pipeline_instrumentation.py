"""Integration tests for pipeline instrumentation auto-trigger (REQ-TCW-401)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


CAP_DEV_PIPE = Path(os.environ.get(
    "CAP_DEV_PIPE_DIR",
    str(Path.home() / "Documents" / "dev" / "cap-dev-pipe"),
))


@pytest.fixture()
def post_run_module():
    """Import prime-post-run.py as a module."""
    script = CAP_DEV_PIPE / "prime-post-run.py"
    if not script.is_file():
        pytest.skip(f"cap-dev-pipe not found at {CAP_DEV_PIPE}")
    import importlib.util
    spec = importlib.util.spec_from_file_location("prime_post_run", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# _read_verdict
# ---------------------------------------------------------------------------

class TestReadVerdict:
    """Test _read_verdict helper."""

    def test_reads_pass(self, tmp_path, post_run_module):
        (tmp_path / "prime-postmortem-report.json").write_text(
            json.dumps({"aggregate_verdict": "PASS"})
        )
        assert post_run_module._read_verdict(tmp_path) == "PASS"

    def test_reads_fail(self, tmp_path, post_run_module):
        (tmp_path / "prime-postmortem-report.json").write_text(
            json.dumps({"aggregate_verdict": "FAIL"})
        )
        assert post_run_module._read_verdict(tmp_path) == "FAIL"

    def test_missing_file_returns_unknown(self, tmp_path, post_run_module):
        assert post_run_module._read_verdict(tmp_path) == "UNKNOWN"

    def test_malformed_json_returns_unknown(self, tmp_path, post_run_module):
        (tmp_path / "prime-postmortem-report.json").write_text("NOT JSON")
        assert post_run_module._read_verdict(tmp_path) == "UNKNOWN"

    def test_missing_key_returns_unknown(self, tmp_path, post_run_module):
        (tmp_path / "prime-postmortem-report.json").write_text(json.dumps({}))
        assert post_run_module._read_verdict(tmp_path) == "UNKNOWN"


# ---------------------------------------------------------------------------
# _read_generation_profile
# ---------------------------------------------------------------------------

class TestReadGenerationProfile:
    """Test profile resolution from seed and onboarding."""

    def test_reads_from_seed(self, tmp_path, post_run_module):
        seed = tmp_path / "seed.json"
        seed.write_text(json.dumps({"generation_profile": "source"}))
        assert post_run_module._read_generation_profile(seed) == "source"

    def test_reads_from_onboarding_sibling(self, tmp_path, post_run_module):
        seed = tmp_path / "seed.json"
        seed.write_text(json.dumps({}))  # No profile in seed
        (tmp_path / "onboarding-metadata.json").write_text(
            json.dumps({"generation_profile": "monitoring"})
        )
        assert post_run_module._read_generation_profile(seed) == "monitoring"

    def test_reads_from_onboarding_parent(self, tmp_path, post_run_module):
        subdir = tmp_path / "plan-ingestion"
        subdir.mkdir()
        seed = subdir / "seed.json"
        seed.write_text(json.dumps({}))
        (tmp_path / "onboarding-metadata.json").write_text(
            json.dumps({"generation_profile": "full"})
        )
        assert post_run_module._read_generation_profile(seed) == "full"

    def test_seed_takes_precedence(self, tmp_path, post_run_module):
        seed = tmp_path / "seed.json"
        seed.write_text(json.dumps({"generation_profile": "source"}))
        (tmp_path / "onboarding-metadata.json").write_text(
            json.dumps({"generation_profile": "monitoring"})
        )
        assert post_run_module._read_generation_profile(seed) == "source"

    def test_missing_everything_returns_empty(self, tmp_path, post_run_module):
        seed = tmp_path / "nonexistent.json"
        assert post_run_module._read_generation_profile(seed) == ""

    def test_malformed_seed_falls_through(self, tmp_path, post_run_module):
        seed = tmp_path / "seed.json"
        seed.write_text("NOT JSON")
        (tmp_path / "onboarding-metadata.json").write_text(
            json.dumps({"generation_profile": "operator"})
        )
        assert post_run_module._read_generation_profile(seed) == "operator"


# ---------------------------------------------------------------------------
# _should_run_instrumentation (Option B)
# ---------------------------------------------------------------------------

class TestShouldRunInstrumentation:
    """Option B: profile sets default, env var overrides."""

    def test_env_true_always_runs(self, tmp_path, post_run_module):
        """ENABLE_INSTRUMENTATION=true forces instrumentation on regardless of profile."""
        seed = tmp_path / "seed.json"
        seed.write_text(json.dumps({"generation_profile": "monitoring"}))
        with patch.dict(os.environ, {"ENABLE_INSTRUMENTATION": "true"}):
            assert post_run_module._should_run_instrumentation(seed) is True

    def test_env_false_always_skips(self, tmp_path, post_run_module):
        """ENABLE_INSTRUMENTATION=false suppresses even for source profile."""
        seed = tmp_path / "seed.json"
        seed.write_text(json.dumps({"generation_profile": "source"}))
        with patch.dict(os.environ, {"ENABLE_INSTRUMENTATION": "false"}):
            assert post_run_module._should_run_instrumentation(seed) is False

    def test_auto_source_profile_runs(self, tmp_path, post_run_module):
        """auto + source profile → run."""
        seed = tmp_path / "seed.json"
        seed.write_text(json.dumps({"generation_profile": "source"}))
        with patch.dict(os.environ, {"ENABLE_INSTRUMENTATION": "auto"}):
            assert post_run_module._should_run_instrumentation(seed) is True

    def test_auto_full_profile_runs(self, tmp_path, post_run_module):
        """auto + full profile → run."""
        seed = tmp_path / "seed.json"
        seed.write_text(json.dumps({"generation_profile": "full"}))
        with patch.dict(os.environ, {"ENABLE_INSTRUMENTATION": "auto"}):
            assert post_run_module._should_run_instrumentation(seed) is True

    def test_auto_monitoring_profile_skips(self, tmp_path, post_run_module):
        """auto + monitoring profile → skip."""
        seed = tmp_path / "seed.json"
        seed.write_text(json.dumps({"generation_profile": "monitoring"}))
        with patch.dict(os.environ, {"ENABLE_INSTRUMENTATION": "auto"}):
            assert post_run_module._should_run_instrumentation(seed) is False

    def test_auto_operator_profile_skips(self, tmp_path, post_run_module):
        """auto + operator profile → skip."""
        seed = tmp_path / "seed.json"
        seed.write_text(json.dumps({"generation_profile": "operator"}))
        with patch.dict(os.environ, {"ENABLE_INSTRUMENTATION": "auto"}):
            assert post_run_module._should_run_instrumentation(seed) is False

    def test_auto_sponsor_profile_skips(self, tmp_path, post_run_module):
        """auto + sponsor profile → skip."""
        seed = tmp_path / "seed.json"
        seed.write_text(json.dumps({"generation_profile": "sponsor"}))
        with patch.dict(os.environ, {"ENABLE_INSTRUMENTATION": "auto"}):
            assert post_run_module._should_run_instrumentation(seed) is False

    def test_auto_no_profile_skips(self, tmp_path, post_run_module):
        """auto + no profile at all → skip (safe default)."""
        seed = tmp_path / "nonexistent.json"
        with patch.dict(os.environ, {"ENABLE_INSTRUMENTATION": "auto"}):
            assert post_run_module._should_run_instrumentation(seed) is False

    def test_no_env_var_defaults_to_auto(self, tmp_path, post_run_module):
        """Missing env var behaves like auto."""
        seed = tmp_path / "seed.json"
        seed.write_text(json.dumps({"generation_profile": "source"}))
        env = {k: v for k, v in os.environ.items() if k != "ENABLE_INSTRUMENTATION"}
        with patch.dict(os.environ, env, clear=True):
            assert post_run_module._should_run_instrumentation(seed) is True

    def test_env_true_no_profile_still_runs(self, tmp_path, post_run_module):
        """Standalone mode: ENABLE_INSTRUMENTATION=true with no profile (existing code)."""
        seed = tmp_path / "nonexistent.json"
        with patch.dict(os.environ, {"ENABLE_INSTRUMENTATION": "true"}):
            assert post_run_module._should_run_instrumentation(seed) is True


# ---------------------------------------------------------------------------
# Workflow profile passthrough
# ---------------------------------------------------------------------------

class TestWorkflowProfilePassthrough:
    """Test that generation_profile flows through the workflow.

    Note: v3 (REQ-TCW v3.0.0) removed generation_profile and provenance
    from the simplified scan-only workflow. Profile passthrough is now
    handled by PrimeContractorWorkflow directly.
    """

    @pytest.mark.skip(reason="v3: generation_profile removed from scan-only workflow")
    def test_profile_in_result(self, tmp_path):
        from startd8.workflows.builtin.todo_completion_workflow import (
            TodoCompletionWorkflow,
        )

        scan_dir = tmp_path / "generated"
        scan_dir.mkdir()
        (scan_dir / "Svc.java").write_text(
            "package x;\npublic class Svc {\n"
            "  // TODO: implement metrics\n"
            "}\n"
        )
        out_dir = tmp_path / "output"
        wf = TodoCompletionWorkflow()
        result = wf.run({
            "scan_dir": str(scan_dir),
            "output_dir": str(out_dir),
            "generation_profile": "source",
            "categories": "A,B,C",
        })
        assert result.output.get("generation_profile") == "source"
        assert result.metadata.get("generation_profile") == "source"

    @pytest.mark.skip(reason="v3: provenance file removed from scan-only workflow")
    def test_profile_in_provenance(self, tmp_path):
        from startd8.workflows.builtin.todo_completion_workflow import (
            TodoCompletionWorkflow,
        )

        scan_dir = tmp_path / "generated"
        scan_dir.mkdir()
        (scan_dir / "Svc.java").write_text(
            "package x;\npublic class Svc {\n"
            "  // TODO: implement metrics\n"
            "}\n"
        )
        out_dir = tmp_path / "output"
        wf = TodoCompletionWorkflow()
        wf.run({
            "scan_dir": str(scan_dir),
            "output_dir": str(out_dir),
            "generation_profile": "full",
            "categories": "A,B,C",
        })
        prov = json.loads((out_dir / "instrumentation-provenance.json").read_text())
        assert prov["generation_profile"] == "full"

    def test_no_profile_omitted_from_result(self, tmp_path):
        from startd8.workflows.builtin.todo_completion_workflow import (
            TodoCompletionWorkflow,
        )

        scan_dir = tmp_path / "generated"
        scan_dir.mkdir()
        (scan_dir / "Svc.java").write_text(
            "package x;\npublic class Svc {\n"
            "  // TODO: implement metrics\n"
            "}\n"
        )
        out_dir = tmp_path / "output"
        wf = TodoCompletionWorkflow()
        result = wf.run({
            "scan_dir": str(scan_dir),
            "output_dir": str(out_dir),
            "categories": "A,B,C",
        })
        assert "generation_profile" not in result.output
