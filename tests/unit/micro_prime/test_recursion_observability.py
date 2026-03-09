"""Tests for recursion observability (REQ-MP-914, REQ-MP-913, Phase 3).

Verifies OTel counter emission, bounded rejection reason labels,
depth cardinality capping, and postmortem metadata.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardManifest,
)
from startd8.micro_prime.decomposer import SubElement
from startd8.micro_prime.decomposition.core import (
    RECURSION_REJECTION_REASONS,
    DecompositionNode,
    DecompositionPlanGraph,
    RecursionPolicy,
    make_fingerprint,
)
from startd8.micro_prime.engine import (
    MicroPrimeEngine,
    _GraphExecutionResult,
    _RECURSION_DEPTH_LABEL_CAP,
    _cap_depth_label,
    _record_recursion_attempted,
    _record_recursion_rejected,
    _record_recursion_succeeded,
)
from startd8.micro_prime.models import (
    ElementResult,
    MicroPrimeConfig,
    TierClassification,
)
from startd8.utils.code_manifest import ElementKind, Param, Signature


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def config() -> MicroPrimeConfig:
    return MicroPrimeConfig(
        repair_enabled=False,
        escalation_enabled=False,
        few_shot_enabled=False,
        semantic_verification_enabled=False,
    )


@pytest.fixture
def config_recursive() -> MicroPrimeConfig:
    return MicroPrimeConfig(
        recursion_enabled=True,
        recursion_max_depth=2,
        repair_enabled=False,
        escalation_enabled=False,
        few_shot_enabled=False,
        semantic_verification_enabled=False,
    )


@pytest.fixture
def engine(config) -> MicroPrimeEngine:
    return MicroPrimeEngine(config=config)


@pytest.fixture
def engine_recursive(config_recursive) -> MicroPrimeEngine:
    return MicroPrimeEngine(config=config_recursive)


@pytest.fixture
def file_spec() -> ForwardFileSpec:
    return ForwardFileSpec(
        file="src/test.py",
        imports=[],
        elements=[
            ForwardElementSpec(
                kind=ElementKind.CLASS,
                name="MyClass",
                bases=["Base"],
            ),
        ],
    )


@pytest.fixture
def manifest(file_spec) -> ForwardManifest:
    return ForwardManifest(
        schema_version="1.0.0",
        file_specs={"src/test.py": file_spec},
        contracts=[],
    )


@pytest.fixture
def class_element() -> ForwardElementSpec:
    return ForwardElementSpec(
        kind=ElementKind.CLASS,
        name="MyClass",
        bases=["Base"],
    )


@pytest.fixture
def simple_element() -> ForwardElementSpec:
    return ForwardElementSpec(
        kind=ElementKind.FUNCTION,
        name="helper",
        signature=Signature(
            params=[Param(name="x", annotation="int")],
            return_annotation="int",
        ),
        docstring_hint="Return x + 1.",
    )


SKELETON = '''class MyClass(Base):
    """A test class."""
    raise NotImplementedError
'''


def _make_graph(
    element: ForwardElementSpec,
    nodes: list[DecompositionNode],
    strategy: str = "test",
) -> DecompositionPlanGraph:
    return DecompositionPlanGraph(
        original_element=element,
        root_nodes=nodes,
        strategy=strategy,
        assembly_kind="class_compose",
        confidence=0.9,
    )


# ── Depth label capping tests ────────────────────────────────────────


class TestDepthLabelCapping:
    """REQ-MP-914, R2-F3: depth labels capped to avoid cardinality explosion."""

    def test_depth_within_cap(self):
        assert _cap_depth_label(0) == "0"
        assert _cap_depth_label(1) == "1"
        assert _cap_depth_label(_RECURSION_DEPTH_LABEL_CAP) == str(_RECURSION_DEPTH_LABEL_CAP)

    def test_depth_beyond_cap_bucketed(self):
        assert _cap_depth_label(_RECURSION_DEPTH_LABEL_CAP + 1) == f"{_RECURSION_DEPTH_LABEL_CAP}+"
        assert _cap_depth_label(100) == f"{_RECURSION_DEPTH_LABEL_CAP}+"

    def test_cap_value_is_three(self):
        """Default cap is 3 per REQ-MP-914 acceptance criteria."""
        assert _RECURSION_DEPTH_LABEL_CAP == 3


# ── Metrics emission tests ───────────────────────────────────────────


class TestRecursionMetricsEmittedWhenEnabled:
    """REQ-MP-914: counters fire only when recursion is enabled."""

    def test_recursion_attempted_emitted_at_depth_gt_zero(
        self, engine_recursive, class_element, file_spec, manifest,
    ):
        """recursion_attempted fires when enabled and depth > 0."""
        node = DecompositionNode(
            sub_element=SubElement(
                name="shell",
                kind="class_shell",
                prompt_context="",
                depends_on=[],
                assembly_order=0,
                element_spec=None,
                deterministic=True,
            ),
        )
        graph = _make_graph(class_element, [node], strategy="class_decompose")

        with patch("startd8.micro_prime.engine._recursion_attempted") as mock_counter:
            mock_counter.add = MagicMock()
            engine_recursive._execute_plan_graph(
                graph=graph,
                file_spec=file_spec,
                manifest=manifest,
                skeleton=SKELETON,
                contracts=[],
                file_path="src/test.py",
                policy=RecursionPolicy(enabled=True),
                depth=1,  # Recursive call
            )
            mock_counter.add.assert_called_once_with(1, {
                "strategy": "class_decompose",
                "depth": "1",
            })

    def test_recursion_succeeded_emitted_on_success(
        self, engine_recursive, class_element, file_spec, manifest,
    ):
        """recursion_succeeded fires when all nodes succeed at depth > 0."""
        node = DecompositionNode(
            sub_element=SubElement(
                name="shell",
                kind="class_shell",
                prompt_context="",
                depends_on=[],
                assembly_order=0,
                element_spec=None,
                deterministic=True,
            ),
        )
        graph = _make_graph(class_element, [node], strategy="class_decompose")

        with patch("startd8.micro_prime.engine._recursion_succeeded") as mock_counter:
            mock_counter.add = MagicMock()
            result = engine_recursive._execute_plan_graph(
                graph=graph,
                file_spec=file_spec,
                manifest=manifest,
                skeleton=SKELETON,
                contracts=[],
                file_path="src/test.py",
                policy=RecursionPolicy(enabled=True),
                depth=1,
            )
            assert result.success is True
            mock_counter.add.assert_called_once_with(1, {
                "strategy": "class_decompose",
                "depth": "1",
            })

    def test_recursion_rejected_emitted_on_failure(
        self, engine_recursive, class_element, file_spec, manifest, simple_element,
    ):
        """recursion_rejected fires with rejection_reason on failure at depth > 0."""
        node = DecompositionNode(
            sub_element=SubElement(
                name="helper",
                kind="helper",
                prompt_context="impl",
                depends_on=[],
                assembly_order=0,
                element_spec=simple_element,
            ),
        )
        graph = _make_graph(class_element, [node], strategy="class_decompose")

        with patch.object(engine_recursive, "_handle_simple") as mock_simple, \
             patch("startd8.micro_prime.engine._recursion_rejected") as mock_counter:
            mock_simple.return_value = ElementResult(
                element_name="helper",
                file_path="src/test.py",
                tier=TierClassification.SIMPLE,
                success=False,
                code=None,
            )
            mock_counter.add = MagicMock()

            result = engine_recursive._execute_plan_graph(
                graph=graph,
                file_spec=file_spec,
                manifest=manifest,
                skeleton=SKELETON,
                contracts=[],
                file_path="src/test.py",
                policy=RecursionPolicy(enabled=True),
                depth=1,
            )
            assert result.success is False
            mock_counter.add.assert_called_once_with(1, {
                "strategy": "class_decompose",
                "depth": "1",
                "rejection_reason": "sub_element_failed",
            })


class TestRecursionMetricsNotEmittedWhenDisabled:
    """R2-S7: zero metric emissions when recursion_enabled=False."""

    def test_no_metrics_when_disabled(
        self, engine, class_element, file_spec, manifest,
    ):
        """No recursion counters fire when policy is disabled."""
        node = DecompositionNode(
            sub_element=SubElement(
                name="shell",
                kind="class_shell",
                prompt_context="",
                depends_on=[],
                assembly_order=0,
                element_spec=None,
                deterministic=True,
            ),
        )
        graph = _make_graph(class_element, [node])

        with patch("startd8.micro_prime.engine._recursion_attempted") as mock_attempted, \
             patch("startd8.micro_prime.engine._recursion_succeeded") as mock_succeeded, \
             patch("startd8.micro_prime.engine._recursion_rejected") as mock_rejected:
            mock_attempted.add = MagicMock()
            mock_succeeded.add = MagicMock()
            mock_rejected.add = MagicMock()

            engine._execute_plan_graph(
                graph=graph,
                file_spec=file_spec,
                manifest=manifest,
                skeleton=SKELETON,
                contracts=[],
                file_path="src/test.py",
                policy=RecursionPolicy(enabled=False),
            )

            mock_attempted.add.assert_not_called()
            mock_succeeded.add.assert_not_called()
            mock_rejected.add.assert_not_called()

    def test_no_metrics_at_depth_zero(
        self, engine_recursive, class_element, file_spec, manifest,
    ):
        """No recursion counters at depth=0 (top-level, not a recursive call)."""
        node = DecompositionNode(
            sub_element=SubElement(
                name="shell",
                kind="class_shell",
                prompt_context="",
                depends_on=[],
                assembly_order=0,
                element_spec=None,
                deterministic=True,
            ),
        )
        graph = _make_graph(class_element, [node])

        with patch("startd8.micro_prime.engine._recursion_attempted") as mock_attempted, \
             patch("startd8.micro_prime.engine._recursion_succeeded") as mock_succeeded:
            mock_attempted.add = MagicMock()
            mock_succeeded.add = MagicMock()

            engine_recursive._execute_plan_graph(
                graph=graph,
                file_spec=file_spec,
                manifest=manifest,
                skeleton=SKELETON,
                contracts=[],
                file_path="src/test.py",
                policy=RecursionPolicy(enabled=True),
                depth=0,  # Top-level
            )

            mock_attempted.add.assert_not_called()
            mock_succeeded.add.assert_not_called()


# ── Rejection reason bounded set tests ───────────────────────────────


class TestRecursionRejectionReasonBounded:
    """REQ-MP-913: metric labels use only bounded rejection reasons."""

    def test_rejection_reasons_are_bounded_set(self):
        """All recursion-specific reasons are in RECURSION_REJECTION_REASONS."""
        assert "recursion_blocked" in RECURSION_REJECTION_REASONS
        assert "depth_exceeded" in RECURSION_REJECTION_REASONS
        assert "budget_exceeded" in RECURSION_REJECTION_REASONS
        assert "monotonicity_violation" in RECURSION_REJECTION_REASONS
        assert "cycle_detected" in RECURSION_REJECTION_REASONS
        assert len(RECURSION_REJECTION_REASONS) == 5

    def test_depth_cap_label_format(self):
        """Bucketed labels match expected format."""
        assert _cap_depth_label(5) == f"{_RECURSION_DEPTH_LABEL_CAP}+"
        assert "+" in _cap_depth_label(999)


# ── Postmortem metadata tests ────────────────────────────────────────


class TestPostmortemIncludesRecursionMetadata:
    """REQ-MP-913, R1-S3: recursion_depth and decomposition_path in results."""

    def test_success_result_includes_metadata(
        self, engine_recursive, class_element, file_spec, manifest,
    ):
        """Successful graph execution includes depth and path."""
        node = DecompositionNode(
            sub_element=SubElement(
                name="shell",
                kind="class_shell",
                prompt_context="",
                depends_on=[],
                assembly_order=0,
                element_spec=None,
                deterministic=True,
            ),
        )
        graph = _make_graph(class_element, [node])
        fp = make_fingerprint(None, "MyClass", "src/test.py", TierClassification.MODERATE)

        result = engine_recursive._execute_plan_graph(
            graph=graph,
            file_spec=file_spec,
            manifest=manifest,
            skeleton=SKELETON,
            contracts=[],
            file_path="src/test.py",
            policy=RecursionPolicy(enabled=True),
            depth=1,
            decomposition_path=[fp],
        )
        assert result.success is True
        assert result.recursion_depth == 1
        assert result.decomposition_path == [fp]

    def test_failure_result_includes_metadata(
        self, engine_recursive, class_element, file_spec, manifest, simple_element,
    ):
        """Failed graph execution includes depth and path for diagnostics."""
        node = DecompositionNode(
            sub_element=SubElement(
                name="helper",
                kind="helper",
                prompt_context="impl",
                depends_on=[],
                assembly_order=0,
                element_spec=simple_element,
            ),
        )
        graph = _make_graph(class_element, [node])
        fp = make_fingerprint(None, "root", "src/test.py", TierClassification.MODERATE)

        with patch.object(engine_recursive, "_handle_simple") as mock_simple:
            mock_simple.return_value = ElementResult(
                element_name="helper",
                file_path="src/test.py",
                tier=TierClassification.SIMPLE,
                success=False,
                code=None,
            )
            result = engine_recursive._execute_plan_graph(
                graph=graph,
                file_spec=file_spec,
                manifest=manifest,
                skeleton=SKELETON,
                contracts=[],
                file_path="src/test.py",
                policy=RecursionPolicy(enabled=True),
                depth=2,
                decomposition_path=[fp],
            )

        assert result.success is False
        assert result.recursion_depth == 2
        assert result.decomposition_path == [fp]

    def test_metadata_defaults_at_depth_zero(
        self, engine, class_element, file_spec, manifest,
    ):
        """At depth 0, metadata shows depth=0 and empty path."""
        node = DecompositionNode(
            sub_element=SubElement(
                name="shell",
                kind="class_shell",
                prompt_context="",
                depends_on=[],
                assembly_order=0,
                element_spec=None,
                deterministic=True,
            ),
        )
        graph = _make_graph(class_element, [node])

        result = engine._execute_plan_graph(
            graph=graph,
            file_spec=file_spec,
            manifest=manifest,
            skeleton=SKELETON,
            contracts=[],
            file_path="src/test.py",
            policy=RecursionPolicy(enabled=False),
        )
        assert result.recursion_depth == 0
        assert result.decomposition_path == []


# ── Fingerprint log level tests ──────────────────────────────────────


class TestFingerprintLogLevel:
    """REQ-MP-913, R2-F7: fingerprints logged at DEBUG only."""

    def test_cycle_detection_logs_at_debug(
        self, engine_recursive, class_element, file_spec, manifest, simple_element,
    ):
        """Cycle detection message uses logger.debug, not INFO+."""
        fp = make_fingerprint(None, "helper", "src/test.py", TierClassification.SIMPLE)

        child = DecompositionNode(
            sub_element=SubElement(
                name="inner", kind="helper", prompt_context="x",
                depends_on=[], assembly_order=0, element_spec=simple_element,
            ),
        )
        parent = DecompositionNode(
            sub_element=SubElement(
                name="helper", kind="helper", prompt_context="x",
                depends_on=[], assembly_order=0, element_spec=simple_element,
            ),
            children=[child],
        )
        graph = _make_graph(class_element, [parent])

        with patch("startd8.micro_prime.engine.logger") as mock_logger:
            engine_recursive._execute_plan_graph(
                graph=graph,
                file_spec=file_spec,
                manifest=manifest,
                skeleton=SKELETON,
                contracts=[],
                file_path="src/test.py",
                policy=RecursionPolicy(enabled=True, max_depth=3),
                decomposition_path=[fp],
            )
            # Verify cycle message went to debug, not info/warning
            debug_messages = [
                str(call) for call in mock_logger.debug.call_args_list
            ]
            assert any("cycle" in msg.lower() for msg in debug_messages)
            info_messages = [
                str(call) for call in mock_logger.info.call_args_list
            ]
            assert not any("cycle" in msg.lower() for msg in info_messages)
