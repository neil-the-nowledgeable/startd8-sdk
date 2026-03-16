"""Tests for service communication graph consumption — REQ-SIG-200/201.

Covers:
- Graph extraction from onboarding to seed artifacts
- Shared modules merge into architectural context
- Strategy 3 in _collect_dependency_imports
- Backward compatibility when graph is absent
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_GRAPH = {
    "services": {
        "emailservice": {
            "imports": ["demo_pb2", "demo_pb2_grpc"],
            "rpc_calls": [],
            "protocol": "grpc",
        },
        "recommendationservice": {
            "imports": ["demo_pb2", "demo_pb2_grpc", "logger"],
            "rpc_calls": [{"target_service": "productcatalogservice", "method": "ListProducts"}],
            "protocol": "grpc",
        },
    },
    "shared_modules": {
        "demo_pb2": {"type": "proto_stub", "used_by": ["emailservice", "recommendationservice"]},
        "demo_pb2_grpc": {"type": "proto_stub", "used_by": ["emailservice", "recommendationservice"]},
        "logger": {"type": "shared_lib", "used_by": ["recommendationservice"]},
    },
    "proto_schemas": ["protos/demo.proto"],
}


# ---------------------------------------------------------------------------
# Phase 2: Architectural context merge
# ---------------------------------------------------------------------------

class TestSharedModulesMerge:
    """REQ-SIG-200 §3.1: graph shared_modules merged into arch context."""

    def test_merge_from_graph(self):
        from startd8.workflows.builtin.plan_ingestion_workflow import PlanIngestionWorkflow

        # Create minimal ParsedPlan mock
        plan = MagicMock()
        plan.goals = ["Build microservices"]
        plan.features = []
        plan.dependency_graph = {}

        manifest_context = {"service_communication_graph": SAMPLE_GRAPH}

        ctx = PlanIngestionWorkflow._derive_architectural_context(plan, manifest_context)

        # Graph modules should be in shared_modules
        names = [m.get("name") for m in ctx["shared_modules"]]
        assert "demo_pb2" in names
        assert "demo_pb2_grpc" in names
        assert "logger" in names

    def test_no_graph_backward_compat(self):
        from startd8.workflows.builtin.plan_ingestion_workflow import PlanIngestionWorkflow

        plan = MagicMock()
        plan.goals = []
        plan.features = []
        plan.dependency_graph = {}

        ctx = PlanIngestionWorkflow._derive_architectural_context(plan, {})
        # Should work fine, shared_modules is empty list
        assert ctx["shared_modules"] == []

    def test_empty_graph_no_crash(self):
        from startd8.workflows.builtin.plan_ingestion_workflow import PlanIngestionWorkflow

        plan = MagicMock()
        plan.goals = []
        plan.features = []
        plan.dependency_graph = {}

        ctx = PlanIngestionWorkflow._derive_architectural_context(
            plan, {"service_communication_graph": {}}
        )
        assert ctx["shared_modules"] == []


# ---------------------------------------------------------------------------
# Phase 3: Strategy 3 in _collect_dependency_imports
# ---------------------------------------------------------------------------

class TestStrategy3CommunicationGraph:
    """REQ-SIG-201: graph-based import extraction in dependency collection."""

    def _make_feature(self, *, feature_id, deps, target_files):
        f = MagicMock()
        f.id = feature_id
        f.name = feature_id
        f.dependencies = deps
        f.target_files = target_files
        f.description = ""
        return f

    def _make_dep(self, *, target_files):
        d = MagicMock()
        d.description = ""
        d.target_files = target_files
        return d

    def test_graph_provides_imports(self):
        """Strategy 3: graph gives imports when desc and manifest miss."""
        from startd8.contractors.prime_contractor import (
            PrimeContractorWorkflow,
            SeedContext,
        )

        wf = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)
        wf._seed_context = SeedContext(
            service_communication_graph=SAMPLE_GRAPH,
        )
        wf._forward_manifest = None

        dep = self._make_dep(target_files=["src/emailservice/email_server.py"])
        feature = self._make_feature(
            feature_id="PI-004",
            deps=["PI-003"],
            target_files=["src/emailservice/email_client.py"],
        )

        queue = MagicMock()
        queue.get_feature.return_value = dep
        wf.queue = queue

        result = wf._collect_dependency_imports(feature)

        assert "PI-003" in result
        modules = result["PI-003"]["modules"]
        assert "demo_pb2" in modules
        assert "demo_pb2_grpc" in modules

    def test_no_graph_no_crash(self):
        """Without graph, Strategy 3 is silently skipped."""
        from startd8.contractors.prime_contractor import (
            PrimeContractorWorkflow,
            SeedContext,
        )

        wf = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)
        wf._seed_context = SeedContext()  # no graph
        wf._forward_manifest = None

        dep = self._make_dep(target_files=["src/emailservice/server.py"])
        feature = self._make_feature(
            feature_id="PI-004",
            deps=["PI-003"],
            target_files=["src/emailservice/client.py"],
        )

        queue = MagicMock()
        queue.get_feature.return_value = dep
        wf.queue = queue

        result = wf._collect_dependency_imports(feature)
        # No modules from any strategy
        assert result == {}

    def test_case_insensitive_match(self):
        """Graph keys are matched case-insensitively against path components."""
        from startd8.contractors.prime_contractor import (
            PrimeContractorWorkflow,
            SeedContext,
        )

        # Graph has "EmailService" but path has "emailservice"
        graph = {
            "services": {
                "EmailService": {"imports": ["proto_mod"], "protocol": "grpc"},
            },
            "shared_modules": {},
        }

        wf = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)
        wf._seed_context = SeedContext(service_communication_graph=graph)
        wf._forward_manifest = None

        dep = self._make_dep(target_files=["src/emailservice/server.py"])
        feature = self._make_feature(
            feature_id="F2", deps=["F1"], target_files=["client.py"],
        )

        queue = MagicMock()
        queue.get_feature.return_value = dep
        wf.queue = queue

        result = wf._collect_dependency_imports(feature)
        assert "F1" in result
        assert "proto_mod" in result["F1"]["modules"]
