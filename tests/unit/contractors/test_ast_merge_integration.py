"""Integration test: ASTMergeStrategy through IntegrationEngine (INV-4 / PI-007).

Verifies that when a cloud-fallback-generated Python file (source) overlaps
with an existing target file, the AST merge auto-switches to replace mode
and produces clean output — no garbled merges, no duplicate __main__ guards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import pytest

from startd8.contractors.adapters.contextcore import ASTMergeStrategy
from startd8.contractors.integration_engine import IntegrationEngine


@dataclass
class _StubUnit:
    """Minimal IntegrationUnit for testing."""

    id: str = "PI-007"
    name: str = "test-unit"
    generated_files: List[str] = field(default_factory=list)
    target_files: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)


# Simulated existing file (target) — a partial gRPC client
_EXISTING_CLIENT = '''\
"""gRPC client for Recommendation Service."""

import grpc
import logging

logger = logging.getLogger(__name__)

RECOMMENDATION_SERVICE_ADDR = "localhost:8080"


def get_recommendations(product_ids):
    """Fetch recommendations excluding given product IDs."""
    channel = grpc.insecure_channel(RECOMMENDATION_SERVICE_ADDR)
    # TODO: implement
    return []


if __name__ == "__main__":
    recs = get_recommendations(["ABC"])
    print(recs)
'''

# Simulated cloud-fallback draft (source) — a complete replacement
_CLOUD_DRAFT = '''\
"""gRPC client for Recommendation Service."""

import grpc
import logging
import demo_pb2
import demo_pb2_grpc

logger = logging.getLogger(__name__)

RECOMMENDATION_SERVICE_ADDR = "localhost:8080"


def get_recommendations(product_ids):
    """Fetch recommendations excluding given product IDs."""
    channel = grpc.insecure_channel(RECOMMENDATION_SERVICE_ADDR)
    stub = demo_pb2_grpc.RecommendationServiceStub(channel)
    request = demo_pb2.ListRecommendationsRequest(
        product_ids=product_ids,
    )
    response = stub.ListRecommendations(request)
    return list(response.product_ids)


if __name__ == "__main__":
    recs = get_recommendations(["OLJCESPC7Z"])
    for rec in recs:
        print(f"Recommendation: {rec}")
'''


class TestASTMergeIntegration:
    """End-to-end: cloud draft merges with existing Python via IntegrationEngine."""

    def _setup_engine(self, tmp_path: Path) -> IntegrationEngine:
        project_root = tmp_path / "project"
        project_root.mkdir()
        strategy = ASTMergeStrategy(merge_mode="additive")
        return IntegrationEngine(
            project_root=project_root,
            merge_strategy=strategy,
            dry_run=False,
        )

    def test_overlapping_python_uses_replace_not_additive(
        self, tmp_path: Path,
    ) -> None:
        """PI-007 scenario: cloud draft + existing file → replace, not garbled merge."""
        engine = self._setup_engine(tmp_path)
        project_root = engine.project_root

        # Write existing file (target)
        target = project_root / "src" / "client.py"
        target.parent.mkdir(parents=True)
        target.write_text(_EXISTING_CLIENT, encoding="utf-8")

        # Write staging file (source = cloud draft)
        staging = tmp_path / "staging"
        source = staging / "src" / "client.py"
        source.parent.mkdir(parents=True)
        source.write_text(_CLOUD_DRAFT, encoding="utf-8")

        unit = _StubUnit(
            generated_files=[str(source)],
            target_files=["src/client.py"],
        )

        result = engine.integrate(unit)
        assert result.success, f"Integration failed: {result.errors}"

        # Read merged output
        merged = target.read_text(encoding="utf-8")

        # The cloud draft should have replaced the existing file
        # (>50% overlap in function/class names triggers auto-replace)
        assert "demo_pb2_grpc" in merged, "Cloud draft imports should be present"
        assert "stub.ListRecommendations" in merged, "Cloud draft implementation should be present"

        # No garbling: only one __main__ guard
        assert merged.count("__main__") == 1, (
            f"Expected 1 __main__ guard, found {merged.count('__main__')}"
        )

        # No garbling: only one logger instantiation
        assert merged.count("getLogger") == 1, (
            f"Expected 1 getLogger call, found {merged.count('getLogger')}"
        )

        # No garbling: only one RECOMMENDATION_SERVICE_ADDR
        assert merged.count("RECOMMENDATION_SERVICE_ADDR") <= 3, (
            "Constant should appear in definition + usage, not duplicated"
        )

    def test_no_overlap_html_copies_directly(self, tmp_path: Path) -> None:
        """Non-.py files bypass AST merge (can_merge returns False) → direct copy."""
        engine = self._setup_engine(tmp_path)
        project_root = engine.project_root

        target = project_root / "templates" / "page.html"
        target.parent.mkdir(parents=True)
        target.write_text("<html><body>old</body></html>", encoding="utf-8")

        staging = tmp_path / "staging"
        source = staging / "templates" / "page.html"
        source.parent.mkdir(parents=True)
        source.write_text("<html><body>new</body></html>", encoding="utf-8")

        unit = _StubUnit(
            generated_files=[str(source)],
            target_files=["templates/page.html"],
        )

        result = engine.integrate(unit)
        assert result.success

        merged = target.read_text(encoding="utf-8")
        # HTML bypasses AST merge → direct copy (source overwrites target)
        assert "new" in merged
        assert "old" not in merged

    def test_disjoint_python_stays_additive(self, tmp_path: Path) -> None:
        """Python files with no overlapping names stay in additive mode."""
        engine = self._setup_engine(tmp_path)
        project_root = engine.project_root

        target = project_root / "utils.py"
        target.write_text("def alpha():\n    return 1\n", encoding="utf-8")

        staging = tmp_path / "staging"
        source = staging / "utils.py"
        source.parent.mkdir(parents=True)
        source.write_text("def beta():\n    return 2\n", encoding="utf-8")

        unit = _StubUnit(
            generated_files=[str(source)],
            target_files=["utils.py"],
        )

        result = engine.integrate(unit)
        assert result.success

        merged = target.read_text(encoding="utf-8")
        # Additive: both functions present
        assert "alpha" in merged
        assert "beta" in merged
