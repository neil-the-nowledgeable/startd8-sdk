"""Tests for plan graph executor (REQ-MP-912, Phase 2).

Tests staging safety, cycle detection, disabled-recursion blocking,
and budget accounting for the recursive execution path.
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
    _NodeExecutionResult,
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
def config_recursion_enabled() -> MicroPrimeConfig:
    return MicroPrimeConfig(
        recursion_enabled=True,
        recursion_max_depth=2,
        recursion_max_sub_elements_total=8,
        recursion_max_llm_calls=3,
        repair_enabled=False,
        escalation_enabled=False,
        few_shot_enabled=False,
        semantic_verification_enabled=False,
    )


@pytest.fixture
def engine(config) -> MicroPrimeEngine:
    return MicroPrimeEngine(config=config)


@pytest.fixture
def engine_recursive(config_recursion_enabled) -> MicroPrimeEngine:
    return MicroPrimeEngine(config=config_recursion_enabled)


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
            ForwardElementSpec(
                kind=ElementKind.METHOD,
                name="do_thing",
                signature=Signature(
                    params=[Param(name="self")],
                    return_annotation="None",
                ),
                parent_class="MyClass",
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
        docstring_hint="A test class.",
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


def _make_leaf_node(
    name: str,
    order: int,
    deterministic: bool = False,
    element_spec: ForwardElementSpec | None = None,
) -> DecompositionNode:
    return DecompositionNode(
        sub_element=SubElement(
            name=name,
            kind="class_shell" if deterministic else "helper",
            prompt_context="" if deterministic else f"implement {name}",
            depends_on=[],
            assembly_order=order,
            element_spec=element_spec,
            deterministic=deterministic,
        ),
    )


def _make_graph(
    element: ForwardElementSpec,
    nodes: list[DecompositionNode],
    strategy: str = "test",
    assembly_kind: str = "class_compose",
) -> DecompositionPlanGraph:
    return DecompositionPlanGraph(
        original_element=element,
        root_nodes=nodes,
        strategy=strategy,
        assembly_kind=assembly_kind,
        confidence=0.9,
    )


SKELETON = '''class MyClass(Base):
    """A test class."""
    raise NotImplementedError

    def do_thing(self) -> None:
        raise NotImplementedError
'''


# ── Staging tests ────────────────────────────────────────────────────


class TestRecursiveDecompositionStaging:
    """REQ-MP-912: skeleton and caches unchanged on failure."""

    def test_successful_graph_returns_all_results(
        self, engine, class_element, file_spec, manifest,
    ):
        """All deterministic nodes succeed → staged results returned."""
        nodes = [
            _make_leaf_node("class_shell", 0, deterministic=True),
        ]
        graph = _make_graph(class_element, nodes)

        result = engine._execute_plan_graph(
            graph=graph,
            file_spec=file_spec,
            manifest=manifest,
            skeleton=SKELETON,
            contracts=[],
            file_path="src/test.py",
            policy=RecursionPolicy(enabled=False),
        )
        assert result.success is True
        assert "class_shell" in result.sub_results
        assert result.llm_calls == 0

    def test_failed_node_discards_all_staged_results(
        self, engine, class_element, file_spec, manifest, simple_element,
    ):
        """One node fails → all previously staged results discarded."""
        nodes = [
            _make_leaf_node("class_shell", 0, deterministic=True),
            # This node has element_spec but _handle_simple will fail (no Ollama)
            _make_leaf_node("helper", 1, element_spec=simple_element),
        ]
        graph = _make_graph(class_element, nodes)

        # Mock _handle_simple to fail
        with patch.object(engine, "_handle_simple") as mock_simple:
            mock_simple.return_value = ElementResult(
                element_name="helper",
                file_path="src/test.py",
                tier=TierClassification.SIMPLE,
                success=False,
                code=None,
            )
            result = engine._execute_plan_graph(
                graph=graph,
                file_spec=file_spec,
                manifest=manifest,
                skeleton=SKELETON,
                contracts=[],
                file_path="src/test.py",
                policy=RecursionPolicy(enabled=False),
            )

        assert result.success is False
        # Staged results from successful class_shell are discarded
        assert result.sub_results == {}

    def test_partial_plan_failure_rolls_back_all_staged_caches(
        self, engine, class_element, file_spec, manifest, simple_element,
    ):
        """R2-S3: fail one sub-element mid-plan, assert no cache entries written."""
        # Record initial cache state
        initial_cache = dict(engine._success_cache)
        initial_completed = list(engine._completed)

        nodes = [
            _make_leaf_node("class_shell", 0, deterministic=True),
            _make_leaf_node("good_helper", 1, element_spec=simple_element),
            _make_leaf_node("bad_helper", 2, element_spec=simple_element),
        ]
        graph = _make_graph(class_element, nodes)

        call_count = 0

        def mock_handle_simple(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ElementResult(
                    element_name="good_helper",
                    file_path="src/test.py",
                    tier=TierClassification.SIMPLE,
                    success=True,
                    code="return 42",
                )
            return ElementResult(
                element_name="bad_helper",
                file_path="src/test.py",
                tier=TierClassification.SIMPLE,
                success=False,
                code=None,
            )

        with patch.object(engine, "_handle_simple", side_effect=mock_handle_simple):
            result = engine._execute_plan_graph(
                graph=graph,
                file_spec=file_spec,
                manifest=manifest,
                skeleton=SKELETON,
                contracts=[],
                file_path="src/test.py",
                policy=RecursionPolicy(enabled=False),
            )

        assert result.success is False
        assert result.sub_results == {}
        # Engine state unchanged
        assert engine._success_cache == initial_cache
        assert engine._completed == initial_completed


# ── Cycle detection tests ────────────────────────────────────────────


class TestCycleDetectionRejects:
    """REQ-MP-911: repeated fingerprints blocked."""

    def test_cycle_in_decomposition_path_rejects(
        self, engine_recursive, class_element, file_spec, manifest, simple_element,
    ):
        """A fingerprint already in the path causes rejection."""
        # Fingerprint must match what the executor computes from simple_element:
        # parent_class=None → "", name="helper", file_path, tier=SIMPLE
        fp = make_fingerprint(None, "helper", "src/test.py", TierClassification.SIMPLE)

        child = _make_leaf_node("inner", 0, element_spec=simple_element)
        parent_node = DecompositionNode(
            sub_element=SubElement(
                name="helper",
                kind="helper",
                prompt_context="implement helper",
                depends_on=[],
                assembly_order=0,
                element_spec=simple_element,
            ),
            children=[child],
        )
        graph = _make_graph(class_element, [parent_node])

        result = engine_recursive._execute_plan_graph(
            graph=graph,
            file_spec=file_spec,
            manifest=manifest,
            skeleton=SKELETON,
            contracts=[],
            file_path="src/test.py",
            policy=RecursionPolicy(enabled=True, max_depth=3),
            decomposition_path=[fp],  # Already visited
        )
        assert result.success is False
        assert result.rejection_reason == "cycle_detected"


# ── Recursion disabled tests ─────────────────────────────────────────


class TestRecursionDisabledBlocks:
    """REQ-MP-912: recursion not attempted when disabled."""

    def test_leaf_nodes_still_execute_when_disabled(
        self, engine, class_element, file_spec, manifest, simple_element,
    ):
        """Leaf nodes use _handle_simple even when recursion is disabled."""
        nodes = [_make_leaf_node("helper", 0, element_spec=simple_element)]
        graph = _make_graph(class_element, nodes)

        with patch.object(engine, "_handle_simple") as mock_simple:
            mock_simple.return_value = ElementResult(
                element_name="helper",
                file_path="src/test.py",
                tier=TierClassification.SIMPLE,
                success=True,
                code="return 1",
            )
            result = engine._execute_plan_graph(
                graph=graph,
                file_spec=file_spec,
                manifest=manifest,
                skeleton=SKELETON,
                contracts=[],
                file_path="src/test.py",
                policy=RecursionPolicy(enabled=False),
            )

        assert result.success is True
        assert result.sub_results["helper"] == "return 1"
        assert result.llm_calls == 1

    def test_children_not_recursed_when_disabled(
        self, engine, class_element, file_spec, manifest, simple_element,
    ):
        """Nodes with children fall back to _handle_simple when recursion disabled."""
        child = _make_leaf_node("inner", 0, element_spec=simple_element)
        parent_node = DecompositionNode(
            sub_element=SubElement(
                name="parent",
                kind="helper",
                prompt_context="implement",
                depends_on=[],
                assembly_order=0,
                element_spec=simple_element,
            ),
            children=[child],
        )
        graph = _make_graph(class_element, [parent_node])

        with patch.object(engine, "_handle_simple") as mock_simple:
            mock_simple.return_value = ElementResult(
                element_name="parent",
                file_path="src/test.py",
                tier=TierClassification.SIMPLE,
                success=True,
                code="return 1",
            )
            result = engine._execute_plan_graph(
                graph=graph,
                file_spec=file_spec,
                manifest=manifest,
                skeleton=SKELETON,
                contracts=[],
                file_path="src/test.py",
                policy=RecursionPolicy(enabled=False),
            )

        # Falls back to _handle_simple instead of recursing into children
        assert result.success is True
        mock_simple.assert_called_once()


# ── Budget accounting tests ──────────────────────────────────────────


class TestDeterministicSubElementsDoNotCountLlmBudget:
    """REQ-MP-912: deterministic sub-elements don't count toward LLM budgets."""

    def test_deterministic_nodes_zero_llm_calls(
        self, engine, class_element, file_spec, manifest,
    ):
        """Deterministic extraction contributes 0 LLM calls."""
        nodes = [
            _make_leaf_node("class_shell", 0, deterministic=True),
        ]
        graph = _make_graph(class_element, nodes)

        result = engine._execute_plan_graph(
            graph=graph,
            file_spec=file_spec,
            manifest=manifest,
            skeleton=SKELETON,
            contracts=[],
            file_path="src/test.py",
            policy=RecursionPolicy(enabled=False),
        )
        assert result.success is True
        assert result.llm_calls == 0

    def test_mixed_deterministic_and_llm_budget(
        self, engine, class_element, file_spec, manifest, simple_element,
    ):
        """Only non-deterministic nodes count toward LLM calls."""
        nodes = [
            _make_leaf_node("class_shell", 0, deterministic=True),
            _make_leaf_node("helper1", 1, element_spec=simple_element),
            _make_leaf_node("helper2", 2, element_spec=simple_element),
        ]
        graph = _make_graph(class_element, nodes)

        with patch.object(engine, "_handle_simple") as mock_simple:
            mock_simple.return_value = ElementResult(
                element_name="helper",
                file_path="src/test.py",
                tier=TierClassification.SIMPLE,
                success=True,
                code="return 1",
            )
            result = engine._execute_plan_graph(
                graph=graph,
                file_spec=file_spec,
                manifest=manifest,
                skeleton=SKELETON,
                contracts=[],
                file_path="src/test.py",
                policy=RecursionPolicy(enabled=False),
            )

        assert result.success is True
        # 2 LLM calls (helper1 + helper2), 0 for deterministic class_shell
        assert result.llm_calls == 2


class TestLlmBudgetCountsOnlyDecompositionCalls:
    """R2-S6: escalation/repair calls do NOT count toward decomposition budget."""

    def test_llm_calls_only_count_handle_simple(
        self, engine, class_element, file_spec, manifest, simple_element,
    ):
        """Each _handle_simple invocation counts as exactly 1 LLM call."""
        nodes = [
            _make_leaf_node("h1", 0, element_spec=simple_element),
        ]
        graph = _make_graph(class_element, nodes)

        with patch.object(engine, "_handle_simple") as mock_simple:
            # Even if _handle_simple internally does repair retries,
            # it counts as 1 decomposition LLM call
            mock_simple.return_value = ElementResult(
                element_name="h1",
                file_path="src/test.py",
                tier=TierClassification.SIMPLE,
                success=True,
                code="return 1",
                repair_steps_applied=["fence_strip", "ast_validate"],
            )
            result = engine._execute_plan_graph(
                graph=graph,
                file_spec=file_spec,
                manifest=manifest,
                skeleton=SKELETON,
                contracts=[],
                file_path="src/test.py",
                policy=RecursionPolicy(enabled=False),
            )

        assert result.llm_calls == 1  # Not 3 (1 + 2 repair steps)


# ── Depth enforcement in executor tests ──────────────────────────────


class TestDepthEnforcementInExecutor:
    """REQ-MP-911: depth limits enforced during graph execution."""

    def test_depth_exceeded_rejects_recursive_node(
        self, engine_recursive, class_element, file_spec, manifest, simple_element,
    ):
        """Node with children at depth >= max_depth is rejected."""
        child = _make_leaf_node("inner", 0, element_spec=simple_element)
        parent = DecompositionNode(
            sub_element=SubElement(
                name="parent",
                kind="helper",
                prompt_context="implement",
                depends_on=[],
                assembly_order=0,
                element_spec=simple_element,
            ),
            children=[child],
        )
        graph = _make_graph(class_element, [parent])

        result = engine_recursive._execute_plan_graph(
            graph=graph,
            file_spec=file_spec,
            manifest=manifest,
            skeleton=SKELETON,
            contracts=[],
            file_path="src/test.py",
            policy=RecursionPolicy(enabled=True, max_depth=1),
            depth=1,  # Already at max depth
        )
        assert result.success is False
        assert result.rejection_reason == "depth_exceeded"


# ── Result type tests ────────────────────────────────────────────────


class TestResultTypes:
    """Verify _GraphExecutionResult and _NodeExecutionResult structures."""

    def test_graph_result_defaults(self):
        r = _GraphExecutionResult(success=True)
        assert r.sub_results == {}
        assert r.llm_calls == 0
        assert r.rejection_reason is None

    def test_node_result_defaults(self):
        r = _NodeExecutionResult(success=False, code="", rejection_reason="test")
        assert r.llm_calls == 0
        assert r.rejection_reason == "test"

    def test_missing_element_spec_rejects(
        self, engine, class_element, file_spec, manifest,
    ):
        """Leaf node without element_spec returns failure."""
        node = _make_leaf_node("orphan", 0, element_spec=None)
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
        assert result.success is False
        assert result.rejection_reason == "missing_element_spec"
