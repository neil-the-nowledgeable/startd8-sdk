"""Tests for multi-language element prompts — REQ-MPL-101.

Verifies that element generation prompts use language-specific instructions
from the LanguageProfile (stub markers, indentation, declaration keywords)
instead of hardcoded Python defaults.
"""

import pytest
from unittest.mock import Mock

from startd8.micro_prime.prompt_builder import (
    build_full_function_prompt,
    build_body_prompt,
)
from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
)
from startd8.utils.code_manifest import ElementKind, Signature
from startd8.languages.registry import LanguageRegistry

_EMPTY_SIG = Signature(params=[])


@pytest.fixture(autouse=True, scope="module")
def discover():
    LanguageRegistry.discover()


def _make_element(name="doWork", kind=ElementKind.FUNCTION):
    return ForwardElementSpec(name=name, kind=kind, signature=_EMPTY_SIG)


def _make_file_spec():
    return ForwardFileSpec(file="src/main.go", elements=[], imports=[])


class TestGoPromptInstructions:
    """REQ-MPL-101: Go prompts use Go-specific instructions."""

    def _go_profile(self):
        return LanguageRegistry.get("go")

    def test_full_function_uses_func_keyword(self):
        prompt = build_full_function_prompt(
            _make_element(), _make_file_spec(), [],
            language_profile=self._go_profile(),
        )
        assert "`func`" in prompt
        assert "`def`" not in prompt

    def test_full_function_no_fences_instruction(self):
        prompt = build_full_function_prompt(
            _make_element(), _make_file_spec(), [],
            language_profile=self._go_profile(),
        )
        assert "code blocks" in prompt.lower() or "markdown fences" in prompt.lower()

    def test_body_prompt_uses_panic_stub(self):
        prompt = build_body_prompt(
            _make_element(), _make_file_spec(), [],
            language_profile=self._go_profile(),
        )
        # The instruction line should reference Go stub, not Python stub.
        # Note: the stub CODE in the skeleton section may still show Python
        # (from _build_element_stub) — that's a separate concern (deferred).
        assert 'panic("not implemented")' in prompt

    def test_body_prompt_uses_tab_indentation(self):
        prompt = build_body_prompt(
            _make_element(), _make_file_spec(), [],
            language_profile=self._go_profile(),
        )
        assert "tab indentation" in prompt.lower()


class TestPythonPromptUnchanged:
    """Regression: Python prompts still use Python defaults."""

    def _py_profile(self):
        return LanguageRegistry.get("python")

    def test_full_function_uses_def_keyword(self):
        prompt = build_full_function_prompt(
            _make_element(), _make_file_spec(), [],
            language_profile=self._py_profile(),
        )
        assert "`def`" in prompt

    def test_body_prompt_uses_notimplemented(self):
        prompt = build_body_prompt(
            _make_element(), _make_file_spec(), [],
            language_profile=self._py_profile(),
        )
        assert "NotImplementedError" in prompt


class TestNoneProfileDefaultsPython:
    """REQ-MPL-101: None profile falls back to Python defaults."""

    def test_full_function_defaults_def(self):
        prompt = build_full_function_prompt(
            _make_element(), _make_file_spec(), [],
            language_profile=None,
        )
        assert "`def`" in prompt

    def test_body_prompt_defaults_notimplemented(self):
        prompt = build_body_prompt(
            _make_element(), _make_file_spec(), [],
            language_profile=None,
        )
        assert "NotImplementedError" in prompt


class TestNodejsPromptInstructions:
    """REQ-NODE-MP-700: Node.js prompts use 2-space indentation."""

    def _node_profile(self):
        return LanguageRegistry.get("nodejs")

    def test_full_function_uses_function_keyword(self):
        prompt = build_full_function_prompt(
            _make_element(), _make_file_spec(), [],
            language_profile=self._node_profile(),
        )
        assert "`function`" in prompt
        assert "`def`" not in prompt

    def test_body_prompt_uses_2_space_indent(self):
        prompt = build_body_prompt(
            _make_element(), _make_file_spec(), [],
            language_profile=self._node_profile(),
        )
        assert "2 spaces" in prompt

    def test_body_prompt_uses_throw_error_stub(self):
        prompt = build_body_prompt(
            _make_element(), _make_file_spec(), [],
            language_profile=self._node_profile(),
        )
        assert 'throw new Error("not implemented")' in prompt


class TestCSharpPromptInstructions:
    """REQ-MPL-101: C# prompts use C#-specific keywords."""

    def _cs_profile(self):
        return LanguageRegistry.get("csharp")

    def test_full_function_uses_public_private(self):
        prompt = build_full_function_prompt(
            _make_element(), _make_file_spec(), [],
            language_profile=self._cs_profile(),
        )
        assert "`public/private`" in prompt

    def test_body_prompt_uses_notimplemented_exception(self):
        prompt = build_body_prompt(
            _make_element(), _make_file_spec(), [],
            language_profile=self._cs_profile(),
        )
        assert "NotImplementedException" in prompt
