"""Tests for decomposition core types and utilities (REQ-MP-910, Phase 0)."""

from __future__ import annotations

import pytest

from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardManifest,
)
from startd8.micro_prime.decomposer import (
    DecompositionPlan,
    ModerateDecomposer,
    SubElement,
)
from startd8.micro_prime.decomposition.core import (
    RECURSION_REJECTION_REASONS,
    DecompositionContext,
    DecompositionNode,
    DecompositionPlanGraph,
    RecursionPolicy,
    compute_graph_confidence,
    make_fingerprint,
    policy_from_config,
)
from startd8.micro_prime.models import MicroPrimeConfig, TierClassification
from startd8.utils.code_manifest import ElementKind, Param, Signature


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def config() -> MicroPrimeConfig:
    # AC-R4-R5: decomposition_enabled defaults to False; opt in for tests.
    return MicroPrimeConfig(decomposition_enabled=True)


@pytest.fixture
def manifest() -> ForwardManifest:
    return ForwardManifest(
        schema_version="1.0.0",
        file_specs={},
        contracts=[],
    )


@pytest.fixture
def file_spec() -> ForwardFileSpec:
    return ForwardFileSpec(
        file="src/mypackage/utils.py",
        imports=[],
        elements=[
            ForwardElementSpec(
                kind=ElementKind.FUNCTION,
                name="helper",
                signature=Signature(
                    params=[Param(name="x", annotation="int")],
                    return_annotation="int",
                ),
            ),
        ],
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
def function_element() -> ForwardElementSpec:
    return ForwardElementSpec(
        kind=ElementKind.FUNCTION,
        name="process_data",
        signature=Signature(
            params=[Param(name="data", annotation="dict")],
            return_annotation="dict",
        ),
        docstring_hint="Process data.",
    )


# ── DecompositionContext tests ───────────────────────────────────────


class TestDecompositionContext:
    """Verify DecompositionContext construction and field access."""

    def test_required_fields(self, config, manifest, file_spec):
        ctx = DecompositionContext(
            config=config,
            manifest=manifest,
            file_spec=file_spec,
            file_path="src/mypackage/utils.py",
            skeleton="# skeleton",
            recursion_policy=RecursionPolicy(),
        )
        assert ctx.config is config
        assert ctx.manifest is manifest
        assert ctx.file_spec is file_spec
        assert ctx.file_path == "src/mypackage/utils.py"
        assert ctx.skeleton == "# skeleton"
        assert ctx.recursion_policy.enabled is False

    def test_optional_fields_default_none(self, config, manifest, file_spec):
        ctx = DecompositionContext(
            config=config,
            manifest=manifest,
            file_spec=file_spec,
            file_path="src/mypackage/utils.py",
            skeleton="",
            recursion_policy=RecursionPolicy(),
        )
        assert ctx.template_registry is None
        assert ctx.classification_signals is None
        assert ctx.classification_reason == ""

    def test_classification_signals_set(self, config, manifest, file_spec):
        signals = {"external_api", "orchestrator"}
        ctx = DecompositionContext(
            config=config,
            manifest=manifest,
            file_spec=file_spec,
            file_path="src/a.py",
            skeleton="",
            recursion_policy=RecursionPolicy(),
            classification_signals=signals,
        )
        assert ctx.classification_signals == signals


class TestDecompositionContextPlumbing:
    """Verify strategies receive the same context fields as prior direct parameters."""

    def test_build_context_matches_direct_params(self, config, manifest, file_spec):
        """ModerateDecomposer.build_context() produces a context with all expected fields."""
        decomposer = ModerateDecomposer(config=config)
        ctx = decomposer.build_context(
            file_spec=file_spec,
            manifest=manifest,
            file_path="src/mypackage/utils.py",
            skeleton="# skel",
            classification_reason="test reason",
            classification_signals={"external_api"},
        )
        assert ctx.config is config
        assert ctx.manifest is manifest
        assert ctx.file_spec is file_spec
        assert ctx.file_path == "src/mypackage/utils.py"
        assert ctx.skeleton == "# skel"
        assert ctx.classification_reason == "test reason"
        assert ctx.classification_signals == {"external_api"}
        assert ctx.recursion_policy.enabled is False

    def test_build_context_custom_policy(self, config, manifest, file_spec):
        """build_context() accepts a custom RecursionPolicy."""
        decomposer = ModerateDecomposer(config=config)
        policy = RecursionPolicy(enabled=True, max_depth=3)
        ctx = decomposer.build_context(
            file_spec=file_spec,
            manifest=manifest,
            file_path="a.py",
            skeleton="",
            recursion_policy=policy,
        )
        assert ctx.recursion_policy.enabled is True
        assert ctx.recursion_policy.max_depth == 3


# ── DecompositionNode tests ──────────────────────────────────────────


class TestDecompositionNode:
    """Verify node structure and leaf detection."""

    def test_leaf_node(self):
        sub = SubElement(
            name="shell",
            kind="class_shell",
            prompt_context="",
            depends_on=[],
            assembly_order=0,
            element_spec=None,
            deterministic=True,
        )
        node = DecompositionNode(sub_element=sub)
        assert node.is_leaf is True
        assert node.children == []

    def test_parent_node(self):
        child_sub = SubElement(
            name="child",
            kind="helper",
            prompt_context="do thing",
            depends_on=[],
            assembly_order=1,
            element_spec=None,
        )
        child_node = DecompositionNode(sub_element=child_sub)

        parent_sub = SubElement(
            name="parent",
            kind="class_shell",
            prompt_context="",
            depends_on=[],
            assembly_order=0,
            element_spec=None,
        )
        parent_node = DecompositionNode(
            sub_element=parent_sub,
            children=[child_node],
        )
        assert parent_node.is_leaf is False
        assert len(parent_node.children) == 1


# ── DecompositionPlanGraph tests ─────────────────────────────────────


class TestDecompositionPlanGraph:
    """Validate graph structure, root node ordering, and child relationships."""

    def test_graph_structure(self, class_element):
        sub1 = SubElement(
            name="shell",
            kind="class_shell",
            prompt_context="",
            depends_on=[],
            assembly_order=0,
            element_spec=None,
            deterministic=True,
        )
        sub2 = SubElement(
            name="init",
            kind="init",
            prompt_context="init",
            depends_on=["shell"],
            assembly_order=1,
            element_spec=None,
        )
        node1 = DecompositionNode(sub_element=sub1)
        node2 = DecompositionNode(sub_element=sub2)

        graph = DecompositionPlanGraph(
            original_element=class_element,
            root_nodes=[node1, node2],
            strategy="class_decompose",
            assembly_kind="class_compose",
            confidence=0.9,
        )
        assert graph.strategy == "class_decompose"
        assert len(graph.root_nodes) == 2
        assert graph.root_nodes[0].sub_element.name == "shell"
        assert graph.root_nodes[1].sub_element.name == "init"

    def test_root_node_ordering_preserved(self, function_element):
        """Root nodes maintain insertion order."""
        nodes = []
        for i in range(4):
            sub = SubElement(
                name=f"step_{i}",
                kind="helper",
                prompt_context=f"step {i}",
                depends_on=[],
                assembly_order=i,
                element_spec=None,
            )
            nodes.append(DecompositionNode(sub_element=sub))

        graph = DecompositionPlanGraph(
            original_element=function_element,
            root_nodes=nodes,
            strategy="function_chain",
            assembly_kind="function_chain",
            confidence=0.8,
        )
        assert [n.sub_element.name for n in graph.root_nodes] == [
            "step_0", "step_1", "step_2", "step_3",
        ]

    def test_nested_children(self, class_element):
        """Graph supports nested children for recursive decomposition."""
        grandchild = DecompositionNode(
            sub_element=SubElement(
                name="gc",
                kind="helper",
                prompt_context="",
                depends_on=[],
                assembly_order=0,
                element_spec=None,
            ),
        )
        child = DecompositionNode(
            sub_element=SubElement(
                name="child",
                kind="helper",
                prompt_context="",
                depends_on=[],
                assembly_order=0,
                element_spec=None,
            ),
            children=[grandchild],
        )
        root = DecompositionNode(
            sub_element=SubElement(
                name="root",
                kind="class_shell",
                prompt_context="",
                depends_on=[],
                assembly_order=0,
                element_spec=None,
                deterministic=True,
            ),
            children=[child],
        )
        graph = DecompositionPlanGraph(
            original_element=class_element,
            root_nodes=[root],
            strategy="class_decompose",
            assembly_kind="class_compose",
            confidence=0.7,
        )
        assert not graph.root_nodes[0].is_leaf
        assert not graph.root_nodes[0].children[0].is_leaf
        assert graph.root_nodes[0].children[0].children[0].is_leaf


# ── Confidence aggregation tests ─────────────────────────────────────


class TestGraphConfidence:
    """Verify confidence aggregation: min across leaf nodes (R2-S8)."""

    def test_empty_graph(self, class_element):
        graph = DecompositionPlanGraph(
            original_element=class_element,
            root_nodes=[],
            strategy="test",
            assembly_kind="test",
            confidence=0.0,
        )
        assert compute_graph_confidence(graph) == 1.0

    def test_all_deterministic_leaves(self, class_element):
        """Deterministic sub-elements contribute 1.0."""
        nodes = [
            DecompositionNode(
                sub_element=SubElement(
                    name=f"d{i}",
                    kind="class_shell",
                    prompt_context="",
                    depends_on=[],
                    assembly_order=i,
                    element_spec=None,
                    deterministic=True,
                ),
            )
            for i in range(3)
        ]
        graph = DecompositionPlanGraph(
            original_element=class_element,
            root_nodes=nodes,
            strategy="test",
            assembly_kind="test",
            confidence=0.0,
        )
        assert compute_graph_confidence(graph) == 1.0

    def test_mixed_deterministic_and_non_deterministic(self, class_element):
        """Non-deterministic leaves contribute 1.0 at plan time (not yet executed)."""
        nodes = [
            DecompositionNode(
                sub_element=SubElement(
                    name="det",
                    kind="class_shell",
                    prompt_context="",
                    depends_on=[],
                    assembly_order=0,
                    element_spec=None,
                    deterministic=True,
                ),
            ),
            DecompositionNode(
                sub_element=SubElement(
                    name="nondet",
                    kind="init",
                    prompt_context="init",
                    depends_on=[],
                    assembly_order=1,
                    element_spec=None,
                    deterministic=False,
                ),
            ),
        ]
        graph = DecompositionPlanGraph(
            original_element=class_element,
            root_nodes=nodes,
            strategy="test",
            assembly_kind="test",
            confidence=0.0,
        )
        # At plan time, all leaves are 1.0
        assert compute_graph_confidence(graph) == 1.0


# ── Fingerprint tests ────────────────────────────────────────────────


class TestFingerprint:
    """Verify canonical fingerprint format matches engine caching."""

    def test_fingerprint_with_parent_class(self):
        fp = make_fingerprint("MyClass", "__init__", "src/a.py", TierClassification.SIMPLE)
        assert fp == "MyClass:__init__:src/a.py:simple"

    def test_fingerprint_without_parent_class(self):
        fp = make_fingerprint(None, "helper", "src/b.py", TierClassification.TRIVIAL)
        assert fp == ":helper:src/b.py:trivial"

    def test_fingerprint_empty_parent_class(self):
        fp = make_fingerprint("", "func", "src/c.py", TierClassification.MODERATE)
        assert fp == ":func:src/c.py:moderate"

    def test_fingerprint_format_is_canonical(self):
        """Fingerprint has exactly 4 colon-separated parts."""
        fp = make_fingerprint("Outer", "method", "src/d.py", TierClassification.COMPLEX)
        parts = fp.split(":")
        assert len(parts) == 4
        assert parts == ["Outer", "method", "src/d.py", "complex"]


# ── RecursionPolicy tests ────────────────────────────────────────────


class TestRecursionPolicy:
    """Verify policy defaults and validation."""

    def test_defaults_preserve_current_behavior(self):
        """Default policy has recursion disabled — no behavior change."""
        policy = RecursionPolicy()
        assert policy.enabled is False
        assert policy.max_depth == 2
        assert policy.max_sub_elements_total == 8
        assert policy.max_llm_calls == 3
        assert policy.monotonicity == "strict_tier_decrease"

    def test_disabled_policy_allows_zero_limits(self):
        """When disabled, zero limits are allowed (no validation needed)."""
        policy = RecursionPolicy(enabled=False, max_depth=0)
        assert policy.max_depth == 0

    def test_enabled_policy_rejects_zero_depth(self):
        """REQ-MP-915, R2-S9: zero max_depth raises ValueError."""
        with pytest.raises(ValueError, match="max_depth must be >= 1"):
            RecursionPolicy(enabled=True, max_depth=0)

    def test_enabled_policy_rejects_zero_sub_elements(self):
        with pytest.raises(ValueError, match="max_sub_elements_total must be >= 1"):
            RecursionPolicy(enabled=True, max_sub_elements_total=0)

    def test_enabled_policy_rejects_zero_llm_calls(self):
        with pytest.raises(ValueError, match="max_llm_calls must be >= 1"):
            RecursionPolicy(enabled=True, max_llm_calls=0)

    def test_enabled_policy_valid(self):
        policy = RecursionPolicy(enabled=True, max_depth=3, max_llm_calls=5)
        assert policy.enabled is True
        assert policy.max_depth == 3

    def test_monotonicity_options(self):
        p1 = RecursionPolicy(monotonicity="strict_tier_decrease")
        assert p1.monotonicity == "strict_tier_decrease"
        p2 = RecursionPolicy(monotonicity="allow_same_tier")
        assert p2.monotonicity == "allow_same_tier"


# ── Backward compatibility tests ─────────────────────────────────────


class TestBackwardCompatibility:
    """Verify existing DecompositionPlan and SubElement interfaces are unaffected."""

    def test_sub_element_unchanged(self):
        sub = SubElement(
            name="shell",
            kind="class_shell",
            prompt_context="test",
            depends_on=["a"],
            assembly_order=0,
            element_spec=None,
            deterministic=True,
        )
        assert sub.name == "shell"
        assert sub.deterministic is True

    def test_decomposition_plan_unchanged(self, class_element):
        plan = DecompositionPlan(
            original_element=class_element,
            sub_elements=[],
            strategy="class_decompose",
            assembly_kind="class_compose",
            confidence=0.85,
        )
        assert plan.confidence == 0.85
        assert plan.strategy == "class_decompose"

    def test_decompose_without_context(self, config):
        """Existing decompose() call signature still works without context param."""
        file_spec = ForwardFileSpec(
            file="src/test.py",
            imports=[],
            elements=[
                ForwardElementSpec(
                    kind=ElementKind.CLASS,
                    name="Foo",
                    bases=[],
                ),
                ForwardElementSpec(
                    kind=ElementKind.METHOD,
                    name="bar",
                    signature=Signature(
                        params=[Param(name="self")],
                        return_annotation="None",
                    ),
                    parent_class="Foo",
                ),
                # Pad to 5 elements to avoid small-file bias
                ForwardElementSpec(
                    kind=ElementKind.FUNCTION,
                    name="f1",
                    signature=Signature(params=[], return_annotation="None"),
                ),
                ForwardElementSpec(
                    kind=ElementKind.FUNCTION,
                    name="f2",
                    signature=Signature(params=[], return_annotation="None"),
                ),
                ForwardElementSpec(
                    kind=ElementKind.FUNCTION,
                    name="f3",
                    signature=Signature(params=[], return_annotation="None"),
                ),
            ],
        )
        manifest = ForwardManifest(
            schema_version="1.0.0",
            file_specs={"src/test.py": file_spec},
            contracts=[],
        )
        decomposer = ModerateDecomposer(config=config)
        # This should work without the context parameter
        result = decomposer.decompose(
            element=file_spec.elements[0],
            file_spec=file_spec,
            manifest=manifest,
            classification_reason="class with methods",
        )
        # Result may be None (class may not qualify) — we're testing the call doesn't crash
        assert result is None or isinstance(result, DecompositionPlan)


# ── Phase 1: Config wiring tests ─────────────────────────────────────


class TestRecursionConfigDefaults:
    """REQ-MP-915: config defaults preserve current behavior (no recursion)."""

    def test_decomposition_disabled_by_default(self):
        """AC-R4-R5: decomposition_enabled defaults to False."""
        config = MicroPrimeConfig()
        assert config.decomposition_enabled is False

    def test_recursion_config_defaults(self):
        config = MicroPrimeConfig()
        assert config.recursion_enabled is False
        assert config.recursion_max_depth == 2
        assert config.recursion_max_sub_elements_total == 8
        assert config.recursion_max_llm_calls == 3
        assert config.recursion_monotonicity == "strict_tier_decrease"

    def test_policy_from_config_defaults(self):
        config = MicroPrimeConfig()
        policy = policy_from_config(config)
        assert policy.enabled is False
        assert policy.max_depth == 2
        assert policy.max_sub_elements_total == 8
        assert policy.max_llm_calls == 3
        assert policy.monotonicity == "strict_tier_decrease"

    def test_policy_from_config_enabled(self):
        config = MicroPrimeConfig(
            recursion_enabled=True,
            recursion_max_depth=3,
            recursion_max_sub_elements_total=10,
            recursion_max_llm_calls=5,
            recursion_monotonicity="allow_same_tier",
        )
        policy = policy_from_config(config)
        assert policy.enabled is True
        assert policy.max_depth == 3
        assert policy.max_sub_elements_total == 10
        assert policy.max_llm_calls == 5
        assert policy.monotonicity == "allow_same_tier"

    def test_policy_from_config_invalid_raises(self):
        """R2-S10: zero limits with enabled=True raise at construction."""
        config = MicroPrimeConfig(recursion_enabled=True, recursion_max_depth=0)
        with pytest.raises(ValueError, match="max_depth must be >= 1"):
            policy_from_config(config)

    def test_build_context_uses_config_policy(self):
        """build_context() plumbs config into RecursionPolicy."""
        config = MicroPrimeConfig(recursion_enabled=False)
        decomposer = ModerateDecomposer(config=config)
        ctx = decomposer.build_context(
            file_spec=ForwardFileSpec(file="a.py", imports=[], elements=[]),
            manifest=ForwardManifest(
                schema_version="1.0.0", file_specs={}, contracts=[],
            ),
            file_path="a.py",
            skeleton="",
        )
        assert ctx.recursion_policy.enabled is False


# ── Phase 1: Policy depth limit tests ────────────────────────────────


class TestRecursionPolicyDepthLimit:
    """REQ-MP-911: depth enforcement."""

    def test_depth_within_limit(self):
        policy = RecursionPolicy(enabled=True, max_depth=2)
        assert policy.check_depth(0) is None
        assert policy.check_depth(1) is None

    def test_depth_at_limit_rejects(self):
        policy = RecursionPolicy(enabled=True, max_depth=2)
        assert policy.check_depth(2) == "depth_exceeded"

    def test_depth_beyond_limit_rejects(self):
        policy = RecursionPolicy(enabled=True, max_depth=1)
        assert policy.check_depth(5) == "depth_exceeded"

    def test_depth_check_disabled_blocks(self):
        policy = RecursionPolicy(enabled=False)
        assert policy.check_depth(0) == "recursion_blocked"


# ── Phase 1: Policy budget limit tests ───────────────────────────────


class TestRecursionPolicyBudgetLimit:
    """REQ-MP-911: sub-element and LLM call budget enforcement."""

    def test_budget_within_limits(self):
        policy = RecursionPolicy(
            enabled=True, max_sub_elements_total=8, max_llm_calls=3,
        )
        assert policy.check_budget(sub_element_count=5, llm_call_count=2) is None

    def test_sub_element_budget_exceeded(self):
        policy = RecursionPolicy(
            enabled=True, max_sub_elements_total=4, max_llm_calls=10,
        )
        assert policy.check_budget(sub_element_count=5, llm_call_count=0) == "budget_exceeded"

    def test_llm_call_budget_exceeded(self):
        policy = RecursionPolicy(
            enabled=True, max_sub_elements_total=100, max_llm_calls=2,
        )
        assert policy.check_budget(sub_element_count=1, llm_call_count=3) == "budget_exceeded"

    def test_both_at_exact_limit(self):
        """At exactly the limit — still OK (> not >=)."""
        policy = RecursionPolicy(
            enabled=True, max_sub_elements_total=5, max_llm_calls=3,
        )
        assert policy.check_budget(sub_element_count=5, llm_call_count=3) is None

    def test_budget_check_disabled_blocks(self):
        policy = RecursionPolicy(enabled=False)
        assert policy.check_budget(0, 0) == "recursion_blocked"


# ── Phase 1: Monotonicity tests ──────────────────────────────────────


class TestRecursionMonotonicityStrict:
    """REQ-MP-911: strict_tier_decrease monotonicity."""

    def test_strict_decrease_allowed(self):
        policy = RecursionPolicy(
            enabled=True, monotonicity="strict_tier_decrease",
        )
        assert policy.check_monotonicity(
            TierClassification.MODERATE, TierClassification.SIMPLE,
        ) is None

    def test_strict_same_tier_rejected(self):
        policy = RecursionPolicy(
            enabled=True, monotonicity="strict_tier_decrease",
        )
        assert policy.check_monotonicity(
            TierClassification.SIMPLE, TierClassification.SIMPLE,
        ) == "monotonicity_violation"

    def test_strict_increase_rejected(self):
        policy = RecursionPolicy(
            enabled=True, monotonicity="strict_tier_decrease",
        )
        assert policy.check_monotonicity(
            TierClassification.SIMPLE, TierClassification.MODERATE,
        ) == "monotonicity_violation"

    def test_strict_same_tier_rejected_even_with_strategy_flag(self):
        """strict_tier_decrease ignores strategy safe_for_same_tier flag."""
        policy = RecursionPolicy(
            enabled=True, monotonicity="strict_tier_decrease",
        )
        assert policy.check_monotonicity(
            TierClassification.MODERATE,
            TierClassification.MODERATE,
            strategy_safe_for_same_tier=True,
        ) == "monotonicity_violation"


class TestRecursionMonotonicityAllowSameTier:
    """REQ-MP-911, R2-F4: allow_same_tier requires dual-guard."""

    def test_same_tier_with_strategy_flag_allowed(self):
        policy = RecursionPolicy(
            enabled=True, monotonicity="allow_same_tier",
        )
        assert policy.check_monotonicity(
            TierClassification.SIMPLE,
            TierClassification.SIMPLE,
            strategy_safe_for_same_tier=True,
        ) is None

    def test_same_tier_without_strategy_flag_rejected(self):
        """R2-F4: policy allows but strategy didn't opt in → reject."""
        policy = RecursionPolicy(
            enabled=True, monotonicity="allow_same_tier",
        )
        assert policy.check_monotonicity(
            TierClassification.SIMPLE,
            TierClassification.SIMPLE,
            strategy_safe_for_same_tier=False,
        ) == "monotonicity_violation"

    def test_decrease_always_allowed(self):
        policy = RecursionPolicy(
            enabled=True, monotonicity="allow_same_tier",
        )
        assert policy.check_monotonicity(
            TierClassification.COMPLEX, TierClassification.TRIVIAL,
        ) is None

    def test_increase_always_rejected(self):
        policy = RecursionPolicy(
            enabled=True, monotonicity="allow_same_tier",
        )
        assert policy.check_monotonicity(
            TierClassification.TRIVIAL, TierClassification.MODERATE,
        ) == "monotonicity_violation"

    def test_monotonicity_disabled_blocks(self):
        policy = RecursionPolicy(enabled=False)
        assert policy.check_monotonicity(
            TierClassification.MODERATE, TierClassification.SIMPLE,
        ) == "recursion_blocked"


# ── Phase 1: Cycle detection tests ───────────────────────────────────


class TestCycleDetection:
    """REQ-MP-911: fingerprint-based cycle detection."""

    def test_no_cycle(self):
        policy = RecursionPolicy(enabled=True)
        fp = make_fingerprint("A", "init", "a.py", TierClassification.SIMPLE)
        assert policy.check_cycle(fp, []) is None

    def test_cycle_detected(self):
        policy = RecursionPolicy(enabled=True)
        fp = make_fingerprint("A", "init", "a.py", TierClassification.SIMPLE)
        path = [fp, "other:fp:x.py:trivial"]
        assert policy.check_cycle(fp, path) == "cycle_detected"

    def test_different_fingerprint_no_cycle(self):
        policy = RecursionPolicy(enabled=True)
        fp1 = make_fingerprint("A", "init", "a.py", TierClassification.SIMPLE)
        fp2 = make_fingerprint("B", "init", "a.py", TierClassification.SIMPLE)
        assert policy.check_cycle(fp2, [fp1]) is None

    def test_cycle_check_disabled_blocks(self):
        policy = RecursionPolicy(enabled=False)
        assert policy.check_cycle("any", []) == "recursion_blocked"


# ── Phase 1: Rejection reasons bounded set tests ─────────────────────


class TestRejectionReasonsBounded:
    """REQ-MP-913: all policy rejections use bounded reason set."""

    def test_all_policy_rejections_in_bounded_set(self):
        """Every rejection reason from policy methods is in RECURSION_REJECTION_REASONS."""
        policy_enabled = RecursionPolicy(enabled=True)
        policy_disabled = RecursionPolicy(enabled=False)

        # Collect all possible rejection reasons from policy methods
        reasons = set()

        # Disabled policy
        reasons.add(policy_disabled.check_depth(0))
        reasons.add(policy_disabled.check_budget(0, 0))
        reasons.add(policy_disabled.check_monotonicity(
            TierClassification.MODERATE, TierClassification.SIMPLE,
        ))
        reasons.add(policy_disabled.check_cycle("fp", []))

        # Enabled policy — trigger each rejection
        reasons.add(policy_enabled.check_depth(99))  # depth_exceeded
        reasons.add(policy_enabled.check_budget(999, 0))  # budget_exceeded
        reasons.add(policy_enabled.check_monotonicity(
            TierClassification.SIMPLE, TierClassification.MODERATE,
        ))  # monotonicity_violation
        reasons.add(policy_enabled.check_cycle("fp", ["fp"]))  # cycle_detected

        # Remove None (success case)
        reasons.discard(None)

        # All reasons must be in the bounded set
        assert reasons == RECURSION_REJECTION_REASONS

    def test_bounded_set_has_expected_members(self):
        assert RECURSION_REJECTION_REASONS == frozenset({
            "recursion_blocked",
            "depth_exceeded",
            "budget_exceeded",
            "monotonicity_violation",
            "cycle_detected",
        })
