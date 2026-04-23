"""Tests for instrumentation contract and guidance threading (REQ-TCW-250, REQ-TCW-251).

Verifies that load_seed_context() extracts and normalizes instrumentation_hints
from onboarding metadata, and that _build_generation_context() threads both
the instrumentation contract and guidance into gen_context.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

from startd8.contractors.context_resolution import (
    PipelineContextStrategy,
    StandaloneContextStrategy,
)
from startd8.contractors.prime_contractor import (
    PrimeContractorWorkflow,
    SeedContext,
)


def _make_workflow(
    project_root: Path,
    execution_mode: str = "standalone",
) -> PrimeContractorWorkflow:
    """Create a minimal PrimeContractorWorkflow for testing via __new__."""
    wf = object.__new__(PrimeContractorWorkflow)
    wf.project_root = project_root
    wf.dry_run = False
    wf.max_retries = 3
    wf.check_truncation = True
    wf.force_regenerate = False
    wf.total_cost_usd = 0.0
    wf.total_input_tokens = 0
    wf.total_output_tokens = 0
    wf.integration_history = []
    wf._validation_override = None
    wf.strict_validation = False

    seed = SeedContext(execution_mode=execution_mode)
    wf._seed_context = seed

    if execution_mode == "pipeline":
        wf._context_strategy = PipelineContextStrategy()
    else:
        wf._context_strategy = StandaloneContextStrategy()

    wf._strict_mode = False
    wf.seed_service_metadata = {}
    wf.seed_forward_manifest = None
    wf.plan_document_text = None
    wf._forward_manifest = None
    wf._engine = type("_StubEngine", (), {"_forward_manifest": None})()
    wf._domain_checklist = None
    wf._current_enrichment = None
    wf._language_profile = None
    wf._skeleton_sources = {}
    wf._security_contract = None
    wf._instrumentation_contract = None
    wf._guidance_context = None
    wf.edit_min_pct = 0.0
    wf._complexity_routing_enabled = False
    wf._resolved_artifact_params = None
    wf._expected_output_contracts = None
    wf._design_calibration_hints = None
    wf._quality_accumulator = None

    return wf


class TestInstrumentationContractThreading:
    """REQ-TCW-250: instrumentation contract extraction and threading."""

    def test_load_seed_context_extracts_instrumentation_hints(self, tmp_path):
        """instrumentation_hints from onboarding are normalized and stored."""
        wf = _make_workflow(project_root=tmp_path)
        wf._seed_context = None

        seed_data = {
            "onboarding": {
                "instrumentation_hints": {
                    "metrics": {
                        "convention_based": [
                            {"name": "rpc.server.duration", "type": "histogram"},
                        ],
                        "manifest_declared": [
                            {"name": "custom_metric", "source": "manifest"},
                        ],
                    },
                    "traces": {"required": [{"span_name": "grpc.server"}]},
                },
            },
        }
        wf.load_seed_context(seed_data)

        assert wf._instrumentation_contract is not None
        # Should be normalized: metrics.required populated
        assert "required" in wf._instrumentation_contract["metrics"]
        assert len(wf._instrumentation_contract["metrics"]["required"]) == 2
        # Original fields preserved
        assert "convention_based" in wf._instrumentation_contract["metrics"]

    def test_load_seed_context_no_hints(self, tmp_path):
        """No instrumentation_hints → _instrumentation_contract is None."""
        wf = _make_workflow(project_root=tmp_path)
        wf._seed_context = None

        wf.load_seed_context({"onboarding": {}})

        assert wf._instrumentation_contract is None

    def test_build_generation_context_threads_contract(self, tmp_path):
        """_build_generation_context() includes instrumentation_contract."""
        wf = _make_workflow(project_root=tmp_path)
        wf._seed_context = None

        seed_data = {
            "onboarding": {
                "instrumentation_hints": {
                    "metrics": {
                        "required": [{"name": "request_count"}],
                    },
                },
            },
        }
        wf.load_seed_context(seed_data)

        # Create a minimal feature
        from startd8.contractors.queue import FeatureSpec
        feature = FeatureSpec(
            id="F-001",
            name="test-feature",
            target_files=["src/server.py"],
            description="Test feature",
        )

        gen_context = wf._build_generation_context(feature)
        assert "instrumentation_contract" in gen_context
        assert gen_context["instrumentation_contract"]["metrics"]["required"][0]["name"] == "request_count"


class TestGenContextJsHostHints:
    """REQ-JSF-009: ``js_host_id`` / ``js_dialect_id`` from forward manifest hints."""

    def test_readme_resolves_node_via_manifest_hint(self, tmp_path):
        from startd8.contractors.queue import FeatureSpec
        from startd8.forward_manifest import ForwardFileSpec, ForwardManifest
        from startd8.languages.js_metadata import JS_DIALECT_PLAIN, JS_HOST_JAVASCRIPT_NODE

        wf = _make_workflow(project_root=tmp_path)
        wf._forward_manifest = ForwardManifest(
            file_specs={
                "README.md": ForwardFileSpec(
                    file="README.md", elements=[], language="nodejs",
                ),
            },
        )
        feature = FeatureSpec(
            id="F-001",
            name="readme-task",
            target_files=["README.md"],
            description="Doc",
        )
        gen_context = wf._build_generation_context(feature)
        assert gen_context["language_profile"].language_id == "nodejs"
        assert gen_context["js_host_id"] == JS_HOST_JAVASCRIPT_NODE
        assert gen_context["js_dialect_id"] == JS_DIALECT_PLAIN


class TestGuidanceThreading:
    """REQ-TCW-251: guidance context extraction and threading."""

    def test_load_seed_context_extracts_guidance(self, tmp_path):
        """guidance from onboarding is stored."""
        wf = _make_workflow(project_root=tmp_path)
        wf._seed_context = None

        seed_data = {
            "onboarding": {
                "guidance": {
                    "constraints": ["Use gRPC interceptors for instrumentation"],
                    "focus": "observability",
                    "preferences": {"style": "concise"},
                },
            },
        }
        wf.load_seed_context(seed_data)

        assert wf._guidance_context is not None
        assert "constraints" in wf._guidance_context
        assert wf._guidance_context["focus"] == "observability"

    def test_load_seed_context_no_guidance(self, tmp_path):
        """No guidance → _guidance_context is None."""
        wf = _make_workflow(project_root=tmp_path)
        wf._seed_context = None

        wf.load_seed_context({"onboarding": {}})

        assert wf._guidance_context is None

    def test_build_generation_context_threads_guidance(self, tmp_path):
        """_build_generation_context() includes guidance when present."""
        wf = _make_workflow(project_root=tmp_path)
        wf._seed_context = None

        seed_data = {
            "onboarding": {
                "guidance": {
                    "constraints": ["Use standard library only"],
                },
            },
        }
        wf.load_seed_context(seed_data)

        from startd8.contractors.queue import FeatureSpec
        feature = FeatureSpec(
            id="F-001",
            name="test-feature",
            target_files=["src/server.py"],
            description="Test feature",
        )

        gen_context = wf._build_generation_context(feature)
        assert "guidance" in gen_context
        assert gen_context["guidance"]["constraints"] == ["Use standard library only"]
