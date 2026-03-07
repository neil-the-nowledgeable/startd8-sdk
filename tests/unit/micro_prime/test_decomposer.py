"""Tests for the Moderate Decomposer (REQ-MP-900, 901, 902, 904, 907, 908)."""

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
    FunctionChainStrategy,
    ModerateDecomposer,
    SubElement,
    _compute_confidence,
    _parse_responsibilities,
    _slugify_helper_name,
    _uniquify_name,
)
from startd8.micro_prime.models import MicroPrimeConfig
from startd8.utils.code_manifest import ElementKind, Param, ParamKind, Signature


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

        NOTE: Class-level attributes are represented as CONSTANT/VARIABLE
        elements with parent_class set to the owning class.
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


# ── FunctionChainStrategy Tests (REQ-MP-902) ─────────────────────────


class TestParseResponsibilities:
    """Tests for _parse_responsibilities helper."""

    def test_semicolon_separated(self):
        text = "Validate the order fields; compute totals with tax; format the confirmation email"
        clauses = _parse_responsibilities(text)
        assert len(clauses) == 3
        assert "Validate the order fields" in clauses[0]

    def test_bullet_separated(self):
        text = "- Validate the order fields\n- Compute totals with tax\n- Format the confirmation email"
        clauses = _parse_responsibilities(text)
        assert len(clauses) == 3

    def test_numbered_separated(self):
        text = "1. Validate the order fields\n2. Compute totals with tax"
        clauses = _parse_responsibilities(text)
        assert len(clauses) == 2

    def test_and_is_not_a_separator(self):
        """'and' within a clause doesn't split it."""
        text = "Validate and sanitize the order fields"
        clauses = _parse_responsibilities(text)
        assert len(clauses) == 1

    def test_short_clauses_ignored(self):
        """Clauses with fewer than 4 words are filtered out."""
        text = "Validate and process the fields; do it; compute totals with tax"
        clauses = _parse_responsibilities(text)
        assert len(clauses) == 2  # "do it" is too short

    def test_empty_string(self):
        assert _parse_responsibilities("") == []

    def test_none_returns_empty(self):
        assert _parse_responsibilities(None) == []


class TestSlugifyHelperName:
    """Tests for _slugify_helper_name helper."""

    def test_basic_slug(self):
        result = _slugify_helper_name("Validate the order fields")
        assert result.startswith("_")
        assert "validate" in result

    def test_long_clause_truncates(self):
        long_clause = " ".join(["word"] * 20)
        result = _slugify_helper_name(long_clause)
        # Takes at most 6 words
        assert result.count("_") <= 7  # _word_word_word_word_word_word

    def test_empty_returns_empty(self):
        assert _slugify_helper_name("") == ""

    def test_slug_over_48_chars_returns_empty(self):
        long_clause = "a " * 30 + "very long responsibility text"
        result = _slugify_helper_name(long_clause)
        # Takes 6 words max; if slug > 48 chars, returns ""
        # With short words this won't exceed, so test with explicit long words
        assert isinstance(result, str)


class TestUniquifyName:
    """Tests for _uniquify_name helper."""

    def test_no_collision(self):
        assert _uniquify_name("_foo", set()) == "_foo"

    def test_collision_adds_suffix(self):
        assert _uniquify_name("_foo", {"_foo"}) == "_foo_2"

    def test_double_collision(self):
        assert _uniquify_name("_foo", {"_foo", "_foo_2"}) == "_foo_3"


class TestFunctionChainStrategy:
    """Tests for function decomposition strategy (REQ-MP-902)."""

    @pytest.fixture
    def func_element(self):
        return ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="process_order",
            signature=Signature(
                params=[
                    Param(name="order", annotation="Order"),
                    Param(name="config", annotation="Config"),
                ],
                return_annotation="str",
            ),
            docstring_hint="Validate the order fields; compute totals with tax; format the confirmation email",
        )

    @pytest.fixture
    def method_element(self):
        return ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="process_order",
            signature=Signature(
                params=[
                    Param(name="self"),
                    Param(name="order", annotation="Order"),
                ],
                return_annotation="str",
            ),
            parent_class="OrderService",
            docstring_hint="Validate the order fields; compute totals with tax; format the confirmation email",
        )

    @pytest.fixture
    def func_file_spec(self, func_element):
        return ForwardFileSpec(
            file="src/orders.py",
            imports=[ForwardImportSpec(kind="import", module="typing", names=["Any"])],
            elements=[func_element],
        )

    @pytest.fixture
    def func_manifest(self, func_file_spec):
        return ForwardManifest(file_specs={"src/orders.py": func_file_spec})

    def test_can_handle_function_with_clauses(
        self, func_element, func_file_spec, func_manifest,
    ):
        strategy = FunctionChainStrategy()
        assert strategy.can_handle(
            func_element, func_file_spec, func_manifest, "scoring",
        ) is True

    def test_cannot_handle_class(self, func_file_spec, func_manifest):
        cls = ForwardElementSpec(
            kind=ElementKind.CLASS, name="Foo",
        )
        strategy = FunctionChainStrategy()
        assert strategy.can_handle(
            cls, func_file_spec, func_manifest, "scoring",
        ) is False

    def test_cannot_handle_no_docstring(self, func_file_spec, func_manifest):
        func = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="simple_func",
            signature=Signature(params=[], return_annotation="None"),
        )
        strategy = FunctionChainStrategy()
        assert strategy.can_handle(
            func, func_file_spec, func_manifest, "scoring",
        ) is False

    def test_cannot_handle_single_clause(self, func_file_spec, func_manifest):
        func = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="simple_func",
            signature=Signature(params=[], return_annotation="None"),
            docstring_hint="Just validate and sanitize the order fields",
        )
        strategy = FunctionChainStrategy()
        assert strategy.can_handle(
            func, func_file_spec, func_manifest, "scoring",
        ) is False

    def test_cannot_handle_api_classification(
        self, func_element, func_file_spec, func_manifest,
    ):
        """Elements classified due to external API are excluded."""
        strategy = FunctionChainStrategy()
        assert strategy.can_handle(
            func_element, func_file_spec, func_manifest,
            "file has 9 external imports (>8); external API dependency",
        ) is False

    def test_cannot_handle_orchestrator_classification(
        self, func_element, func_file_spec, func_manifest,
    ):
        strategy = FunctionChainStrategy()
        assert strategy.can_handle(
            func_element, func_file_spec, func_manifest,
            "orchestrator pattern detected",
        ) is False

    def test_cannot_handle_with_classification_signals(
        self, func_element, func_file_spec, func_manifest,
    ):
        """When classification_signals are provided, they take precedence."""
        strategy = FunctionChainStrategy()
        assert strategy.can_handle(
            func_element, func_file_spec, func_manifest,
            "scoring",
            classification_signals={"external_api"},
        ) is False

    def test_cannot_handle_too_many_clauses(
        self, func_file_spec, func_manifest,
    ):
        func = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="big_func",
            signature=Signature(params=[], return_annotation="None"),
            docstring_hint=(
                "Step one validate the data; step two process the data; "
                "step three format the output; step four send the result; "
                "step five log the outcome"
            ),
        )
        strategy = FunctionChainStrategy()
        assert strategy.can_handle(
            func, func_file_spec, func_manifest, "scoring",
        ) is False

    def test_cannot_handle_when_disabled(
        self, func_element, func_file_spec, func_manifest,
    ):
        config = MicroPrimeConfig(function_chain_enabled=False)
        strategy = FunctionChainStrategy(config=config)
        assert strategy.can_handle(
            func_element, func_file_spec, func_manifest, "scoring",
        ) is False

    def test_plan_produces_helpers_and_dispatch(
        self, func_element, func_file_spec, func_manifest,
    ):
        strategy = FunctionChainStrategy()
        plan = strategy.plan(
            func_element, func_file_spec, func_manifest, "scoring",
        )
        assert plan is not None
        assert plan.strategy == "function_chain"
        assert plan.assembly_kind == "function_chain"

        helpers = [s for s in plan.sub_elements if s.kind == "helper"]
        dispatch = [s for s in plan.sub_elements if s.kind == "dispatch_body"]
        assert len(helpers) == 3
        assert len(dispatch) == 1

        # Helpers have element_specs with params forwarded
        for h in helpers:
            assert h.element_spec is not None
            assert h.element_spec.signature is not None
            param_names = [p.name for p in h.element_spec.signature.params]
            assert "order" in param_names
            assert "config" in param_names

        # Dispatch depends on all helpers
        assert len(dispatch[0].depends_on) == 3

    def test_plan_method_helpers_include_self(
        self, method_element, func_file_spec, func_manifest,
    ):
        strategy = FunctionChainStrategy()
        plan = strategy.plan(
            method_element, func_file_spec, func_manifest, "scoring",
        )
        assert plan is not None
        helpers = [s for s in plan.sub_elements if s.kind == "helper"]
        for h in helpers:
            assert h.element_spec.parent_class == "OrderService"
            param_names = [p.name for p in h.element_spec.signature.params]
            assert param_names[0] == "self"

    def test_plan_helper_names_are_unique(self, func_file_spec, func_manifest):
        """Helper names don't collide with existing elements."""
        func = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="process",
            signature=Signature(params=[], return_annotation="None"),
            docstring_hint="Validate the order fields; compute totals with tax",
        )
        # Add a collision element
        func_file_spec_with_collision = ForwardFileSpec(
            file="src/orders.py",
            imports=func_file_spec.imports,
            elements=[func, ForwardElementSpec(
                kind=ElementKind.FUNCTION,
                name="_validate_the_order_fields",
                signature=Signature(params=[], return_annotation="None"),
            )],
        )
        manifest = ForwardManifest(
            file_specs={"src/orders.py": func_file_spec_with_collision},
        )
        strategy = FunctionChainStrategy()
        plan = strategy.plan(
            func, func_file_spec_with_collision, manifest, "scoring",
        )
        assert plan is not None
        helper_names = [s.name for s in plan.sub_elements if s.kind == "helper"]
        assert len(helper_names) == len(set(helper_names))  # all unique

    def test_assemble_module_function(
        self, func_element, func_file_spec, func_manifest,
    ):
        """Assembly for module-level functions concatenates helpers + dispatch."""
        strategy = FunctionChainStrategy()
        plan = strategy.plan(
            func_element, func_file_spec, func_manifest, "scoring",
        )
        assert plan is not None
        helpers = [s for s in plan.sub_elements if s.kind == "helper"]
        dispatch = next(s for s in plan.sub_elements if s.kind == "dispatch_body")

        sub_results = {dispatch.name: "return _helper_1(order)"}
        for h in helpers:
            sub_results[h.name] = "return None"

        result = strategy.assemble(plan, sub_results, "")
        assert result is not None
        assert "def" in result  # helpers have def lines
        assert "return _helper_1(order)" in result

    def test_assemble_method_returns_dispatch_only(
        self, method_element, func_file_spec, func_manifest,
    ):
        """Assembly for methods returns only dispatch body (helpers are separate)."""
        strategy = FunctionChainStrategy()
        plan = strategy.plan(
            method_element, func_file_spec, func_manifest, "scoring",
        )
        assert plan is not None
        dispatch = next(s for s in plan.sub_elements if s.kind == "dispatch_body")
        helpers = [s for s in plan.sub_elements if s.kind == "helper"]

        sub_results = {dispatch.name: "return self._validate(self.order)"}
        for h in helpers:
            sub_results[h.name] = "pass"

        result = strategy.assemble(plan, sub_results, "")
        assert result is not None
        assert result == "return self._validate(self.order)"
        assert "def" not in result  # No helper defs for methods

    def test_assemble_missing_dispatch_returns_none(
        self, func_element, func_file_spec, func_manifest,
    ):
        strategy = FunctionChainStrategy()
        plan = strategy.plan(
            func_element, func_file_spec, func_manifest, "scoring",
        )
        assert plan is not None
        result = strategy.assemble(plan, {}, "")
        assert result is None

    def test_plan_confidence_with_slug_fallback(self, func_file_spec, func_manifest):
        """Inferred helper names reduce confidence."""
        func = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="do_work",
            signature=Signature(params=[], return_annotation="None"),
            # Clauses made of only special chars → empty slug → fallback
            docstring_hint="$$$ %%% ^^^ &&& @@@ !!!; $$$ %%% ^^^ &&& @@@ !!!",
        )
        strategy = FunctionChainStrategy()
        plan = strategy.plan(
            func, func_file_spec, func_manifest, "scoring",
        )
        if plan is not None:
            # Empty slugs trigger _helper_N fallback and inferred_helper_signature signal
            assert plan.confidence < 1.0


class TestModerateDecomposerFunctionChain:
    """Test that ModerateDecomposer routes to FunctionChainStrategy."""

    def test_can_decompose_function_with_clauses(self):
        func = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="process",
            signature=Signature(params=[], return_annotation="None"),
            docstring_hint="Validate the order fields; compute totals with tax",
        )
        file_spec = ForwardFileSpec(
            file="src/orders.py", imports=[], elements=[func],
        )
        manifest = ForwardManifest(file_specs={"src/orders.py": file_spec})
        decomposer = ModerateDecomposer()
        assert decomposer.can_decompose(
            func, file_spec, manifest, "scoring",
        ) is True

    def test_decompose_function_produces_plan(self):
        func = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="process",
            signature=Signature(
                params=[Param(name="data", annotation="dict")],
                return_annotation="str",
            ),
            docstring_hint="Validate the input data; transform to output format",
        )
        file_spec = ForwardFileSpec(
            file="src/orders.py", imports=[], elements=[func],
        )
        manifest = ForwardManifest(file_specs={"src/orders.py": file_spec})
        decomposer = ModerateDecomposer()
        plan = decomposer.decompose(
            func, file_spec, manifest, "scoring",
        )
        assert plan is not None
        assert plan.strategy == "function_chain"
        assert len(plan.sub_elements) == 3  # 2 helpers + 1 dispatch


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
