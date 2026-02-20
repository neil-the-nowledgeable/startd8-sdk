"""Tests for AR-810 ServiceMetadataPreflightRule."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from startd8.workflows.builtin.preflight_rules.rules_common import (
    ServiceMetadataPreflightRule,
)
from startd8.workflows.builtin.preflight_rules._base import RuleContext
from startd8.workflows.builtin.domain_preflight_models import (
    CheckStatus,
    TaskDomain,
)


def _make_ctx(
    target_file: str,
    project_root: Path,
    domain: TaskDomain = TaskDomain.PYTHON_SINGLE_MODULE,
) -> RuleContext:
    """Build a minimal RuleContext for testing."""
    target_path = project_root / target_file
    return RuleContext(
        target_file=target_file,
        target_path=target_path,
        target_dir=target_path.parent,
        project_root=project_root,
        domain=domain,
        available_deps=None,  # type: ignore[arg-type]
    )


class TestServiceMetadataPreflightRule:

    def test_non_service_file_returns_none(self, tmp_path: Path):
        """Non-service files (e.g. utils.py) return None."""
        rule = ServiceMetadataPreflightRule()
        ctx = _make_ctx("utils.py", tmp_path)
        assert rule.evaluate(ctx) is None

    def test_dockerfile_warns_when_no_metadata(self, tmp_path: Path):
        """Dockerfile with no onboarding-metadata.json → WARN."""
        rule = ServiceMetadataPreflightRule()
        ctx = _make_ctx("Dockerfile", tmp_path)
        result = rule.evaluate(ctx)
        assert result is not None
        assert len(result.checks) == 1
        assert result.checks[0].status == CheckStatus.WARN

    def test_dockerfile_no_warn_when_metadata_present(self, tmp_path: Path):
        """Dockerfile with service_metadata in onboarding-metadata.json → None."""
        metadata = {"service_metadata": {"transport_protocol": "grpc"}}
        (tmp_path / "onboarding-metadata.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )
        rule = ServiceMetadataPreflightRule()
        ctx = _make_ctx("Dockerfile", tmp_path)
        assert rule.evaluate(ctx) is None

    def test_server_file_warns(self, tmp_path: Path):
        """Files with _server in name trigger check."""
        rule = ServiceMetadataPreflightRule()
        ctx = _make_ctx("product_server.py", tmp_path)
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.checks[0].status == CheckStatus.WARN

    def test_pb2_file_warns(self, tmp_path: Path):
        """Files with _pb2 in name trigger check."""
        rule = ServiceMetadataPreflightRule()
        ctx = _make_ctx("service_pb2.py", tmp_path)
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.checks[0].status == CheckStatus.WARN

    def test_grpc_file_warns(self, tmp_path: Path):
        """Files with grpc in name trigger check."""
        rule = ServiceMetadataPreflightRule()
        ctx = _make_ctx("grpc_client.py", tmp_path)
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.checks[0].status == CheckStatus.WARN
