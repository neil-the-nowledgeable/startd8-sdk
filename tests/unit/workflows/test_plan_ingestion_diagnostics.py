"""Tests for plan_ingestion_diagnostics — Kaizen Phase 0 (REQ-KPI-1xx, 3xx)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from startd8.workflows.builtin.plan_ingestion_diagnostics import (
    IngestionDiagnostic,
    PhaseDiagnostic,
    PlanIngestionKaizenConfig,
    TaskDensity,
    _MIN_DESCRIPTION_CHARS,
    build_diagnostic,
    compute_assess_quality,
    compute_density_warnings,
    compute_parse_quality,
    compute_refine_quality,
    compute_seed_quality,
    compute_task_density,
    load_kaizen_config,
    persist_diagnostic,
    persist_prompt_response,
)


# ── Helpers ──────────────────────────────────────────────────────────


@dataclass
class _FakeFeature:
    target_files: List[str]
    dependencies: List[str]
    api_signatures: List[str]


def _make_seed(
    *,
    tasks: Optional[List[Dict[str, Any]]] = None,
    architectural_context: Optional[str] = None,
    design_calibration: Optional[str] = None,
    service_metadata: Optional[str] = None,
    onboarding: Optional[str] = None,
    context_files: Optional[list] = None,
    project_metadata: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "tasks": tasks or [],
        "architectural_context": architectural_context,
        "design_calibration": design_calibration,
        "service_metadata": service_metadata,
        "onboarding": onboarding,
        "context_files": context_files,
        "project_metadata": project_metadata,
    }


# ── compute_parse_quality ────────────────────────────────────────────


class TestComputeParseQuality:
    def test_empty_features(self):
        result = compute_parse_quality([], {}, [])
        assert result["features_extracted"] == 0
        assert result["dep_graph_coverage"] == 0.0

    def test_with_features(self):
        features = [
            _FakeFeature(target_files=["a.py"], dependencies=["F-2"], api_signatures=["def foo()"]),
            _FakeFeature(target_files=["b.py", "c.py"], dependencies=[], api_signatures=[]),
        ]
        dep_graph = {"F-1": ["F-2"]}
        result = compute_parse_quality(features, dep_graph, ["a.py", "b.py"])
        assert result["features_extracted"] == 2
        assert result["files_mentioned"] == 2
        assert result["features_with_targets"] == 2
        assert result["features_with_deps"] == 1
        assert result["multi_file_features"] == 1
        assert result["features_with_signatures"] == 1
        assert result["dep_graph_coverage"] == 0.5


# ── compute_assess_quality ───────────────────────────────────────────


class TestComputeAssessQuality:
    def test_basic(self):
        result = compute_assess_quality(
            composite=55, route_value="artisan", threshold=40, dimensions=[3, 7, 5, 8, 6, 9, 4],
        )
        assert result["composite_score"] == 55
        assert result["route_decision"] == "artisan"
        assert result["route_margin"] == 15
        assert result["dimension_spread"] == 6  # 9 - 3

    def test_empty_dimensions(self):
        result = compute_assess_quality(30, "prime", 40, [])
        assert result["dimension_spread"] == 0


# ── compute_seed_quality ─────────────────────────────────────────────


class TestComputeSeedQuality:
    def test_perfect_seed(self):
        tasks = [
            {
                "config": {
                    "task_description": "Build the widget",
                    "context": {"target_files": ["widget.py"]},
                },
            },
        ]
        seed = _make_seed(
            tasks=tasks,
            architectural_context="MVC",
            design_calibration="standard",
            service_metadata="v1",
            onboarding="docs",
            context_files=["a.py"],
            project_metadata="proj",
        )
        score, warnings = compute_seed_quality(seed)
        assert score == 1.0
        assert warnings == []

    def test_empty_seed(self):
        score, warnings = compute_seed_quality(_make_seed())
        # 0.3*0 + 0.3*0 + 0.2*1 (schema valid) + 0.2*0 = 0.2
        assert score == pytest.approx(0.2, abs=0.01)
        assert "seed has no tasks" in warnings

    def test_partial_coverage(self):
        tasks = [
            {"config": {"task_description": "A task", "context": {}}},
            {"config": {"task_description": "", "context": {"target_files": ["x.py"]}}},
        ]
        seed = _make_seed(tasks=tasks, architectural_context="ctx")
        score, warnings = compute_seed_quality(seed)
        # desc_ratio=0.5, target_ratio=0.5, schema=1.0, coverage=1/6 fields → ~0.633
        assert 0.4 < score < 0.8
        assert any("missing description" in w for w in warnings)
        assert any("missing target_files" in w for w in warnings)

    def test_schema_invalid(self):
        tasks = [{"config": {"task_description": "t", "context": {"target_files": ["f"]}}}]
        seed = _make_seed(
            tasks=tasks,
            architectural_context="a", design_calibration="d",
            service_metadata="s", onboarding="o",
            context_files=["c"], project_metadata="p",
        )
        score, _ = compute_seed_quality(seed, schema_valid=False)
        # 0.3 + 0.3 + 0.0 + 0.2 = 0.8 (schema penalty)
        assert score == pytest.approx(0.8, abs=0.01)


# ── compute_refine_quality ───────────────────────────────────────────


class TestComputeRefineQuality:
    def test_no_review(self):
        result = compute_refine_quality(None)
        assert result["rounds_completed"] == 0
        assert result["acceptance_rate"] == 0.0

    def test_with_triage(self):
        review = {
            "rounds_completed": 2,
            "triage": {
                "accepted": ["s1", "s2", "s3"],
                "rejected": ["s4"],
            },
        }
        result = compute_refine_quality(review)
        assert result["suggestions_total"] == 4
        assert result["suggestions_accepted"] == 3
        assert result["acceptance_rate"] == 0.75


# ── compute_task_density ─────────────────────────────────────────────


class TestComputeTaskDensity:
    def test_basic(self):
        tasks = [
            {
                "task_id": "T-001",
                "config": {
                    "task_description": "Build REQ-001 widget\n```python\nfoo()```",
                },
            },
            {
                "task_id": "T-002",
                "config": {"task_description": "Simple task"},
            },
        ]
        result = compute_task_density(tasks)
        assert len(result) == 2
        assert result[0].task_id == "T-001"
        assert result[0].has_code_examples is True
        assert result[0].has_requirements_refs is True
        assert result[0].description_lines == 3  # 2 newlines → 3 lines
        assert result[1].has_code_examples is False
        assert result[1].has_requirements_refs is False

    def test_negative_scope_in_context(self):
        tasks = [
            {
                "task_id": "T-001",
                "config": {
                    "task_description": "Build widget",
                    "context": {"negative_scope": ["Do not modify auth"]},
                },
            },
        ]
        result = compute_task_density(tasks)
        assert result[0].has_negative_scope is True

    def test_negative_scope_absent(self):
        tasks = [
            {"task_id": "T-001", "config": {"task_description": "Build widget"}},
        ]
        result = compute_task_density(tasks)
        assert result[0].has_negative_scope is False

    def test_multi_segment_req_id_detected(self):
        """Multi-segment IDs like REQ-PMS-008 are detected as requirement refs."""
        tasks = [
            {
                "task_id": "T-001",
                "config": {
                    "task_description": "Implements REQ-PMS-008 logging standard",
                },
            },
        ]
        result = compute_task_density(tasks)
        assert result[0].has_requirements_refs is True


# ── compute_density_warnings ────────────────────────────────────────


class TestComputeDensityWarnings:
    def test_empty_density(self):
        assert compute_density_warnings([]) == []

    def test_shallow_descriptions(self):
        density = [
            TaskDensity(task_id="T-1", description_chars=100),
            TaskDensity(task_id="T-2", description_chars=600),
        ]
        warnings = compute_density_warnings(density)
        assert any(f"< {_MIN_DESCRIPTION_CHARS} chars" in w for w in warnings)

    def test_no_code_examples(self):
        density = [
            TaskDensity(task_id="T-1", description_chars=600, has_code_examples=False),
        ]
        warnings = compute_density_warnings(density)
        assert "no tasks have code examples" in " ".join(warnings)

    def test_some_code_examples_no_warning(self):
        density = [
            TaskDensity(task_id="T-1", description_chars=600, has_code_examples=True),
            TaskDensity(task_id="T-2", description_chars=600, has_code_examples=False),
        ]
        warnings = compute_density_warnings(density)
        assert not any("code examples" in w for w in warnings)

    def test_missing_requirements_refs(self):
        density = [
            TaskDensity(task_id="T-1", description_chars=600, has_requirements_refs=False),
            TaskDensity(task_id="T-2", description_chars=600, has_requirements_refs=False),
            TaskDensity(task_id="T-3", description_chars=600, has_requirements_refs=True),
        ]
        warnings = compute_density_warnings(density)
        assert any("missing requirements references" in w for w in warnings)

    def test_all_rich_no_warnings(self):
        density = [
            TaskDensity(
                task_id="T-1", description_chars=600,
                has_code_examples=True, has_requirements_refs=True,
            ),
        ]
        warnings = compute_density_warnings(density)
        assert warnings == []


# ── compute_seed_quality with task_density ──────────────────────────


class TestComputeSeedQualityWithDensity:
    def test_backward_compat_without_density(self):
        """Without task_density, original 4-component formula is used."""
        tasks = [{"config": {"task_description": "t", "context": {"target_files": ["f"]}}}]
        seed = _make_seed(
            tasks=tasks,
            architectural_context="a", design_calibration="d",
            service_metadata="s", onboarding="o",
            context_files=["c"], project_metadata="p",
        )
        score, _ = compute_seed_quality(seed)
        assert score == 1.0  # Same as original perfect score

    def test_shallow_descriptions_lower_score(self):
        """Shallow descriptions should produce lower score with density."""
        tasks = [{"config": {"task_description": "short", "context": {"target_files": ["f"]}}}]
        seed = _make_seed(
            tasks=tasks,
            architectural_context="a", design_calibration="d",
            service_metadata="s", onboarding="o",
            context_files=["c"], project_metadata="p",
        )
        density = [TaskDensity(task_id="T-1", description_chars=50)]
        score_with, _ = compute_seed_quality(seed, task_density=density)
        score_without, _ = compute_seed_quality(seed)
        assert score_with < score_without

    def test_rich_descriptions_high_score(self):
        """Rich descriptions with code+refs should score high."""
        tasks = [{"config": {"task_description": "x" * 600, "context": {"target_files": ["f"]}}}]
        seed = _make_seed(
            tasks=tasks,
            architectural_context="a", design_calibration="d",
            service_metadata="s", onboarding="o",
            context_files=["c"], project_metadata="p",
        )
        density = [TaskDensity(
            task_id="T-1", description_chars=600,
            has_code_examples=True, has_requirements_refs=True,
        )]
        score, _ = compute_seed_quality(seed, task_density=density)
        assert score >= 0.95

    def test_density_warnings_merged(self):
        """Density warnings should be merged into quality warnings."""
        tasks = [{"config": {"task_description": "short", "context": {"target_files": ["f"]}}}]
        seed = _make_seed(
            tasks=tasks,
            architectural_context="a", design_calibration="d",
            service_metadata="s", onboarding="o",
            context_files=["c"], project_metadata="p",
        )
        density = [TaskDensity(task_id="T-1", description_chars=50)]
        _, warnings = compute_seed_quality(seed, task_density=density)
        assert any(f"< {_MIN_DESCRIPTION_CHARS}" in w for w in warnings)

    def test_empty_density_list(self):
        """Empty density list should still use 6-component formula."""
        seed = _make_seed(
            architectural_context="a", design_calibration="d",
            service_metadata="s", onboarding="o",
            context_files=["c"], project_metadata="p",
        )
        score, _ = compute_seed_quality(seed, task_density=[])
        # desc=0, target=0, schema=1, coverage=1, depth=0, richness=0
        assert score == pytest.approx(0.30, abs=0.01)


# ── build_diagnostic ─────────────────────────────────────────────────


class TestBuildDiagnostic:
    def test_assembly(self):
        phases = {
            "parse": PhaseDiagnostic(phase="parse", time_ms=100, cost_usd=0.01,
                                      input_tokens=500, output_tokens=200),
            "assess": PhaseDiagnostic(phase="assess", time_ms=50, cost_usd=0.005,
                                       input_tokens=300, output_tokens=100),
        }
        diag = build_diagnostic(
            run_timestamp="2026-03-07T00:00:00Z",
            plan_source="/tmp/plan.md",
            plan_checksum="abc123",
            route="artisan",
            overall_success=True,
            phase_diagnostics=phases,
            seed_quality_score=0.85,
            quality_warnings=["no onboarding"],
        )
        assert diag.schema_version == "1.0.0"
        assert diag.totals["time_ms"] == 150
        assert diag.totals["cost_usd"] == pytest.approx(0.015, abs=1e-6)
        assert diag.totals["input_tokens"] == 800
        assert diag.seed_quality_score == 0.85
        assert diag.quality_warnings == ["no onboarding"]


# ── persist_diagnostic ───────────────────────────────────────────────


class TestPersistDiagnostic:
    def test_writes_json(self, tmp_path: Path):
        diag = build_diagnostic(
            run_timestamp="2026-03-07T00:00:00Z",
            plan_source="plan.md",
            plan_checksum="abc",
            route="prime",
            overall_success=True,
            phase_diagnostics={},
        )
        persist_diagnostic(diag, tmp_path)
        out = tmp_path / "plan-ingestion-diagnostic.json"
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["schema_version"] == "1.0.0"
        assert data["route"] == "prime"

    def test_advisory_no_raise_on_bad_path(self):
        """I/O failure must not raise."""
        diag = build_diagnostic(
            run_timestamp="t",
            plan_source="p",
            plan_checksum="c",
            route="prime",
            overall_success=True,
            phase_diagnostics={},
        )
        # Path that cannot be created
        persist_diagnostic(diag, Path("/nonexistent/deeply/nested/path"))
        # No exception raised — advisory persistence


# ── persist_prompt_response (Phase 1) ────────────────────────────────


class TestPersistPromptResponse:
    def test_creates_files(self, tmp_path: Path):
        persist_prompt_response(tmp_path, "parse", "prompt text", "response text")
        kaizen_dir = tmp_path / "kaizen-prompts"
        assert (kaizen_dir / "parse_prompt.txt").read_text() == "prompt text"
        assert (kaizen_dir / "parse_response.txt").read_text() == "response text"

    def test_truncation(self, tmp_path: Path):
        big_text = "x" * 5000
        persist_prompt_response(tmp_path, "assess", big_text, "short", max_bytes=1000)
        prompt_path = tmp_path / "kaizen-prompts" / "assess_prompt.txt"
        content = prompt_path.read_text()
        assert len(content) < 5000
        assert "TRUNCATED at 1000 bytes" in content
        # Response should not be truncated
        resp_path = tmp_path / "kaizen-prompts" / "assess_response.txt"
        assert resp_path.read_text() == "short"

    def test_advisory_no_raise(self):
        """I/O failure must not raise."""
        persist_prompt_response(
            Path("/nonexistent/deeply/nested"), "parse", "p", "r",
        )
        # No exception raised

    def test_multiple_phases(self, tmp_path: Path):
        persist_prompt_response(tmp_path, "parse", "p1", "r1")
        persist_prompt_response(tmp_path, "assess", "p2", "r2")
        persist_prompt_response(tmp_path, "transform", "p3", "r3")
        kaizen_dir = tmp_path / "kaizen-prompts"
        assert len(list(kaizen_dir.iterdir())) == 6  # 3 phases × 2 files


# ── load_kaizen_config (Phase 2) ─────────────────────────────────────


class TestLoadKaizenConfig:
    def test_full_config(self, tmp_path: Path):
        cfg = {
            "plan_ingestion_kaizen": {
                "parse_prompt_suffix": "\nAlways use code fences.",
                "assess_prompt_suffix": "\nBe conservative.",
                "transform_prompt_suffix": "\nUse headings.",
                "complexity_threshold_override": 50,
            }
        }
        p = tmp_path / "kaizen.json"
        p.write_text(json.dumps(cfg))
        result = load_kaizen_config(p)
        assert result.parse_prompt_suffix == "\nAlways use code fences."
        assert result.assess_prompt_suffix == "\nBe conservative."
        assert result.transform_prompt_suffix == "\nUse headings."
        assert result.complexity_threshold_override == 50

    def test_empty_config(self, tmp_path: Path):
        p = tmp_path / "kaizen.json"
        p.write_text("{}")
        result = load_kaizen_config(p)
        assert result.parse_prompt_suffix == ""
        assert result.complexity_threshold_override is None

    def test_unknown_keys_ignored(self, tmp_path: Path):
        cfg = {
            "plan_ingestion_kaizen": {
                "parse_prompt_suffix": "test",
                "unknown_field": "ignored",
            }
        }
        p = tmp_path / "kaizen.json"
        p.write_text(json.dumps(cfg))
        result = load_kaizen_config(p)
        assert result.parse_prompt_suffix == "test"
        assert not hasattr(result, "unknown_field")

    def test_partial_config(self, tmp_path: Path):
        cfg = {"plan_ingestion_kaizen": {"complexity_threshold_override": 30}}
        p = tmp_path / "kaizen.json"
        p.write_text(json.dumps(cfg))
        result = load_kaizen_config(p)
        assert result.complexity_threshold_override == 30
        assert result.parse_prompt_suffix == ""

    def test_refine_fields_defaults(self):
        cfg = PlanIngestionKaizenConfig()
        assert cfg.refine_scope_override == ""
        assert cfg.refine_review_profile == {}
        assert cfg.refine_rounds_override is None

    def test_refine_fields_from_json(self, tmp_path: Path):
        cfg = {
            "plan_ingestion_kaizen": {
                "refine_scope_override": "Focus on code examples.",
                "refine_review_profile": {
                    "persona": "test persona",
                    "focus": "test focus",
                    "areas": ["completeness"],
                },
                "refine_rounds_override": 2,
            }
        }
        p = tmp_path / "kaizen.json"
        p.write_text(json.dumps(cfg))
        result = load_kaizen_config(p)
        assert result.refine_scope_override == "Focus on code examples."
        assert result.refine_review_profile["persona"] == "test persona"
        assert result.refine_rounds_override == 2

    def test_refine_fields_partial(self, tmp_path: Path):
        cfg = {"plan_ingestion_kaizen": {"refine_rounds_override": 3}}
        p = tmp_path / "kaizen.json"
        p.write_text(json.dumps(cfg))
        result = load_kaizen_config(p)
        assert result.refine_rounds_override == 3
        assert result.refine_scope_override == ""
        assert result.refine_review_profile == {}


# ── Cross-run trend script (Phase 2) ────────────────────────────────


class TestPlanIngestionTrends:
    def test_discover_and_format(self, tmp_path: Path):
        """End-to-end: create 2 diagnostic files, run trend analysis."""
        from scripts.plan_ingestion_trends import (
            discover_diagnostics,
            extract_metrics,
            format_table,
        )

        # Create two run directories with diagnostic files
        for i, ts in enumerate(["2026-03-01T10:00:00Z", "2026-03-02T10:00:00Z"]):
            run_dir = tmp_path / f"run-{i}"
            run_dir.mkdir()
            diag = {
                "schema_version": "1.0.0",
                "run_timestamp": ts,
                "route": "artisan",
                "overall_success": True,
                "phases": {
                    "parse": {
                        "quality_signals": {"features_extracted": 3 + i},
                        "code_extraction_fallback": i == 0,
                    },
                    "assess": {
                        "quality_signals": {"composite_score": 45, "route_margin": 5},
                    },
                },
                "totals": {"cost_usd": 0.01 * (i + 1), "time_ms": 5000},
                "seed_quality_score": 0.7 + i * 0.1,
                "quality_warnings": ["warn"] if i == 0 else [],
            }
            (run_dir / "plan-ingestion-diagnostic.json").write_text(
                json.dumps(diag)
            )

        diagnostics = discover_diagnostics(tmp_path)
        assert len(diagnostics) == 2

        metrics = [extract_metrics(d) for d in diagnostics]
        assert metrics[0]["features"] == 3
        assert metrics[1]["features"] == 4
        assert metrics[0]["fallbacks"] == 1
        assert metrics[1]["fallbacks"] == 0

        table = format_table(metrics)
        assert "artisan" in table
        assert "seed" in table.lower() or "Seed" in table

    def test_empty_dir(self, tmp_path: Path):
        from scripts.plan_ingestion_trends import discover_diagnostics
        assert discover_diagnostics(tmp_path) == []

    def test_main_json_output(self, tmp_path: Path):
        from scripts.plan_ingestion_trends import main

        run_dir = tmp_path / "run-0"
        run_dir.mkdir()
        diag = {
            "schema_version": "1.0.0",
            "run_timestamp": "2026-03-01T10:00:00Z",
            "route": "prime",
            "overall_success": True,
            "phases": {},
            "totals": {},
            "seed_quality_score": 0.5,
            "quality_warnings": [],
        }
        (run_dir / "plan-ingestion-diagnostic.json").write_text(json.dumps(diag))

        rc = main(["--runs-dir", str(tmp_path), "--json"])
        assert rc == 0


# ── Seed quality injection + gate (Phase 3) ──────────────────────────


def _make_seed_with_quality(score: float, warnings: Optional[List[str]] = None) -> Dict[str, Any]:
    """Create a minimal seed dict with _ingestion_quality block."""
    return {
        "tasks": [],
        "_ingestion_quality": {
            "seed_quality_score": score,
            "features_extracted": 3,
            "multi_file_features": 1,
            "route_margin": 10,
            "field_coverage_warnings": warnings or [],
            "diagnostic_report_path": "plan-ingestion-diagnostic.json",
        },
    }


class TestIngestionQualityInSeed:
    def test_quality_block_structure(self):
        seed = _make_seed_with_quality(0.85, ["no onboarding"])
        q = seed["_ingestion_quality"]
        assert q["seed_quality_score"] == 0.85
        assert q["features_extracted"] == 3
        assert q["multi_file_features"] == 1
        assert q["route_margin"] == 10
        assert q["field_coverage_warnings"] == ["no onboarding"]
        assert q["diagnostic_report_path"] == "plan-ingestion-diagnostic.json"


class TestCheckSeedQuality:
    def test_passes_high_score(self, tmp_path: Path):
        from scripts.check_seed_quality import check_seed_quality

        seed_path = tmp_path / "seed.json"
        seed_path.write_text(json.dumps(_make_seed_with_quality(0.9)))
        passes, score, warnings = check_seed_quality(seed_path, threshold=0.5)
        assert passes is True
        assert score == 0.9

    def test_warns_low_score(self, tmp_path: Path):
        from scripts.check_seed_quality import check_seed_quality

        seed_path = tmp_path / "seed.json"
        seed_path.write_text(json.dumps(
            _make_seed_with_quality(0.3, ["no architectural_context", "no onboarding"])
        ))
        passes, score, warnings = check_seed_quality(seed_path, threshold=0.5)
        assert passes is False
        assert score == 0.3
        assert len(warnings) == 2

    def test_main_exit_code_ok(self, tmp_path: Path):
        from scripts.check_seed_quality import main

        seed_path = tmp_path / "seed.json"
        seed_path.write_text(json.dumps(_make_seed_with_quality(0.9)))
        rc = main([str(seed_path), "--threshold", "0.5"])
        assert rc == 0

    def test_main_exit_code_warn(self, tmp_path: Path):
        from scripts.check_seed_quality import main

        seed_path = tmp_path / "seed.json"
        seed_path.write_text(json.dumps(_make_seed_with_quality(0.3)))
        rc = main([str(seed_path), "--threshold", "0.5"])
        assert rc == 1

    def test_main_missing_file(self, tmp_path: Path):
        from scripts.check_seed_quality import main

        rc = main([str(tmp_path / "nonexistent.json")])
        assert rc == 2

    def test_no_quality_block_defaults_to_pass(self, tmp_path: Path):
        from scripts.check_seed_quality import check_seed_quality

        seed_path = tmp_path / "seed.json"
        seed_path.write_text(json.dumps({"tasks": []}))
        passes, score, warnings = check_seed_quality(seed_path, threshold=0.5)
        assert passes is True
        assert score == 1.0  # default when block missing
