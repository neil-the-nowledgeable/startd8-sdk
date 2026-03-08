"""Tests for the Micro Prime Prompt Builder (REQ-MP-200–205)."""

from __future__ import annotations

import pytest

from startd8.forward_manifest import (
    ContractCategory,
    ContractConfidence,
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardImportSpec,
    InterfaceContract,
)
from startd8.micro_prime.prompt_builder import (
    _build_element_stub,
    _estimate_body_lines,
    _render_constraints,
    _render_imports,
    _render_sibling_stubs,
    build_body_prompt,
    find_few_shot_examples,
)
from startd8.utils.code_manifest import ElementKind, Param, Signature


class TestBuildBodyPrompt:
    """Tests for build_body_prompt()."""

    def test_function_prompt_contains_instructions(
        self, simple_function_element, sample_file_spec, sample_contracts,
    ):
        prompt = build_body_prompt(
            simple_function_element, sample_file_spec, sample_contracts,
        )
        assert "Implement ONLY the function body" in prompt
        assert "raise NotImplementedError" in prompt
        assert "def get_name" in prompt

    def test_method_prompt_contains_class_context(
        self, simple_function_element, sample_file_spec, sample_contracts,
    ):
        """REQ-MP-201: Methods include class context."""
        prompt = build_body_prompt(
            simple_function_element, sample_file_spec, sample_contracts,
        )
        assert "method of class" in prompt
        assert "MyClass" in prompt

    def test_prompt_includes_imports(
        self, simple_function_element, sample_file_spec, sample_contracts,
    ):
        """REQ-MP-201: Imports included for API surface restriction."""
        prompt = build_body_prompt(
            simple_function_element, sample_file_spec, sample_contracts,
        )
        assert "from typing import Optional, List" in prompt
        assert "import json" in prompt

    def test_prompt_includes_constraints(
        self, simple_function_element, sample_file_spec, sample_contracts,
    ):
        prompt = build_body_prompt(
            simple_function_element, sample_file_spec, sample_contracts,
        )
        assert "[BINDING]" in prompt
        assert "get_name" in prompt

    def test_prompt_includes_sibling_stubs(
        self, simple_function_element, sample_file_spec, empty_contracts,
    ):
        """REQ-MP-201: Sibling stubs for class context."""
        prompt = build_body_prompt(
            simple_function_element, sample_file_spec, empty_contracts,
        )
        assert "get_value" in prompt
        assert "Other methods" in prompt


class TestConstantPrompt:
    """Tests for constant prompt (REQ-MP-204)."""

    def test_constant_prompt_format(
        self, constant_element, sample_file_spec, empty_contracts,
    ):
        prompt = build_body_prompt(
            constant_element, sample_file_spec, empty_contracts,
        )
        assert "module-level variable" in prompt
        assert "assignment statement" in prompt
        assert "DEFAULT_TIMEOUT" in prompt

    def test_constant_prompt_no_function_instructions(
        self, constant_element, sample_file_spec, empty_contracts,
    ):
        prompt = build_body_prompt(
            constant_element, sample_file_spec, empty_contracts,
        )
        assert "function body" not in prompt.lower()


class TestAsyncPrompt:
    """Tests for async function prompts."""

    def test_async_def_keyword(
        self, async_function_element, sample_file_spec, empty_contracts,
    ):
        prompt = build_body_prompt(
            async_function_element, sample_file_spec, empty_contracts,
        )
        assert "`async def fetch_data(" in prompt


class TestFewShotExamples:
    """Tests for few-shot example injection (REQ-MP-203)."""

    def test_few_shot_in_prompt(
        self, simple_function_element, sample_file_spec, empty_contracts,
    ):
        examples = ["def helper():\n    return 42"]
        prompt = build_body_prompt(
            simple_function_element, sample_file_spec, empty_contracts,
            few_shot_examples=examples,
        )
        assert "Example (completed)" in prompt
        assert "return 42" in prompt

    def test_max_two_examples(
        self, simple_function_element, sample_file_spec, empty_contracts,
    ):
        examples = [f"def f{i}():\n    return {i}" for i in range(5)]
        prompt = build_body_prompt(
            simple_function_element, sample_file_spec, empty_contracts,
            few_shot_examples=examples,
        )
        # Should only include 2 examples
        assert prompt.count("Example") <= 2


class TestBuildElementStub:
    """Tests for _build_element_stub()."""

    def test_function_stub(self, simple_function_element):
        stub = _build_element_stub(simple_function_element)
        assert "def get_name(self, key: str) -> str:" in stub
        assert "raise NotImplementedError" in stub

    def test_async_stub(self, async_function_element):
        stub = _build_element_stub(async_function_element)
        assert "async def fetch_data" in stub

    def test_property_stub(self, property_element):
        stub = _build_element_stub(property_element)
        assert "@property" in stub
        assert "def total" in stub

    def test_class_stub(self):
        elem = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="MyModel",
            bases=["BaseModel"],
        )
        stub = _build_element_stub(elem)
        assert "class MyModel(BaseModel):" in stub

    def test_stub_includes_docstring(self, simple_function_element):
        stub = _build_element_stub(simple_function_element)
        assert "Return the name" in stub

    def test_stub_includes_decorators(self):
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="cached",
            signature=Signature(params=[Param(name="self")]),
            decorators=["lru_cache"],
            parent_class="Cache",
        )
        stub = _build_element_stub(elem)
        assert "@lru_cache" in stub


class TestEstimateBodyLines:
    """Tests for _estimate_body_lines()."""

    def test_constant_estimate(self, constant_element):
        assert _estimate_body_lines(constant_element) == "1-2"

    def test_property_estimate(self, property_element):
        assert _estimate_body_lines(property_element) == "1-2"

    def test_no_params_estimate(self):
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="foo",
            signature=Signature(params=[]),
        )
        assert _estimate_body_lines(elem) == "3-6"

    def test_few_params_estimate(self):
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="foo",
            signature=Signature(params=[
                Param(name="a"), Param(name="b"),
            ]),
        )
        assert _estimate_body_lines(elem) == "4-8"

    def test_many_params_estimate(self):
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="foo",
            signature=Signature(params=[
                Param(name="a"), Param(name="b"), Param(name="c"),
            ]),
        )
        assert _estimate_body_lines(elem) == "6-12"


class TestFindFewShotExamples:
    """Tests for find_few_shot_examples()."""

    def test_finds_same_class_examples(self, simple_function_element):
        completed = [
            {
                "element": {"name": "get_value", "parent_class": "MyClass"},
                "file_path": "src/mypackage/utils.py",
                "code": "def get_value(self):\n    return 42",
                "syntax_valid": True,
            },
        ]
        examples = find_few_shot_examples(
            simple_function_element,
            "src/mypackage/utils.py",
            completed,
        )
        assert len(examples) == 1
        assert "return 42" in examples[0]

    def test_finds_same_file_examples(self):
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="process",
            signature=Signature(params=[], return_annotation="None"),
        )
        completed = [
            {
                "element": {"name": "helper", "parent_class": None},
                "file_path": "src/module.py",
                "code": "def helper():\n    return True",
                "syntax_valid": True,
            },
        ]
        examples = find_few_shot_examples(elem, "src/module.py", completed)
        assert len(examples) == 1

    def test_max_examples_limit(self, simple_function_element):
        completed = [
            {
                "element": {"name": f"method_{i}", "parent_class": "MyClass"},
                "file_path": "src/mypackage/utils.py",
                "code": f"def method_{i}(self):\n    return {i}",
                "syntax_valid": True,
            }
            for i in range(5)
        ]
        examples = find_few_shot_examples(
            simple_function_element,
            "src/mypackage/utils.py",
            completed,
            max_examples=2,
        )
        assert len(examples) == 2

    def test_skips_invalid_code(self, simple_function_element):
        completed = [
            {
                "element": {"name": "bad", "parent_class": "MyClass"},
                "file_path": "src/mypackage/utils.py",
                "code": "broken code",
                "syntax_valid": False,
            },
        ]
        examples = find_few_shot_examples(
            simple_function_element,
            "src/mypackage/utils.py",
            completed,
        )
        assert len(examples) == 0

    def test_empty_completed_list(self, simple_function_element):
        examples = find_few_shot_examples(
            simple_function_element,
            "src/mypackage/utils.py",
            [],
        )
        assert len(examples) == 0

    def test_tier3_same_kind_across_files(self):
        """Tier 3: same-kind examples from other files (REQ-MP-205)."""
        target = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="process",
            signature=Signature(params=[Param(name="self")]),
            parent_class="Worker",
        )
        completed = [
            {
                "element": {
                    "name": "run",
                    "parent_class": "OtherClass",
                    "kind": ElementKind.METHOD,
                },
                "file_path": "src/other/module.py",  # different file
                "code": "def run(self):\n    return True",
                "syntax_valid": True,
            },
        ]
        examples = find_few_shot_examples(
            target, "src/worker/module.py", completed,
        )
        # Not same class, not same file — matched via same kind (METHOD)
        assert len(examples) == 1
        assert "return True" in examples[0]

    def test_tier_priority_order(self):
        """Tier 1 (same-class) preferred over Tier 2 (same-file) over Tier 3 (same-kind)."""
        target = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="target",
            signature=Signature(params=[Param(name="self")]),
            parent_class="MyClass",
        )
        completed = [
            # Tier 3 only: same kind, different file, different class
            {
                "element": {"name": "other_kind", "parent_class": "Other", "kind": ElementKind.METHOD},
                "file_path": "src/other.py",
                "code": "def other_kind(self):\n    return 'kind'",
                "syntax_valid": True,
            },
            # Tier 2: same file, different class
            {
                "element": {"name": "same_file", "parent_class": "OtherLocal", "kind": ElementKind.METHOD},
                "file_path": "src/mine.py",
                "code": "def same_file(self):\n    return 'file'",
                "syntax_valid": True,
            },
            # Tier 1: same class
            {
                "element": {"name": "same_class", "parent_class": "MyClass", "kind": ElementKind.METHOD},
                "file_path": "src/mine.py",
                "code": "def same_class(self):\n    return 'class'",
                "syntax_valid": True,
            },
        ]
        examples = find_few_shot_examples(
            target, "src/mine.py", completed, max_examples=2,
        )
        assert len(examples) == 2
        # Tier 1 (same class) should be first
        assert "return 'class'" in examples[0]
        # Tier 2 (same file) should fill the second slot
        assert "return 'file'" in examples[1]


# ═══════════════════════════════════════════════════════════════════════════
# Design Doc Sections (REQ-DDS-001)
# ═══════════════════════════════════════════════════════════════════════════


class TestDesignDocSections:
    def test_prompt_builder_with_design_sections(
        self, simple_function_element, sample_file_spec, sample_contracts,
    ):
        """# Implementation context: section rendered when sections provided."""
        sections = [
            "Stage 1: ChatGoogleGenerativeAI gemini-1.5-flash with HumanMessage",
            "Error handling returning HTTP error responses per stage",
        ]
        prompt = build_body_prompt(
            simple_function_element,
            sample_file_spec,
            sample_contracts,
            design_doc_sections=sections,
        )
        assert "# Implementation context:" in prompt
        assert "ChatGoogleGenerativeAI" in prompt
        assert "Error handling" in prompt

    def test_prompt_builder_without_design_sections(
        self, simple_function_element, sample_file_spec, sample_contracts,
    ):
        """No section when empty/None."""
        prompt = build_body_prompt(
            simple_function_element,
            sample_file_spec,
            sample_contracts,
            design_doc_sections=None,
        )
        assert "# Implementation context:" not in prompt

        prompt_empty = build_body_prompt(
            simple_function_element,
            sample_file_spec,
            sample_contracts,
            design_doc_sections=[],
        )
        assert "# Implementation context:" not in prompt_empty


class TestTaskDescription:
    """Tests for task_description forwarding (Mottainai Rule 2)."""

    def test_task_description_rendered_in_prompt(
        self, simple_function_element, sample_file_spec, sample_contracts,
    ):
        """Task context line rendered when task_description provided."""
        desc = "Creates insecure gRPC channel to localhost:8080, calls SendOrderConfirmation"
        prompt = build_body_prompt(
            simple_function_element,
            sample_file_spec,
            sample_contracts,
            task_description=desc,
        )
        assert "# Task context:" in prompt
        assert "gRPC" in prompt
        assert "SendOrderConfirmation" in prompt

    def test_task_description_absent_when_none(
        self, simple_function_element, sample_file_spec, sample_contracts,
    ):
        """No task context line when task_description is None or empty."""
        prompt = build_body_prompt(
            simple_function_element,
            sample_file_spec,
            sample_contracts,
            task_description=None,
        )
        assert "# Task context:" not in prompt

        prompt_empty = build_body_prompt(
            simple_function_element,
            sample_file_spec,
            sample_contracts,
            task_description="",
        )
        assert "# Task context:" not in prompt_empty

    def test_task_description_before_design_sections(
        self, simple_function_element, sample_file_spec, sample_contracts,
    ):
        """Task context appears before implementation context."""
        prompt = build_body_prompt(
            simple_function_element,
            sample_file_spec,
            sample_contracts,
            design_doc_sections=["RpcError handling"],
            task_description="gRPC test client",
        )
        task_pos = prompt.index("# Task context:")
        impl_pos = prompt.index("# Implementation context:")
        assert task_pos < impl_pos
