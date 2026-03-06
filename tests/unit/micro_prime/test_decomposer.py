"""Tests for the Moderate Decomposer (REQ-MP-900, 901, 904, 907, 908)."""

from __future__ import annotations

import pytest

from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardImportSpec,
    ForwardManifest,
)
from startd8.micro_prime.decomposer import (
    ClassDecomposeStrategy,
    DecompositionPlan,
    ModerateDecomposer,
    SubElement,
    _compute_confidence,
)
from startd8.micro_prime.models import MicroPrimeConfig
from startd8.utils.code_manifest import ElementKind, Param, Signature


# ── ClassDecomposeStrategy Tests (REQ-MP-901) ───────────────────────


class TestClassDecomposeStrategy:
    """Tests for class decomposition strategy."""

    def test_can_handle_class_with_methods(
        self, class_element_with_methods, class_file_spec, class_manifest,
    ):
        """can_handle returns True for class whose methods are separate elements."""
        strategy = ClassDecomposeStrategy()
        assert strategy.can_handle(
            class_element_with_methods, class_file_spec, class_manifest,
            "class definition; long docstring",
        ) is True

    def test_cannot_handle_non_class(
        self, class_file_spec, class_manifest,
    ):
        """can_handle returns False for non-class elements."""
        func_element = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="some_func",
            signature=Signature(params=[], return_annotation="None"),
        )
        strategy = ClassDecomposeStrategy()
        assert strategy.can_handle(
            func_element, class_file_spec, class_manifest, "scoring",
        ) is False

    def test_cannot_handle_class_without_separate_methods(self, class_manifest):
        """Returns False when methods aren't in file_spec as separate elements."""
        # Class element without any child methods in file_spec
        bare_class = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="Lonely",
            bases=[],
        )
        file_spec = ForwardFileSpec(
            file="src/lonely.py",
            imports=[],
            elements=[bare_class],
        )
        strategy = ClassDecomposeStrategy()
        assert strategy.can_handle(
            bare_class, file_spec, class_manifest, "scoring",
        ) is False

    def test_cannot_handle_metaclass(
        self, class_file_spec, class_manifest,
    ):
        """Class with ABCMeta in bases is rejected."""
        meta_class = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="AbstractFormatter",
            bases=["ABCMeta"],
        )
        strategy = ClassDecomposeStrategy()
        assert strategy.can_handle(
            meta_class, class_file_spec, class_manifest, "scoring",
        ) is False

    def test_cannot_handle_complex_dataclass(
        self, class_file_spec, class_manifest,
    ):
        """Class with complex dataclass decorator is rejected."""
        dc_class = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="Config",
            bases=[],
            decorators=["dataclass(frozen=True, field(default_factory=list))"],
        )
        strategy = ClassDecomposeStrategy()
        assert strategy.can_handle(
            dc_class, class_file_spec, class_manifest, "scoring",
        ) is False

    def test_cannot_handle_when_disabled(
        self, class_element_with_methods, class_file_spec, class_manifest,
    ):
        """can_handle returns False when class_decompose_enabled=False."""
        config = MicroPrimeConfig(class_decompose_enabled=False)
        strategy = ClassDecomposeStrategy(config=config)
        assert strategy.can_handle(
            class_element_with_methods, class_file_spec, class_manifest,
            "class definition",
        ) is False

    def test_plan_produces_single_shell_sub_element(
        self, class_element_with_methods, class_file_spec, class_manifest,
    ):
        """Plan for CustomJsonFormatter has 1 sub-element: class_shell (deterministic)."""
        strategy = ClassDecomposeStrategy()
        plan = strategy.plan(
            class_element_with_methods, class_file_spec, class_manifest,
            "class definition; long docstring",
        )
        assert plan is not None
        assert plan.strategy == "class_decompose"
        assert plan.assembly_kind == "class_compose"
        assert len(plan.sub_elements) == 1

        shell = plan.sub_elements[0]
        assert shell.name == "class_shell"
        assert shell.kind == "class_shell"
        assert shell.deterministic is True
        assert shell.element_spec is None
        assert shell.assembly_order == 0

    def test_class_without_attrs_produces_shell_only(self, class_manifest):
        """Class with no class-level attributes produces shell-only plan.

        NOTE: ForwardElementSpec validation disallows parent_class on CONSTANT
        kind elements. Class-level attributes as separate manifest elements
        require schema evolution. For Phase 1, _count_class_attrs returns 0.
        """
        class_elem = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="MyFormatter",
            bases=["logging.Formatter"],
        )
        file_spec = ForwardFileSpec(
            file="src/fmt.py",
            imports=[],
            elements=[
                class_elem,
                ForwardElementSpec(
                    kind=ElementKind.METHOD,
                    name="format",
                    signature=Signature(
                        params=[Param(name="self"), Param(name="record")],
                        return_annotation="str",
                    ),
                    parent_class="MyFormatter",
                ),
            ],
        )
        strategy = ClassDecomposeStrategy()
        plan = strategy.plan(
            class_elem, file_spec, class_manifest, "class definition",
        )
        assert plan is not None
        assert len(plan.sub_elements) == 1
        assert plan.sub_elements[0].kind == "class_shell"

    def test_init_in_manifest_added_to_plan(self, class_manifest):
        """__init__ in file_spec is added to the decomposition plan."""
        class_elem = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="MyClass",
            bases=[],
        )
        file_spec = ForwardFileSpec(
            file="src/cls.py",
            imports=[],
            elements=[
                class_elem,
                ForwardElementSpec(
                    kind=ElementKind.METHOD,
                    name="__init__",
                    signature=Signature(
                        params=[Param(name="self"), Param(name="name")],
                        return_annotation="None",
                    ),
                    parent_class="MyClass",
                ),
                ForwardElementSpec(
                    kind=ElementKind.METHOD,
                    name="run",
                    signature=Signature(
                        params=[Param(name="self")],
                        return_annotation="None",
                    ),
                    parent_class="MyClass",
                ),
            ],
        )
        strategy = ClassDecomposeStrategy()
        plan = strategy.plan(
            class_elem, file_spec, class_manifest, "class definition",
        )
        assert plan is not None
        # class_shell + __init__
        assert len(plan.sub_elements) == 2
        kinds = [s.kind for s in plan.sub_elements]
        assert "class_shell" in kinds
        assert "init" in kinds


# ── Assembly Tests (REQ-MP-904) ─────────────────────────────────────


class TestClassComposeAssembly:
    """Tests for class_compose assembly strategy."""

    def test_shell_only_returns_pass(
        self, class_element_with_methods,
    ):
        """Shell-only class assembly returns 'pass'."""
        strategy = ClassDecomposeStrategy()
        plan = DecompositionPlan(
            original_element=class_element_with_methods,
            sub_elements=[
                SubElement(
                    name="class_shell",
                    kind="class_shell",
                    prompt_context="",
                    depends_on=[],
                    assembly_order=0,
                    element_spec=None,
                    deterministic=True,
                ),
            ],
            strategy="class_decompose",
            assembly_kind="class_compose",
            confidence=1.0,
        )
        result = strategy.assemble(plan, {"class_shell": "pass"}, "")
        assert result == "pass"

    def test_assembly_validates_ast(self, class_element_with_methods):
        """Invalid Python in assembly returns None."""
        strategy = ClassDecomposeStrategy()
        plan = DecompositionPlan(
            original_element=class_element_with_methods,
            sub_elements=[
                SubElement(
                    name="_class_attributes",
                    kind="class_attr",
                    prompt_context="",
                    depends_on=[],
                    assembly_order=1,
                    element_spec=None,
                ),
            ],
            strategy="class_decompose",
            assembly_kind="class_compose",
            confidence=1.0,
        )
        result = strategy.assemble(
            plan,
            {"_class_attributes": "def !!!invalid:"},
            "",
        )
        assert result is None

    def test_assembly_with_attrs_valid(self, class_element_with_methods):
        """Class-level attributes produce valid assembled code."""
        strategy = ClassDecomposeStrategy()
        plan = DecompositionPlan(
            original_element=class_element_with_methods,
            sub_elements=[
                SubElement(
                    name="class_shell", kind="class_shell",
                    prompt_context="", depends_on=[], assembly_order=0,
                    element_spec=None, deterministic=True,
                ),
                SubElement(
                    name="_class_attributes", kind="class_attr",
                    prompt_context="", depends_on=["class_shell"],
                    assembly_order=1, element_spec=None,
                ),
            ],
            strategy="class_decompose",
            assembly_kind="class_compose",
            confidence=1.0,
        )
        result = strategy.assemble(
            plan,
            {
                "class_shell": "pass",
                "_class_attributes": 'FORMAT = "%(message)s"',
            },
            "",
        )
        assert result is not None
        assert "FORMAT" in result

    def test_assembly_with_init_wraps_method(self, class_element_with_methods):
        """__init__ body is wrapped into a method definition."""
        strategy = ClassDecomposeStrategy()
        init_spec = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__init__",
            signature=Signature(
                params=[Param(name="self"), Param(name="name")],
                return_annotation="None",
            ),
            parent_class=class_element_with_methods.name,
        )
        plan = DecompositionPlan(
            original_element=class_element_with_methods,
            sub_elements=[
                SubElement(
                    name="class_shell", kind="class_shell",
                    prompt_context="", depends_on=[], assembly_order=0,
                    element_spec=None, deterministic=True,
                ),
                SubElement(
                    name="__init__", kind="init",
                    prompt_context="", depends_on=["class_shell"],
                    assembly_order=1, element_spec=init_spec,
                ),
            ],
            strategy="class_decompose",
            assembly_kind="class_compose",
            confidence=1.0,
        )
        result = strategy.assemble(
            plan,
            {
                "class_shell": "pass",
                "__init__": "self.name = name",
            },
            "",
        )
        assert result is not None
        assert "def __init__(self, name)" in result
        assert "self.name = name" in result


# ── Confidence Computation Tests (REQ-MP-900, R1-S6) ────────────────


class TestConfidenceComputation:
    """Tests for _compute_confidence."""

    def test_no_signals_returns_high_confidence(self):
        """No uncertainty signals → confidence is 1.0."""
        plan = DecompositionPlan(
            original_element=ForwardElementSpec(
                kind=ElementKind.CLASS, name="Foo",
            ),
            sub_elements=[],
            strategy="class_decompose",
            assembly_kind="class_compose",
            confidence=0.0,
        )
        assert _compute_confidence(plan, []) == 1.0

    def test_all_signals_returns_low_confidence(self):
        """All uncertainty signals → confidence is 0.0."""
        plan = DecompositionPlan(
            original_element=ForwardElementSpec(
                kind=ElementKind.CLASS, name="Foo",
            ),
            sub_elements=[],
            strategy="class_decompose",
            assembly_kind="class_compose",
            confidence=0.0,
        )
        all_signals = [
            "missing_init",
            "inferred_helper_signature",
            "parse_only_responsibility",
            "class_level_attrs_gt1",
        ]
        result = _compute_confidence(plan, all_signals)
        assert result == 0.0

    def test_partial_signals(self):
        """Some signals reduce confidence proportionally."""
        plan = DecompositionPlan(
            original_element=ForwardElementSpec(
                kind=ElementKind.CLASS, name="Foo",
            ),
            sub_elements=[],
            strategy="class_decompose",
            assembly_kind="class_compose",
            confidence=0.0,
        )
        result = _compute_confidence(plan, ["missing_init"])
        assert 0.0 < result < 1.0

    def test_confidence_threshold_rejects_low_confidence(
        self, class_element_with_methods, class_file_spec, class_manifest,
    ):
        """Plan with confidence below threshold returns None from decompose().

        A clean class decomposition has confidence 1.0, so we set the
        threshold to 1.1 (impossible to reach) to test the rejection path.
        """
        config = MicroPrimeConfig(decomposition_confidence_threshold=1.1)
        decomposer = ModerateDecomposer(config=config)
        plan = decomposer.decompose(
            class_element_with_methods, class_file_spec, class_manifest,
            "class definition; long docstring",
        )
        assert plan is None


# ── ModerateDecomposer Tests (REQ-MP-900, 907, 908) ─────────────────


class TestModerateDecomposer:
    """Tests for ModerateDecomposer."""

    def test_can_decompose_class(
        self, class_element_with_methods, class_file_spec, class_manifest,
    ):
        """can_decompose returns True for decomposable class."""
        decomposer = ModerateDecomposer()
        assert decomposer.can_decompose(
            class_element_with_methods, class_file_spec, class_manifest,
            "class definition; long docstring",
        ) is True

    def test_cannot_decompose_function_phase1(
        self, class_file_spec, class_manifest,
    ):
        """Phase 1 has no function strategy — returns False."""
        func = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="process_data",
            signature=Signature(params=[], return_annotation="None"),
        )
        decomposer = ModerateDecomposer()
        assert decomposer.can_decompose(
            func, class_file_spec, class_manifest, "scoring",
        ) is False

    def test_cannot_decompose_when_disabled(
        self, class_element_with_methods, class_file_spec, class_manifest,
    ):
        """decomposition_enabled=False returns False."""
        config = MicroPrimeConfig(decomposition_enabled=False)
        decomposer = ModerateDecomposer(config=config)
        assert decomposer.can_decompose(
            class_element_with_methods, class_file_spec, class_manifest,
            "class definition",
        ) is False

    def test_decompose_class_produces_plan(
        self, class_element_with_methods, class_file_spec, class_manifest,
    ):
        """decompose() returns a plan with 1 sub-element for CustomJsonFormatter."""
        decomposer = ModerateDecomposer()
        plan = decomposer.decompose(
            class_element_with_methods, class_file_spec, class_manifest,
            "class definition; long docstring",
        )
        assert plan is not None
        assert plan.strategy == "class_decompose"
        assert len(plan.sub_elements) == 1
        assert plan.confidence > 0.0

    def test_decompose_disabled_returns_none(
        self, class_element_with_methods, class_file_spec, class_manifest,
    ):
        """decompose() returns None when disabled."""
        config = MicroPrimeConfig(decomposition_enabled=False)
        decomposer = ModerateDecomposer(config=config)
        plan = decomposer.decompose(
            class_element_with_methods, class_file_spec, class_manifest,
            "class definition",
        )
        assert plan is None

    def test_decompose_single_entry_point(
        self, class_element_with_methods, class_file_spec, class_manifest,
    ):
        """decompose() is the single entry point — returns plan directly."""
        decomposer = ModerateDecomposer()
        plan = decomposer.decompose(
            class_element_with_methods, class_file_spec, class_manifest,
            "class definition; long docstring",
        )
        # Should return a plan without needing a separate can_decompose() call
        assert plan is not None
        assert isinstance(plan, DecompositionPlan)

    def test_max_sub_elements_rejects_oversized(self, class_manifest):
        """Plans exceeding max_sub_elements are rejected."""
        config = MicroPrimeConfig(max_sub_elements=0)
        decomposer = ModerateDecomposer(config=config)

        class_elem = ForwardElementSpec(
            kind=ElementKind.CLASS, name="Foo", bases=[],
        )
        file_spec = ForwardFileSpec(
            file="src/foo.py",
            imports=[],
            elements=[
                class_elem,
                ForwardElementSpec(
                    kind=ElementKind.METHOD,
                    name="bar",
                    signature=Signature(
                        params=[Param(name="self")],
                        return_annotation="None",
                    ),
                    parent_class="Foo",
                ),
            ],
        )
        plan = decomposer.decompose(
            class_elem, file_spec, class_manifest, "class definition",
        )
        assert plan is None

    def test_assemble_delegates_to_strategy(
        self, class_element_with_methods, class_file_spec, class_manifest,
    ):
        """assemble() delegates to the matching strategy."""
        decomposer = ModerateDecomposer()
        plan = decomposer.decompose(
            class_element_with_methods, class_file_spec, class_manifest,
            "class definition",
        )
        assert plan is not None
        result = decomposer.assemble(
            plan, {"class_shell": "pass"}, "",
        )
        assert result == "pass"


# ── Engine Integration Tests ─────────────────────────────────────────


class TestHandleModerateInEngine:
    """Tests for _handle_moderate in MicroPrimeEngine."""

    def test_moderate_class_decomposes(
        self, class_element_with_methods, class_file_spec,
        class_skeleton, class_manifest,
    ):
        """MODERATE class with separate methods decomposes successfully."""
        from startd8.micro_prime.engine import MicroPrimeEngine
        from startd8.micro_prime.models import TierClassification

        engine = MicroPrimeEngine()
        file_result = engine.process_file(
            class_file_spec, class_manifest, class_skeleton,
        )
        class_result = next(
            r for r in file_result.element_results
            if r.element_name == "CustomJsonFormatter"
        )
        assert class_result.tier == TierClassification.MODERATE
        assert class_result.success is True
        assert class_result.code == "pass"
        assert class_result.escalation is None
        assert class_result.decomposition_metadata is not None
        assert class_result.decomposition_metadata["strategy"] == "class_decompose"

    def test_decomposition_disabled_escalates(
        self, class_element_with_methods, class_file_spec,
        class_skeleton, class_manifest,
    ):
        """decomposition_enabled=False produces TIER_TOO_HIGH escalation."""
        from startd8.micro_prime.engine import MicroPrimeEngine
        from startd8.micro_prime.models import (
            EscalationReason,
            MicroPrimeConfig,
            TierClassification,
        )

        config = MicroPrimeConfig(decomposition_enabled=False)
        engine = MicroPrimeEngine(config=config)
        file_result = engine.process_file(
            class_file_spec, class_manifest, class_skeleton,
        )
        class_result = next(
            r for r in file_result.element_results
            if r.element_name == "CustomJsonFormatter"
        )
        assert class_result.success is False
        assert class_result.escalation is not None
        assert class_result.escalation.reason == EscalationReason.TIER_TOO_HIGH

    def test_inspect_decomposition(
        self, class_element_with_methods, class_file_spec, class_manifest,
    ):
        """inspect_decomposition returns viability info for dry-run."""
        from startd8.micro_prime.engine import MicroPrimeEngine

        engine = MicroPrimeEngine()
        info = engine.inspect_decomposition(
            class_element_with_methods, class_file_spec, class_manifest,
            "class definition; long docstring",
        )
        assert info["viable"] is True
        assert info["strategy"] == "class_decompose"
        assert info["sub_count"] == 1

    def test_inspect_decomposition_no_manifest(
        self, class_element_with_methods, class_file_spec,
    ):
        """inspect_decomposition returns not viable when manifest is None."""
        from startd8.micro_prime.engine import MicroPrimeEngine

        engine = MicroPrimeEngine()
        info = engine.inspect_decomposition(
            class_element_with_methods, class_file_spec, None,
            "class definition",
        )
        assert info["viable"] is False

    def test_failed_decomposition_does_not_pollute_few_shot(
        self, class_file_spec, class_manifest,
    ):
        """Sub-element successes are rolled back when decomposition fails."""
        from unittest.mock import patch

        from startd8.micro_prime.engine import MicroPrimeEngine
        from startd8.micro_prime.models import TierClassification

        engine = MicroPrimeEngine()
        initial_completed = len(engine._completed)

        # Force _extract_class_shell to return None → decomposition fails
        with patch.object(engine, "_extract_class_shell", return_value=None):
            engine._current_manifest = class_manifest
            result = engine._handle_moderate(
                ForwardElementSpec(
                    kind=ElementKind.CLASS,
                    name="CustomJsonFormatter",
                    bases=["logging.Formatter"],
                ),
                class_file_spec,
                class_manifest,
                "skeleton",
                [],
                "src/emailservice/logger.py",
                "class definition",
            )

        assert result.success is False
        assert len(engine._completed) == initial_completed
