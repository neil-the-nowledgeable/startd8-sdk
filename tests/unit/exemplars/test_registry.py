"""Tests for the ExemplarRegistry (REQ-PEP-001)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from startd8.exemplars.models import (
    ConfigFingerprint,
    ExemplarEntry,
    ExemplarScores,
    MAX_REGISTRY_SIZE,
)
from startd8.exemplars.registry import ExemplarRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(
    *,
    language: str = "java",
    file_type: str = "source",
    transport: str = "grpc",
    archetype: str = "grpc_server",
    maturity: int = 1,
    run_id: str = "run-001",
    feature_id: str = "PI-001",
    req_score: float = 1.0,
    dq_score: float = 1.0,
    cost: float = 0.10,
    timestamp: str = "2026-03-18T00:00:00Z",
) -> ExemplarEntry:
    fp = ConfigFingerprint(language, file_type, transport, archetype)
    return ExemplarEntry(
        id=ExemplarEntry.make_id(fp, run_id, feature_id),
        fingerprint=fp,
        maturity=maturity,
        source_run_id=run_id,
        source_feature_id=feature_id,
        spec_artifact_path=f"kaizen-prompts/standalone/{feature_id}/spec.md",
        code_artifact_path=f"generated/src/{feature_id}.java",
        draft_artifact_path=f"kaizen-prompts/standalone/{feature_id}/draft.md",
        seed_task_digest="abcdef0123456789",
        scores=ExemplarScores(
            requirement_score=req_score,
            disk_quality_score=dq_score,
            cost_usd=cost,
        ),
        agent_specs={"lead": "anthropic:claude-sonnet-4-20250514", "drafter": "anthropic:claude-sonnet-4-20250514"},
        code_summary="package main\n\nfunc main() {}",
        timestamp=timestamp,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExemplarRegistryBasic:
    """Core add/find operations."""

    def test_add_and_find_exact(self):
        reg = ExemplarRegistry(project_id="test")
        entry = _make_entry()
        reg.add(entry)

        fp = ConfigFingerprint("java", "source", "grpc", "grpc_server")
        result = reg.find_best_match(fp)
        assert result is not None
        assert result.id == entry.id

    def test_find_returns_none_when_empty(self):
        reg = ExemplarRegistry()
        fp = ConfigFingerprint("java", "source", "grpc", "grpc_server")
        assert reg.find_best_match(fp) is None

    def test_find_partial_match(self):
        reg = ExemplarRegistry()
        reg.add(_make_entry(transport="grpc"))

        # Search with different transport
        fp = ConfigFingerprint("java", "source", "http", "grpc_server")
        result = reg.find_best_match(fp)
        assert result is not None

    def test_find_no_match(self):
        reg = ExemplarRegistry()
        reg.add(_make_entry(language="java"))

        fp = ConfigFingerprint("go", "source", "grpc", "grpc_server")
        assert reg.find_best_match(fp) is None

    def test_exact_match_preferred_over_partial(self):
        reg = ExemplarRegistry()
        partial = _make_entry(transport="http", run_id="run-001")
        exact = _make_entry(transport="grpc", run_id="run-002")
        reg.add(partial)
        reg.add(exact)

        fp = ConfigFingerprint("java", "source", "grpc", "grpc_server")
        result = reg.find_best_match(fp)
        assert result is not None
        assert result.source_run_id == "run-002"

    def test_higher_maturity_preferred(self):
        reg = ExemplarRegistry()
        reg.add(_make_entry(maturity=1, run_id="run-001"))
        reg.add(_make_entry(maturity=2, run_id="run-002"))

        fp = ConfigFingerprint("java", "source", "grpc", "grpc_server")
        result = reg.find_best_match(fp)
        assert result is not None
        assert result.maturity == 2

    def test_deduplicate_by_id(self):
        reg = ExemplarRegistry()
        entry = _make_entry()
        reg.add(entry)
        reg.add(entry)  # same ID
        assert len(reg) == 1

    def test_get_match_type(self):
        reg = ExemplarRegistry()
        reg.add(_make_entry(transport="grpc"))

        exact_fp = ConfigFingerprint("java", "source", "grpc", "grpc_server")
        assert reg.get_match_type(exact_fp) == "exact"

        partial_fp = ConfigFingerprint("java", "source", "http", "grpc_server")
        assert reg.get_match_type(partial_fp) == "partial"

        no_fp = ConfigFingerprint("python", "test", "none", "unit_test")
        assert reg.get_match_type(no_fp) == "none"


class TestExemplarRegistryPersistence:
    """Save/load round-trip."""

    def test_save_and_load(self, tmp_path):
        reg = ExemplarRegistry(project_id="test-project")
        reg.add(_make_entry(run_id="run-001"))
        reg.add(_make_entry(run_id="run-002", feature_id="PI-002"))

        path = tmp_path / "registry.json"
        reg.save(path)

        loaded = ExemplarRegistry.load(path)
        assert len(loaded) == 2
        assert loaded.project_id == "test-project"

    def test_load_nonexistent_returns_empty(self, tmp_path):
        reg = ExemplarRegistry.load(tmp_path / "nope.json")
        assert len(reg) == 0

    def test_load_malformed_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")
        reg = ExemplarRegistry.load(path)
        assert len(reg) == 0

    def test_round_trip_preserves_fingerprint(self, tmp_path):
        reg = ExemplarRegistry()
        entry = _make_entry(language="go", archetype="grpc_client")
        reg.add(entry)

        path = tmp_path / "reg.json"
        reg.save(path)
        loaded = ExemplarRegistry.load(path)

        result = loaded.exemplars[0]
        assert result.fingerprint.language == "go"
        assert result.fingerprint.archetype == "grpc_client"

    def test_round_trip_preserves_scores(self, tmp_path):
        reg = ExemplarRegistry()
        entry = _make_entry(req_score=0.95, dq_score=0.88, cost=0.25)
        reg.add(entry)

        path = tmp_path / "reg.json"
        reg.save(path)
        loaded = ExemplarRegistry.load(path)

        result = loaded.exemplars[0]
        assert result.scores.requirement_score == 0.95
        assert result.scores.disk_quality_score == 0.88
        assert result.scores.cost_usd == 0.25


class TestExemplarRegistryEviction:
    """Size bound enforcement."""

    def test_evicts_when_over_limit(self):
        reg = ExemplarRegistry()
        # Add MAX_REGISTRY_SIZE + 5 entries
        for i in range(MAX_REGISTRY_SIZE + 5):
            reg.add(_make_entry(
                run_id=f"run-{i:04d}",
                feature_id=f"PI-{i:04d}",
                timestamp=f"2026-01-{(i % 28) + 1:02d}T00:00:00Z",
            ))
        assert len(reg) == MAX_REGISTRY_SIZE

    def test_evicts_lowest_maturity_first(self):
        reg = ExemplarRegistry()
        # Fill with low-maturity entries
        for i in range(MAX_REGISTRY_SIZE):
            reg.add(_make_entry(
                run_id=f"run-{i:04d}",
                feature_id=f"PI-{i:04d}",
                maturity=0,
            ))
        # Add one high-maturity entry that should survive
        high = _make_entry(run_id="run-high", feature_id="PI-HIGH", maturity=3)
        reg.add(high)

        assert len(reg) == MAX_REGISTRY_SIZE
        ids = {e.id for e in reg.exemplars}
        assert high.id in ids


class TestMaturityPromotion:
    """REQ-PEP-003: auto-promote maturity."""

    def test_promote_level_1_to_2(self):
        reg = ExemplarRegistry()
        reg.add(_make_entry(run_id="run-001", maturity=1))
        reg.add(_make_entry(run_id="run-002", maturity=1))

        promotions = reg.promote_maturity()
        assert len(promotions) == 2
        assert all(p["new_level"] == 2 for p in promotions)

    def test_no_promotion_same_run(self):
        reg = ExemplarRegistry()
        reg.add(_make_entry(run_id="run-001", feature_id="PI-001", maturity=1))
        reg.add(_make_entry(run_id="run-001", feature_id="PI-002", maturity=1))

        promotions = reg.promote_maturity()
        assert len(promotions) == 0  # Same run, no promotion

    def test_promote_level_2_to_3(self):
        reg = ExemplarRegistry()
        for i in range(3):
            reg.add(_make_entry(
                run_id=f"run-{i:03d}",
                feature_id=f"PI-{i:03d}",
                maturity=2,
            ))

        promotions = reg.promote_maturity()
        assert len(promotions) == 3
        assert all(p["new_level"] == 3 for p in promotions)


class TestConfigFingerprint:
    """REQ-PEP-002: fingerprint computation."""

    def test_from_java_source(self):
        fp = ConfigFingerprint.compute(
            "src/main/java/AdService.java",
            language="java",
            transport="grpc",
        )
        assert fp.language == "java"
        assert fp.file_type == "source"
        assert fp.transport == "grpc"
        assert fp.archetype == "grpc_server"

    def test_from_go_test(self):
        fp = ConfigFingerprint.compute("pkg/server_test.go")
        assert fp.language == "go"
        assert fp.file_type == "test"
        assert fp.archetype == "unit_test"

    def test_from_dockerfile(self):
        fp = ConfigFingerprint.compute("Dockerfile")
        assert fp.file_type == "dockerfile"
        assert fp.archetype == "multi_stage_dockerfile"

    def test_from_build_gradle(self):
        fp = ConfigFingerprint.compute("build.gradle", language="java")
        assert fp.file_type == "build_config"
        assert fp.archetype == "gradle_build"

    def test_from_go_mod(self):
        fp = ConfigFingerprint.compute("go.mod", language="go")
        assert fp.file_type == "build_config"
        assert fp.archetype == "go_mod"

    def test_from_package_json(self):
        fp = ConfigFingerprint.compute("package.json", language="nodejs")
        assert fp.file_type == "build_config"
        assert fp.archetype == "package_json"

    def test_language_inferred_from_extension(self):
        fp = ConfigFingerprint.compute("main.go")
        assert fp.language == "go"

    def test_string_roundtrip(self):
        fp = ConfigFingerprint("java", "source", "grpc", "grpc_server")
        s = str(fp)
        assert s == "java:source:grpc:grpc_server"
        restored = ConfigFingerprint.from_string(s)
        assert restored == fp

    def test_exact_and_partial_matching(self):
        fp1 = ConfigFingerprint("java", "source", "grpc", "grpc_server")
        fp2 = ConfigFingerprint("java", "source", "http", "grpc_server")
        assert fp1.matches_exact(fp1)
        assert not fp1.matches_exact(fp2)
        assert fp1.matches_partial(fp2)  # same except transport

    def test_java_test_detection(self):
        fp = ConfigFingerprint.compute("src/test/AdServiceTest.java")
        assert fp.file_type == "test"
        assert fp.archetype == "unit_test"

    def test_python_test_detection(self):
        fp = ConfigFingerprint.compute("tests/test_server.py")
        assert fp.file_type == "test"
        assert fp.archetype == "unit_test"


class TestExemplarEntry:
    """ExemplarEntry model."""

    def test_make_id_deterministic(self):
        fp = ConfigFingerprint("java", "source", "grpc", "grpc_server")
        id1 = ExemplarEntry.make_id(fp, "run-001", "PI-001")
        id2 = ExemplarEntry.make_id(fp, "run-001", "PI-001")
        assert id1 == id2
        assert id1.startswith("ex-")

    def test_make_id_differs_for_different_runs(self):
        fp = ConfigFingerprint("java", "source", "grpc", "grpc_server")
        id1 = ExemplarEntry.make_id(fp, "run-001", "PI-001")
        id2 = ExemplarEntry.make_id(fp, "run-002", "PI-001")
        assert id1 != id2

    def test_to_dict_and_from_dict(self):
        entry = _make_entry()
        d = entry.to_dict()
        restored = ExemplarEntry.from_dict(d)
        assert restored.id == entry.id
        assert restored.fingerprint == entry.fingerprint
        assert restored.scores.requirement_score == entry.scores.requirement_score
