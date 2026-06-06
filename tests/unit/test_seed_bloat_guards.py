"""
Unit tests for the seed-bloat guards (kickoff-ingestion pilot, 2026-06-05).

The 88 MB prime-context-seed.json dissection (VALIDATION_AND_MANIFEST_DERIVATION.md
§6 note 2) produced three asks:
  (a) the AST walker must respect ignore rules (.venv/, pipeline-output/, .git/)
  (b) de-duplicate forward_manifest in the seed (top-level only)
  (c) a seed size budget — warn at low MBs, fail an order of magnitude up

No LLM calls — all deterministic.
"""

import json

import pytest

from startd8.forward_manifest_extractor import (
    SourceReconciler,
    is_excluded_source_path,
)
from startd8.workflows.builtin.plan_ingestion_emitter import _check_seed_size_budget
from startd8.workflows.builtin.plan_ingestion_models import (
    ParsedFeature,
    PlanIngestionConfig,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# (a) AST walker ignore rules
# ---------------------------------------------------------------------------

class TestExcludedSourcePath:
    def test_venv_excluded(self):
        assert is_excluded_source_path(".venv/lib/python3.14/site-packages/pkg/mod.py")

    def test_pipeline_output_excluded(self):
        assert is_excluded_source_path(
            ".cap-dev-pipe/pipeline-output/run-001/app/main.py"
        )
        assert is_excluded_source_path("pipeline-output/run-001/app/main.py")

    def test_git_excluded(self):
        assert is_excluded_source_path(".git/hooks/sample.py")

    def test_project_source_included(self):
        assert not is_excluded_source_path("app/main.py")
        assert not is_excluded_source_path("src/startd8/cli.py")
        assert not is_excluded_source_path("main.py")

    def test_only_directory_components_matched(self):
        # A FILE named like an excluded dir must not be excluded
        assert not is_excluded_source_path("app/archive.py")
        assert not is_excluded_source_path("app/build.py")


class TestSourceReconcilerIgnoresNonProjectDirs:
    def _make_project(self, tmp_path):
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "real.py").write_text(
            "def project_fn(x: int) -> int:\n    return x\n"
        )
        venv_pkg = tmp_path / ".venv" / "lib" / "python3.14" / "site-packages" / "somelib"
        venv_pkg.mkdir(parents=True)
        (venv_pkg / "internals.py").write_text(
            "def library_internal(y: str) -> str:\n    return y\n"
        )
        pipe_out = tmp_path / ".cap-dev-pipe" / "pipeline-output" / "old-run"
        pipe_out.mkdir(parents=True)
        (pipe_out / "stale.py").write_text(
            "def stale_output(z: float) -> float:\n    return z\n"
        )
        git_dir = tmp_path / ".git" / "hooks"
        git_dir.mkdir(parents=True)
        (git_dir / "hook.py").write_text("def hook_fn():\n    pass\n")
        return tmp_path

    def test_reconcile_extracts_only_project_contracts(self, tmp_path):
        root = self._make_project(tmp_path)
        feature = ParsedFeature(
            feature_id="F-001", name="real", target_files=["app/real.py"],
        )
        contracts = SourceReconciler(project_root=root).reconcile([feature])
        descriptions = {c.description for c in contracts}
        assert any("app/real.py" in d for d in descriptions)
        assert not any(".venv" in d for d in descriptions)
        assert not any("pipeline-output" in d for d in descriptions)
        assert not any(".git" in d for d in descriptions)

    def test_reconcile_names_exclude_library_internals(self, tmp_path):
        root = self._make_project(tmp_path)
        contracts = SourceReconciler(project_root=root).reconcile([])
        descriptions = " | ".join(c.description for c in contracts)
        assert "library_internal" not in descriptions
        assert "stale_output" not in descriptions
        assert "project_fn" in descriptions


# ---------------------------------------------------------------------------
# (c) Seed size budget
# ---------------------------------------------------------------------------

def _write_file_of_mb(tmp_path, mb):
    p = tmp_path / "prime-context-seed.json"
    p.write_bytes(b"x" * int(mb * 1_000_000))
    return p


class TestSeedSizeBudget:
    def test_under_budget_silent(self, tmp_path, caplog):
        p = _write_file_of_mb(tmp_path, 0.1)
        size = _check_seed_size_budget(p, warn_mb=5.0, fail_mb=50.0)
        assert size < 5.0
        assert "unusually large" not in caplog.text

    def test_warn_threshold_logs(self, tmp_path, caplog):
        p = _write_file_of_mb(tmp_path, 6)
        with caplog.at_level("WARNING"):
            _check_seed_size_budget(p, warn_mb=5.0, fail_mb=50.0, fm_contract_count=42)
        assert "unusually large" in caplog.text
        assert "42" in caplog.text

    def test_fail_threshold_raises(self, tmp_path):
        p = _write_file_of_mb(tmp_path, 51)
        with pytest.raises(ValueError, match="51.0 MB.*fail.*at 50"):
            _check_seed_size_budget(p, warn_mb=5.0, fail_mb=50.0, fm_contract_count=46290)

    def test_fail_message_names_walker_root_cause(self, tmp_path):
        p = _write_file_of_mb(tmp_path, 88)
        with pytest.raises(ValueError, match="non-project sources"):
            _check_seed_size_budget(p, warn_mb=5.0, fail_mb=50.0)

    def test_zero_thresholds_disable(self, tmp_path):
        p = _write_file_of_mb(tmp_path, 88)
        # Opt-out: thresholds <= 0 disable the checks entirely
        size = _check_seed_size_budget(p, warn_mb=0, fail_mb=0)
        assert size > 50


class TestSeedSizeConfig:
    def test_defaults(self):
        cfg = PlanIngestionConfig.from_dict({"plan_path": "plan.md"})
        assert cfg.seed_size_warn_mb == 5.0
        assert cfg.seed_size_fail_mb == 50.0

    def test_overrides(self):
        cfg = PlanIngestionConfig.from_dict(
            {"plan_path": "plan.md", "seed_size_warn_mb": 1, "seed_size_fail_mb": 10}
        )
        assert cfg.seed_size_warn_mb == 1.0
        assert cfg.seed_size_fail_mb == 10.0


# ---------------------------------------------------------------------------
# (b) forward_manifest de-dup — emitter no longer copies into artifacts
# ---------------------------------------------------------------------------

class TestForwardManifestSingleSerialization:
    def test_build_seed_artifacts_has_no_manifest_param(self):
        """The artifacts builder must not accept/copy the forward manifest —
        the seed's top-level field is the single serialization point."""
        import inspect
        from startd8.workflows.builtin.plan_ingestion_emitter import PhaseEmitter

        sig = inspect.signature(PhaseEmitter._build_seed_artifacts)
        assert "forward_manifest_dict" not in sig.parameters

    def test_sapper_loader_reads_top_level_manifest(self, tmp_path):
        from startd8.forward_manifest import ForwardFileSpec, ForwardManifest
        from startd8.sapper.host import load_from_ingestion_seed

        fm = ForwardManifest(
            file_specs={"app/jobs.py": ForwardFileSpec(file="app/jobs.py")}
        )
        seed = {
            "forward_manifest": fm.model_dump(),  # top-level (canonical)
            "artifacts": {
                "skeleton_sources": {"app/jobs.py": "def f(): ...\n"},
                # NOTE: no artifacts copy — post-de-dup seed shape
            },
        }
        p = tmp_path / "artisan-context-seed.json"
        p.write_text(json.dumps(seed))

        manifest, skeletons = load_from_ingestion_seed(str(p))
        assert "app/jobs.py" in skeletons
        # Full manifest reconstructed from the top-level field, not minimal fallback
        assert manifest.file_specs["app/jobs.py"].file == "app/jobs.py"
