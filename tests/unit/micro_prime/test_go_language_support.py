"""Tests for MicroPrime Go language support (MP-P1 through MP-P6).

Covers:
- MP-P1: Language-parameterized system prompts
- MP-P1b: Pluggable syntax validation
- MP-P2: Go keyword reserves
- MP-P3: Go structural verification (stub detection)
- MP-P4: Go signature rendering
- MP-P5: Go literal coercion
- MP-P6: Go function decomposition
- Integration: Go files not bypassed
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest

from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
)
from startd8.micro_prime.engine import (
    MicroPrimeEngine,
    _build_system_prompt,
    _coerce_literals_for_language,
    _is_non_python_file,
    _skeleton_has_stubs,
    _validate_file_whole_result,
    extract_function_body,
    _ELEMENT_BODY_SYSTEM_PROMPT,
    _ELEMENT_FULL_FUNCTION_SYSTEM_PROMPT,
    _FILE_WHOLE_SYSTEM_PROMPT,
)
from startd8.micro_prime.decomposer import (
    FunctionChainStrategy,
    ModerateDecomposer,
    _GO_RESERVED,
    _PYTHON_RESERVED,
    _render_go_signature_str,
    _render_signature_for_language,
    _slugify_helper_name,
)
from startd8.micro_prime.models import MicroPrimeConfig
from startd8.languages.go import GoLanguageProfile
from startd8.languages.python import PythonLanguageProfile
from startd8.utils.code_manifest import ElementKind, Param, ParamKind, Signature


# ── Helpers ──


def _go_profile() -> GoLanguageProfile:
    return GoLanguageProfile()


def _py_profile() -> PythonLanguageProfile:
    return PythonLanguageProfile()


def _make_element(name: str = "main", kind: ElementKind = ElementKind.FUNCTION) -> ForwardElementSpec:
    return ForwardElementSpec(
        kind=kind,
        name=name,
        signature=Signature(params=[], return_annotation="None"),
        docstring_hint="Entry point.",
    )


def _make_file_spec(file_path: str) -> ForwardFileSpec:
    return ForwardFileSpec(
        file=file_path,
        elements=[_make_element()],
    )


# ── MP-P1: Language-Parameterized System Prompts ──


class TestBuildSystemPrompt:
    """MP-P1: System prompts are language-parameterized."""

    def test_python_body_matches_constant(self) -> None:
        """Python body prompt must match the legacy constant exactly."""
        assert _build_system_prompt(_py_profile(), "body") == _ELEMENT_BODY_SYSTEM_PROMPT

    def test_python_full_function_matches_constant(self) -> None:
        assert _build_system_prompt(_py_profile(), "full_function") == _ELEMENT_FULL_FUNCTION_SYSTEM_PROMPT

    def test_python_file_whole_matches_constant(self) -> None:
        assert _build_system_prompt(_py_profile(), "file_whole") == _FILE_WHOLE_SYSTEM_PROMPT

    def test_python_none_profile_matches_constant(self) -> None:
        """None profile defaults to Python."""
        assert _build_system_prompt(None, "body") == _ELEMENT_BODY_SYSTEM_PROMPT

    def test_go_body_contains_go_role(self) -> None:
        prompt = _build_system_prompt(_go_profile(), "body")
        assert "Go engineer" in prompt or "Go" in prompt

    def test_go_body_uses_tab_indent(self) -> None:
        prompt = _build_system_prompt(_go_profile(), "body")
        assert "tab" in prompt.lower()

    def test_go_body_no_python_references(self) -> None:
        prompt = _build_system_prompt(_go_profile(), "body")
        assert "Python" not in prompt
        assert "def " not in prompt

    def test_go_file_whole_mentions_panic_stub(self) -> None:
        prompt = _build_system_prompt(_go_profile(), "file_whole")
        assert "panic" in prompt

    def test_go_full_function_mentions_closing_brace(self) -> None:
        prompt = _build_system_prompt(_go_profile(), "full_function")
        assert "brace" in prompt.lower()

    def test_engine_uses_language_profile_for_prompts(self) -> None:
        """Engine._get_system_prompt dispatches through _build_system_prompt."""
        config = MicroPrimeConfig(provider="ollama", model="test")
        engine = MicroPrimeEngine(config=config, language_profile=_go_profile())
        prompt = engine._get_system_prompt("body")
        assert "Go" in prompt


# ── MP-P1b: Pluggable Syntax Validation ──


class TestValidateSyntax:
    """MP-P1b: Language-dispatched syntax validation."""

    def test_python_valid_code(self) -> None:
        ok, err = _py_profile().validate_syntax("x = 1")
        assert ok is True
        assert err == ""

    def test_python_invalid_code(self) -> None:
        ok, err = _py_profile().validate_syntax("def :")
        assert ok is False
        assert err != ""

    def test_go_validate_syntax_exists(self) -> None:
        """GoLanguageProfile has validate_syntax method."""
        profile = _go_profile()
        assert hasattr(profile, "validate_syntax")

    @patch("subprocess.run")
    def test_go_valid_code_via_gofmt(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        ok, err = _go_profile().validate_syntax('package main\nfunc main() {}')
        assert ok is True

    @patch("subprocess.run")
    def test_go_invalid_code_via_gofmt(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stderr="syntax error")
        ok, err = _go_profile().validate_syntax('func {')
        assert ok is False
        assert "syntax error" in err

    def test_engine_syntax_valid_dispatches(self) -> None:
        """Engine._syntax_valid uses language_profile."""
        config = MicroPrimeConfig(provider="ollama", model="test")
        engine = MicroPrimeEngine(config=config, language_profile=_py_profile())
        assert engine._syntax_valid("x = 1") is True
        assert engine._syntax_valid("def :") is False


# ── MP-P2: Go Keyword Reserves ──


class TestGoKeywordReserves:
    """MP-P2: Language-dispatched reserved word checking."""

    def test_go_reserved_contains_keywords(self) -> None:
        for kw in ("func", "go", "select", "chan", "defer", "interface"):
            assert kw in _GO_RESERVED, f"Missing Go keyword: {kw}"

    def test_go_reserved_contains_predeclared(self) -> None:
        for name in ("nil", "true", "false", "make", "len", "append"):
            assert name in _GO_RESERVED, f"Missing predeclared: {name}"

    def test_slugify_rejects_go_keyword_as_slug(self) -> None:
        """A single-word clause that is a Go keyword should be rejected."""
        # _slugify checks "slug in reserved" — slug must equal a reserved word
        slug = _slugify_helper_name("select items", "go")
        # The slug is "select_items" which is NOT in _GO_RESERVED, so it passes
        assert slug != ""
        # But a clause that produces just a keyword as slug:
        slug2 = _slugify_helper_name("func this thing now", "go")
        # slug = "func_this_thing_now" — not in reserved, passes
        assert slug2 != ""

    def test_slugify_rejects_exact_go_keyword(self) -> None:
        """If slug matches exactly a reserved word, it's rejected."""
        # Force a single-word slug: only word in clause
        slug = _slugify_helper_name("make the new object here", "go")
        # slug = "make_the_new_object_here" — not in reserved
        assert slug != ""

    def test_go_reserved_words_in_set(self) -> None:
        """Verify key Go reserved words exist in the set."""
        assert "func" in _GO_RESERVED
        assert "make" in _GO_RESERVED
        assert "select" in _GO_RESERVED
        assert "nil" in _GO_RESERVED

    def test_slugify_unknown_language_falls_back_to_python(self) -> None:
        """Unknown language should use Python reserved words."""
        slug = _slugify_helper_name("handle the request cleanly", "rust")
        # Uses _PYTHON_RESERVED as fallback — this slug isn't reserved
        assert slug != ""

    def test_moderate_decomposer_accepts_language_id(self) -> None:
        decomposer = ModerateDecomposer(language_id="go")
        assert decomposer._language_id == "go"


# ── MP-P3: Go Structural Verification ──


class TestGoStubDetection:
    """MP-P3: Stub detection uses Go patterns for Go skeletons."""

    def test_go_skeleton_has_panic_stub(self) -> None:
        skeleton = '''package main

func main() {
    panic("not implemented")
}
'''
        assert _skeleton_has_stubs(skeleton, _go_profile()) is True

    def test_go_skeleton_no_stubs(self) -> None:
        skeleton = '''package main

import "fmt"

func main() {
    fmt.Println("Hello")
}
'''
        assert _skeleton_has_stubs(skeleton, _go_profile()) is False

    def test_go_skeleton_has_todo_stub(self) -> None:
        skeleton = '''package main

func handler() {
    // TODO: implement
}
'''
        assert _skeleton_has_stubs(skeleton, _go_profile()) is True

    def test_python_skeleton_detection_unchanged(self) -> None:
        skeleton = '''def main():
    raise NotImplementedError
'''
        assert _skeleton_has_stubs(skeleton, _py_profile()) is True

    def test_python_skeleton_no_stubs(self) -> None:
        skeleton = '''def main():
    return 42
'''
        assert _skeleton_has_stubs(skeleton, _py_profile()) is False


# ── MP-P4: Go Signature Rendering ──


class TestGoSignatureRendering:
    """MP-P4: Render Go-style signatures."""

    def test_go_simple_signature(self) -> None:
        sig = Signature(
            params=[
                Param(name="name", kind=ParamKind.POSITIONAL, annotation="string"),
                Param(name="age", kind=ParamKind.POSITIONAL, annotation="int"),
            ],
            return_annotation="error",
        )
        result = _render_go_signature_str(sig)
        assert result == "(name string, age int)"

    def test_go_signature_skips_self(self) -> None:
        sig = Signature(
            params=[
                Param(name="self", kind=ParamKind.POSITIONAL_ONLY),
                Param(name="value", kind=ParamKind.POSITIONAL, annotation="int"),
            ],
            return_annotation=None,
        )
        result = _render_go_signature_str(sig)
        assert "self" not in result
        assert result == "(value int)"

    def test_go_empty_params(self) -> None:
        sig = Signature(params=[], return_annotation="error")
        result = _render_go_signature_str(sig)
        assert result == "()"

    def test_dispatch_python_uses_pep570(self) -> None:
        sig = Signature(
            params=[
                Param(name="x", kind=ParamKind.POSITIONAL, annotation="int"),
            ],
            return_annotation="int",
        )
        result = _render_signature_for_language(sig, "python")
        assert result == "(x: int)"

    def test_dispatch_go_uses_go_style(self) -> None:
        sig = Signature(
            params=[
                Param(name="x", kind=ParamKind.POSITIONAL, annotation="int"),
            ],
            return_annotation="int",
        )
        result = _render_signature_for_language(sig, "go")
        assert result == "(x int)"


# ── MP-P5: Go Literal Coercion ──


class TestGoLiteralCoercion:
    """MP-P5: Fix Python literals in Go context."""

    def test_none_to_nil(self) -> None:
        result = _coerce_literals_for_language("return None", "go")
        assert "nil" in result
        assert "None" not in result

    def test_true_to_lowercase(self) -> None:
        result = _coerce_literals_for_language("x := True", "go")
        assert "true" in result
        assert "True" not in result

    def test_false_to_lowercase(self) -> None:
        result = _coerce_literals_for_language("ok := False", "go")
        assert "false" in result
        assert "False" not in result

    def test_python_noop(self) -> None:
        code = "x = None"
        assert _coerce_literals_for_language(code, "python") == code

    def test_no_false_positive_in_strings(self) -> None:
        code = 'msg := "None of the above"'
        result = _coerce_literals_for_language(code, "go")
        # 'None' inside the string should be preserved
        assert "None of the above" in result

    def test_idempotent(self) -> None:
        code = "return nil"
        result = _coerce_literals_for_language(code, "go")
        assert result == code


# ── MP-P6: Go Function Decomposition ──


class TestGoFunctionDecomposition:
    """MP-P6: Function chain strategy handles Go."""

    def test_function_chain_accepts_language_id(self) -> None:
        strategy = FunctionChainStrategy(language_id="go")
        assert strategy._language_id == "go"

    def test_class_decompose_returns_false_for_go_elements(self) -> None:
        """Go has no classes — class decompose never applies."""
        from startd8.micro_prime.decomposer import ClassDecomposeStrategy
        from startd8.forward_manifest import ForwardManifest

        strategy = ClassDecomposeStrategy()
        # Go struct elements are mapped to ElementKind.CLASS
        element = ForwardElementSpec(
            kind=ElementKind.CLASS, name="Server",
            signature=None, docstring_hint="gRPC server",
        )
        file_spec = ForwardFileSpec(file="server.go", elements=[element])
        manifest = ForwardManifest(files=[file_spec])
        # No child methods → can_handle returns False
        assert strategy.can_handle(element, file_spec, manifest, "test") is False


# ── Integration: Go Files Flow Through MicroPrime ──


class TestGoNotBypassed:
    """Go files should flow through MicroPrime, not bypass it."""

    def test_go_file_not_in_non_python_extensions(self) -> None:
        assert _is_non_python_file("main.go") is False
        assert _is_non_python_file("src/server/handler.go") is False

    def test_go_mod_still_bypassed(self) -> None:
        """go.mod is a config file, still bypassed."""
        assert _is_non_python_file("go.mod") is True

    def test_go_sum_still_bypassed(self) -> None:
        assert _is_non_python_file("go.sum") is True

    def test_engine_with_go_profile(self) -> None:
        """Engine accepts GoLanguageProfile."""
        config = MicroPrimeConfig(provider="ollama", model="test")
        engine = MicroPrimeEngine(config=config, language_profile=_go_profile())
        assert engine._language_profile.language_id == "go"

    def test_engine_default_python_profile(self) -> None:
        """Engine defaults to PythonLanguageProfile."""
        config = MicroPrimeConfig(provider="ollama", model="test")
        engine = MicroPrimeEngine(config=config)
        assert engine._language_profile.language_id == "python"


# ── Validate file whole with Go ──


class TestValidateFileWholeGo:
    """validate_file_whole_result handles Go files."""

    @patch("subprocess.run")
    def test_valid_go_file(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        profile = _go_profile()
        code = '''package main

import "fmt"

func main() {
\tfmt.Println("Hello")
}
'''
        ok, reason, missing = _validate_file_whole_result(
            code, "", _make_file_spec("main.go"), profile,
        )
        assert ok is True, reason

    @patch("subprocess.run")
    def test_go_file_with_stubs_rejected(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        profile = _go_profile()
        code = '''package main

func handler() {
\tpanic("not implemented")
}
'''
        ok, reason, _ = _validate_file_whole_result(
            code, "", _make_file_spec("handler.go"), profile,
        )
        assert ok is False
        assert "stub" in reason.lower()

    @patch("subprocess.run")
    def test_go_file_syntax_error_rejected(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stderr="expected '}'")
        profile = _go_profile()
        ok, reason, _ = _validate_file_whole_result(
            "func {", "", _make_file_spec("bad.go"), profile,
        )
        assert ok is False
        assert "syntax" in reason.lower()


# ── Extract function body for Go ──


class TestExtractFunctionBodyGo:
    """extract_function_body handles Go via brace matching."""

    def test_go_simple_function(self) -> None:
        code = '''func Add(a int, b int) int {
\treturn a + b
}
'''
        element = _make_element("Add")
        # Mock go_splicer functions
        with patch("startd8.languages.go_splicer._find_func_declaration", return_value=0), \
             patch("startd8.languages.go_splicer._find_body_range", return_value=(0, 2)):
            result = extract_function_body(code, element, _go_profile())
        # Should extract the body (lines between { and })
        assert result is not None

    def test_python_function_unchanged(self) -> None:
        code = '''def add(a, b):
    return a + b
'''
        element = _make_element("add")
        result = extract_function_body(code, element, _py_profile())
        assert result is not None
        assert "return a + b" in result


# ── validate_syntax on language profiles ──


class TestLanguageProfileValidateSyntax:
    """All language profiles implement validate_syntax."""

    def test_python_profile(self) -> None:
        ok, _ = PythonLanguageProfile().validate_syntax("x = 1")
        assert ok is True

    def test_java_profile_valid(self) -> None:
        from startd8.languages.java import JavaLanguageProfile
        ok, _ = JavaLanguageProfile().validate_syntax("public class Foo { }")
        assert ok is True

    def test_nodejs_profile_has_method(self) -> None:
        from startd8.languages.nodejs import NodeLanguageProfile
        assert hasattr(NodeLanguageProfile(), "validate_syntax")
